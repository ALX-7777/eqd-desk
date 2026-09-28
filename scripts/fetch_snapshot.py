#!/usr/bin/env python3
"""fetch_snapshot.py — build a realistic seed snapshot for the EQD training app.

It pulls a small amount of free data from Yahoo Finance (via yfinance) and writes a JSON
file the app loads as its initial market state. It does NOT need to be accurate or live:
it just gives the simulator a realistic starting point.

What it fetches (per underlying):
  - index level + history   -> spot, realized vol
  - vol index (VIX/VSTOXX)  -> 30-day at-the-money implied vol anchor
  - options proxy (SPY/FEZ) -> real skew + ATM term structure (fit in log-moneyness)

Everything is wrapped so that a single failed fetch never aborts the run: missing pieces
fall back to sensible defaults and are flagged in ``source_notes``.

Usage (from the repo root; ``--group scripts`` pulls in yfinance)::

    uv run --group scripts python scripts/fetch_snapshot.py                 # spx (default)
    uv run --group scripts python scripts/fetch_snapshot.py --underlying sx5e
    uv run --group scripts python scripts/fetch_snapshot.py --out my.json --mirror ''

By default the snapshot is written to ``src/eqd_desk/data/snapshot.json`` (the Python
app's package data) and mirrored to ``web/src/data/snapshot.json`` (the React app), so
both apps stay in sync. ``--mirror ''`` disables the mirror; it is also skipped when its
directory does not exist (e.g. inside the Docker image, which has no ``web/``). A custom
``--out`` is NOT mirrored unless ``--mirror PATH`` is given too, so a one-off output never
refreshes the React copy alone.
Without uv: ``pip install yfinance pandas numpy`` then ``python scripts/fetch_snapshot.py``.

Note: index option chains (^GSPC, ^STOXX50E) are not served by Yahoo's API, so the skew
is taken from the listed ETF proxy (SPY / FEZ). Log-moneyness makes the fitted shape
scale-free, so it transfers to the index directly.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import math
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, TypedDict

import numpy as np


class Preset(TypedDict):
    """One underlying preset (mirrors ``eqd_desk.data.config.UNDERLYINGS`` + a rate)."""

    name: str
    index_ticker: str
    vol_ticker: str
    options_proxy: str
    currency: str
    default_div_yield: float
    default_rate: float


# --- underlying presets -----------------------------------------------------
CONFIGS: dict[str, Preset] = {
    "spx": {
        "name": "S&P 500",
        "index_ticker": "^GSPC",
        "vol_ticker": "^VIX",
        "options_proxy": "SPY",
        "currency": "USD",
        "default_div_yield": 0.013,
        "default_rate": 0.04,  # placeholder USD short rate — set to current level
    },
    "sx5e": {
        "name": "Euro Stoxx 50",
        "index_ticker": "^STOXX50E",
        "vol_ticker": "V2TX.DE",
        "options_proxy": "FEZ",
        "currency": "EUR",
        "default_div_yield": 0.03,
        "default_rate": 0.025,  # placeholder EUR short rate — set to current level
    },
}

TRADING_DAYS = 252
TARGET_DTE_DAYS = 30  # expiry we aim for when sampling the proxy smile

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "src" / "eqd_desk" / "data" / "snapshot.json"
DEFAULT_MIRROR = REPO_ROOT / "web" / "src" / "data" / "snapshot.json"


def _yf() -> Any:
    """Import yfinance on first use, so ``--help`` (and offline tests) work without it."""
    try:
        return importlib.import_module("yfinance")
    except ImportError:
        sys.exit(
            "yfinance is required. Run: uv run --group scripts python scripts/fetch_snapshot.py"
            "  (or: pip install yfinance pandas numpy)"
        )


def safe_last_close(ticker: str) -> float | None:
    """Last daily close for a ticker, or None on any failure."""
    try:
        hist = _yf().Ticker(ticker).history(period="1mo")
        if hist is None or hist.empty or "Close" not in hist:
            return None
        return float(hist["Close"].dropna().iloc[-1])
    except Exception as exc:
        print(f"  ! could not read {ticker}: {exc}")
        return None


def fetch_spot_and_realized(index_ticker: str) -> tuple[float | None, float | None, str]:
    """Return (spot, realized_vol, asof_iso). Falls back to (None, None, today)."""
    asof = dt.date.today().isoformat()
    try:
        hist = _yf().Ticker(index_ticker).history(period="1y")
        if hist is None or hist.empty or "Close" not in hist:
            raise ValueError("no history returned")
        close = hist["Close"].dropna()
        spot = float(close.iloc[-1])
        asof = close.index[-1].date().isoformat()
        logret = np.log(close / close.shift(1)).dropna()
        realized = float(logret.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(logret) > 5 else None
        return spot, realized, asof
    except Exception as exc:
        print(f"  ! index fetch failed for {index_ticker}: {exc}")
        return None, None, asof


def fetch_atm_vol(vol_ticker: str) -> float | None:
    """Vol index level -> decimal ATM 30d vol (e.g. VIX 16 -> 0.16). None on failure."""
    level = safe_last_close(vol_ticker)
    if level is None:
        return None
    return round(level / 100.0, 4)


def _nearest_expiry(
    expiries: Iterable[str], target_days: int = TARGET_DTE_DAYS, today: dt.date | None = None
) -> str | None:
    """Pick the expiry string (``YYYY-MM-DD``) closest to ``target_days`` from ``today``.

    Unparseable strings are skipped; ties keep the earlier-listed expiry. Returns None
    if nothing parses.
    """
    today = today or dt.date.today()
    best: str | None = None
    best_gap: int | None = None
    for e in expiries:
        try:
            d = dt.datetime.strptime(e, "%Y-%m-%d").date()
        except ValueError:
            continue
        gap = abs((d - today).days - target_days)
        if best_gap is None or gap < best_gap:
            best, best_gap = e, gap
    return best


def fetch_skew_and_term(
    proxy_ticker: str,
) -> tuple[dict[str, float] | None, list[dict[str, float]]]:
    """From the proxy options chain, fit a quadratic smile in log-moneyness for the
    near-30d expiry and collect a small ATM term structure.

    Returns (skew_dict_or_None, term_structure_list). skew = {slope, curv} are the shape
    coefficients (ATM level is set separately from the vol index). The fit::

        iv(k) ~= a0 + slope*k + curv*k^2,   k = ln(strike / proxy_spot)
    """
    try:
        tk = _yf().Ticker(proxy_ticker)
        expiries: list[str] = list(tk.options or [])
        if not expiries:
            print(f"  ! {proxy_ticker} has no listed expiries")
            return None, []

        proxy_spot = safe_last_close(proxy_ticker)
        if not proxy_spot:
            return None, []

        # --- skew from the near-30d expiry ---
        exp = _nearest_expiry(expiries)
        chain = tk.option_chain(exp)
        rows: list[tuple[float, float]] = []
        for df, kind in ((chain.calls, "C"), (chain.puts, "P")):
            if df is None or df.empty:
                continue
            for _, r in df.iterrows():
                iv = r.get("impliedVolatility", None)
                strike = r.get("strike", None)
                oi = r.get("openInterest", 0) or 0
                vol = r.get("volume", 0) or 0
                if iv is None or strike is None:
                    continue
                if not (0.03 < float(iv) < 1.5):  # drop junk IVs
                    continue
                if (oi + vol) <= 0:  # require a little liquidity
                    continue
                k = math.log(float(strike) / proxy_spot)
                if abs(k) > 0.30:  # keep the usable wing
                    continue
                # use OTM side of each type to avoid deep-ITM noise
                if kind == "C" and k < -0.02:
                    continue
                if kind == "P" and k > 0.02:
                    continue
                rows.append((k, float(iv)))

        skew: dict[str, float] | None = None
        if len(rows) >= 5:
            ks = np.array([r[0] for r in rows])
            ivs = np.array([r[1] for r in rows])
            curv, slope, _a0 = np.polyfit(ks, ivs, 2)  # highest power first
            skew = {"slope": round(float(slope), 4), "curv": round(float(curv), 4)}
        else:
            print(f"  ! only {len(rows)} usable {proxy_ticker} quotes; will fall back")

        # --- small ATM term structure across a few expiries ---
        term: list[dict[str, float]] = []
        for e in expiries[:8]:
            try:
                d = dt.datetime.strptime(e, "%Y-%m-%d").date()
            except ValueError:
                continue
            t_years = max((d - dt.date.today()).days, 1) / 365.0
            try:
                ch = tk.option_chain(e)
            except Exception:
                continue
            atm_iv = _atm_iv_from_chain(ch, proxy_spot)
            if atm_iv is not None:
                term.append({"t": round(t_years, 4), "atm_iv": round(atm_iv, 4)})

        return skew, term
    except Exception as exc:
        print(f"  ! proxy options fetch failed for {proxy_ticker}: {exc}")
        return None, []


def _atm_iv_from_chain(chain: Any, proxy_spot: float) -> float | None:
    """Average call/put IV for the strike nearest the proxy spot."""
    best: float | None = None
    for df in (chain.calls, chain.puts):
        if df is None or df.empty:
            continue
        sub = (
            df.dropna(subset=["strike", "impliedVolatility"]) if "impliedVolatility" in df else None
        )
        if sub is None or sub.empty:
            continue
        idx = (sub["strike"] - proxy_spot).abs().idxmin()
        iv = float(sub.loc[idx, "impliedVolatility"])
        if 0.03 < iv < 1.5:
            best = iv if best is None else (best + iv) / 2.0
    return best


def estimate_div_yield(proxy_ticker: str, fallback: float) -> float:
    """Trailing 12m proxy dividends / price, else fallback."""
    try:
        tk = _yf().Ticker(proxy_ticker)
        divs = tk.dividends
        price = safe_last_close(proxy_ticker)
        if divs is not None and not divs.empty and price:
            one_year_ago = dt.datetime.now(divs.index.tz) - dt.timedelta(days=365)
            recent = divs[divs.index >= one_year_ago]
            if not recent.empty:
                y = float(recent.sum()) / price
                if 0 < y < 0.12:
                    return round(y, 4)
    except Exception as exc:
        print(f"  ! dividend estimate failed for {proxy_ticker}: {exc}")
    return fallback


def build_snapshot(underlying: str) -> dict[str, Any]:
    """Fetch everything for ``underlying`` and assemble the snapshot JSON payload."""
    cfg = CONFIGS[underlying]
    notes: list[str] = []
    print(f"Fetching {cfg['name']} ({underlying}) ...")

    spot, realized, asof = fetch_spot_and_realized(cfg["index_ticker"])
    if spot is None:
        spot = 6000.0 if underlying == "spx" else 5000.0
        notes.append(f"index {cfg['index_ticker']} unavailable; spot is a placeholder")
    if realized is None:
        notes.append("realized vol unavailable")

    atm = fetch_atm_vol(cfg["vol_ticker"])
    if atm is None:
        atm = 0.18
        notes.append(f"vol index {cfg['vol_ticker']} unavailable; atm_vol_30d defaulted to 0.18")

    skew, term = fetch_skew_and_term(cfg["options_proxy"])
    if skew is None:
        # parametric equity skew: downward in strike, mild smile (decimal vols)
        skew = {"slope": -0.40, "curv": 0.60}
        notes.append(f"proxy {cfg['options_proxy']} skew unavailable; using parametric fallback")
    skew["atm"] = atm  # ATM level comes from the vol index

    q = estimate_div_yield(cfg["options_proxy"], cfg["default_div_yield"])

    return {
        "asof": asof,
        "underlying": underlying,
        "name": cfg["name"],
        "currency": cfg["currency"],
        "spot": round(spot, 2),
        "r": cfg["default_rate"],
        "q": q,
        "realized_vol": round(realized, 4) if realized is not None else None,
        "atm_vol_30d": atm,
        "skew": skew,
        "term_structure": term,
        "source_notes": notes or ["all fields fetched live"],
        "tickers": {
            "index_ticker": cfg["index_ticker"],
            "vol_ticker": cfg["vol_ticker"],
            "options_proxy": cfg["options_proxy"],
        },
    }


def write_outputs(text: str, out: Path, mirror: Path | None) -> list[Path]:
    """Write ``text`` (UTF-8, LF line endings) to ``out`` and, when given, to ``mirror``.

    ``out``'s directory is created if needed. The mirror keeps the React app's copy in
    sync; it is skipped (with a message) when its directory does not exist, e.g. inside
    the Docker image where ``web/`` is absent. Returns the paths actually written.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    written = [out]
    if mirror is not None and mirror.resolve() != out.resolve():
        if mirror.parent.is_dir():
            mirror.write_text(text, encoding="utf-8", newline="\n")
            written.append(mirror)
        else:
            print(f"  (mirror skipped: {mirror.parent} does not exist)")
    return written


