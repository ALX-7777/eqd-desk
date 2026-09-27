#!/usr/bin/env python3
"""
fetch_snapshot.py — build a realistic seed snapshot for the EQD training app.

It pulls a small amount of free data from Yahoo Finance (via yfinance) and writes
a JSON file the app loads as its initial market state. It does NOT need to be
accurate or live — it just gives the simulator a realistic starting point.

What it fetches (per underlying):
  - index level + history   -> spot, realized vol
  - vol index (VIX/VSTOXX)  -> 30-day at-the-money implied vol anchor
  - options proxy (SPY/FEZ) -> real skew + ATM term structure (fit in log-moneyness)

Everything is wrapped so that a single failed fetch never aborts the run: missing
pieces fall back to sensible defaults and are flagged in `source_notes`.

Usage:
    pip install yfinance pandas numpy
    python scripts/fetch_snapshot.py --underlying spx           # default
    python scripts/fetch_snapshot.py --underlying sx5e --out src/data/snapshot.json

Note: index option chains (^GSPC, ^STOXX50E) are not served by Yahoo's API, so the
skew is taken from the listed ETF proxy (SPY / FEZ). Log-moneyness makes the fitted
shape scale-free, so it transfers to the index directly.
"""

import argparse
import datetime as dt
import json
import math
import sys

import numpy as np

try:
    import yfinance as yf
except ImportError:
    sys.exit("yfinance is required. Run: pip install yfinance pandas numpy")


# --- underlying presets -----------------------------------------------------
CONFIGS = {
    "spx": {
        "name": "S&P 500",
        "index_ticker": "^GSPC",
        "vol_ticker": "^VIX",
        "options_proxy": "SPY",
        "currency": "USD",
        "default_div_yield": 0.013,
        "default_rate": 0.04,   # placeholder USD short rate — set to current level
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


def safe_last_close(ticker: str):
    """Last daily close for a ticker, or None on any failure."""
    try:
        hist = yf.Ticker(ticker).history(period="1mo")
        if hist is None or hist.empty or "Close" not in hist:
            return None
        return float(hist["Close"].dropna().iloc[-1])
    except Exception as exc:
        print(f"  ! could not read {ticker}: {exc}")
        return None


def fetch_spot_and_realized(index_ticker: str):
    """Return (spot, realized_vol, asof_iso). Falls back to (None, None, today)."""
    asof = dt.date.today().isoformat()
    try:
        hist = yf.Ticker(index_ticker).history(period="1y")
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


def fetch_atm_vol(vol_ticker: str):
    """Vol index level -> decimal ATM 30d vol (e.g. VIX 16 -> 0.16). None on failure."""
    level = safe_last_close(vol_ticker)
    if level is None:
        return None
    return round(level / 100.0, 4)


def _nearest_expiry(expiries, target_days=TARGET_DTE_DAYS):
    """Pick the expiry string closest to `target_days` from now."""
    today = dt.date.today()
    best, best_gap = None, None
    for e in expiries:
        try:
            d = dt.datetime.strptime(e, "%Y-%m-%d").date()
        except ValueError:
            continue
        gap = abs((d - today).days)
        if best_gap is None or gap < best_gap:
            best, best_gap = e, gap
    return best


def fetch_skew_and_term(proxy_ticker: str):
    """
    From the proxy options chain, fit a quadratic smile in log-moneyness for the
    near-30d expiry and collect a small ATM term structure.

    Returns (skew_dict_or_None, term_structure_list). skew = {slope, curv} are the
    shape coefficients (ATM level is set separately from the vol index). The fit:
        iv(k) ~= a0 + slope*k + curv*k^2,   k = ln(strike / proxy_spot)
    """
    try:
        tk = yf.Ticker(proxy_ticker)
        expiries = list(tk.options or [])
        if not expiries:
            print(f"  ! {proxy_ticker} has no listed expiries")
            return None, []

        proxy_spot = safe_last_close(proxy_ticker)
        if not proxy_spot:
            return None, []

        # --- skew from the near-30d expiry ---
        exp = _nearest_expiry(expiries)
        chain = tk.option_chain(exp)
        rows = []
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
                if not (0.03 < float(iv) < 1.5):   # drop junk IVs
                    continue
                if (oi + vol) <= 0:                 # require a little liquidity
                    continue
                k = math.log(float(strike) / proxy_spot)
                if abs(k) > 0.30:                   # keep the usable wing
                    continue
                # use OTM side of each type to avoid deep-ITM noise
                if kind == "C" and k < -0.02:
                    continue
                if kind == "P" and k > 0.02:
                    continue
                rows.append((k, float(iv)))

        skew = None
        if len(rows) >= 5:
            ks = np.array([r[0] for r in rows])
            ivs = np.array([r[1] for r in rows])
            curv, slope, _a0 = np.polyfit(ks, ivs, 2)  # highest power first
            skew = {"slope": round(float(slope), 4), "curv": round(float(curv), 4)}
        else:
            print(f"  ! only {len(rows)} usable {proxy_ticker} quotes; will fall back")

        # --- small ATM term structure across a few expiries ---
        term = []
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


def _atm_iv_from_chain(chain, proxy_spot):
    """Average call/put IV for the strike nearest the proxy spot."""
    best = None
    for df in (chain.calls, chain.puts):
        if df is None or df.empty:
            continue
        sub = df.dropna(subset=["strike", "impliedVolatility"]) if "impliedVolatility" in df else None
        if sub is None or sub.empty:
            continue
        idx = (sub["strike"] - proxy_spot).abs().idxmin()
        iv = float(sub.loc[idx, "impliedVolatility"])
        if 0.03 < iv < 1.5:
            best = iv if best is None else (best + iv) / 2.0
    return best


def estimate_div_yield(proxy_ticker: str, fallback: float):
    """Trailing 12m proxy dividends / price, else fallback."""
    try:
        tk = yf.Ticker(proxy_ticker)
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


def build_snapshot(underlying: str):
    cfg = CONFIGS[underlying]
    notes = []
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

    snapshot = {
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
        "tickers": {k: cfg[k] for k in ("index_ticker", "vol_ticker", "options_proxy")},
    }
    return snapshot


def main():
    p = argparse.ArgumentParser(description="Seed-snapshot generator for the EQD trainer.")
    p.add_argument("--underlying", choices=sorted(CONFIGS), default="spx")
    p.add_argument("--out", default="src/data/snapshot.json")
    args = p.parse_args()

    snap = build_snapshot(args.underlying)

    try:
        import os
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(snap, f, indent=2)
        print(f"\nWrote {args.out}")
    except Exception as exc:
        print(f"\nCould not write {args.out}: {exc}\nSnapshot follows:")

    print(json.dumps(snap, indent=2))


if __name__ == "__main__":
    main()