def resolve_mirror(out: Path, mirror_arg: str | None) -> Path | None:
    """Where to mirror the output (``None`` = nowhere).

    An explicit ``--mirror PATH`` is always honoured and ``--mirror ''`` disables the
    mirror. Left unset, the React copy (:data:`DEFAULT_MIRROR`) is written only when
    ``--out`` is the package default (:data:`DEFAULT_OUT`): refreshing the React app from a
    custom ``--out`` (a scratch file, or the pre-Python ``src/data/`` path) would leave the
    two committed copies out of sync, with the Python app still on the old data.
    """
    if mirror_arg is not None:
        return Path(mirror_arg) if mirror_arg else None
    return DEFAULT_MIRROR if out.resolve() == DEFAULT_OUT.resolve() else None


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point (``argv`` defaults to ``sys.argv[1:]``)."""
    p = argparse.ArgumentParser(description="Seed-snapshot generator for the EQD trainer.")
    p.add_argument("--underlying", choices=sorted(CONFIGS), default="spx")
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="output JSON (default: src/eqd_desk/data/snapshot.json, the Python package data)",
    )
    p.add_argument(
        "--mirror",
        default=None,
        help="also write this copy (default: web/src/data/snapshot.json, the React app, "
        "but only when --out is left at its default); pass '' to disable",
    )
    args = p.parse_args(argv)
    mirror = resolve_mirror(args.out, args.mirror)
    if mirror is None and args.mirror is None:
        print("  (custom --out: the React copy is not mirrored; add --mirror PATH to write one)")

    snap = build_snapshot(args.underlying)
    text = json.dumps(snap, indent=2)

    try:
        for path in write_outputs(text, args.out, mirror):
            print(f"\nWrote {path}")
    except OSError as exc:
        print(f"\nCould not write {args.out}: {exc}\nSnapshot follows:")

    print(text)


if __name__ == "__main__":
    main()
