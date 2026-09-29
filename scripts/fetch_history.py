#!/usr/bin/env python3
"""fetch_history.py — pull real daily history for the trading simulator's "historical
replay" mode.

It fetches the index level (^GSPC) and the vol index (^VIX) and writes a JSON series the
app replays: on each Reset the simulator picks a random undisclosed window and you trade
against the real path. This is seed/realism data only: it never touches the reactive loop.

Usage (from the repo root; ``--group scripts`` pulls in yfinance)::

    uv run --group scripts python scripts/fetch_history.py                  # 8 years
    uv run --group scripts python scripts/fetch_history.py --years 10
    uv run --group scripts python scripts/fetch_history.py --out my.json --mirror ''

By default the series is written to ``src/eqd_desk/data/history.json`` (the Python app's
package data) and mirrored to ``web/src/data/history.json`` (the React app), so both apps
stay in sync. ``--mirror ''`` disables the mirror; it is also skipped when its directory
does not exist (e.g. inside the Docker image, which has no ``web/``). A custom ``--out``
is NOT mirrored unless ``--mirror PATH`` is given too, so a one-off output never
refreshes the React copy alone.
Without uv: ``pip install yfinance pandas numpy`` then ``python scripts/fetch_history.py``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypedDict

MIN_POINTS = 100
"""Refuse to write a series shorter than this many aligned trading days."""

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "src" / "eqd_desk" / "data" / "history.json"
DEFAULT_MIRROR = REPO_ROOT / "web" / "src" / "data" / "history.json"


class HistoryRow(TypedDict):
    """One day of the output series (the JSON shape of ``eqd_desk.data.HistoryPoint``)."""

    date: str
    spot: float
    vix: float


def _yf() -> Any:
    """Import yfinance on first use, so ``--help`` (and offline tests) work without it."""
    try:
        return importlib.import_module("yfinance")
    except ImportError:
        sys.exit(
            "yfinance is required. Run: uv run --group scripts python scripts/fetch_history.py"
            "  (or: pip install yfinance pandas numpy)"
        )


def fetch_series(years: int) -> list[HistoryRow]:
    """Daily ^GSPC close + ^VIX close over the last ``years`` years, aligned on the trading
    days both have, oldest first. Days with a non-positive spot or a VIX outside (1, 200)
    are dropped as bad prints.

    Raises:
        RuntimeError: if Yahoo returns no history for either ticker.
    """
    yf = _yf()
    period = f"{max(1, years)}y"
    gspc = yf.Ticker("^GSPC").history(period=period)
    vix = yf.Ticker("^VIX").history(period=period)
    if gspc is None or gspc.empty or vix is None or vix.empty:
        raise RuntimeError("no history returned for ^GSPC / ^VIX")

    spot = gspc["Close"].dropna()
    vol = vix["Close"].dropna()
    # align on common trading days
    spot.index = spot.index.tz_localize(None).normalize()
    vol.index = vol.index.tz_localize(None).normalize()
    common = spot.index.intersection(vol.index)

    series: list[HistoryRow] = []
    for d in common:
        s = float(spot.loc[d])
        v = float(vol.loc[d])
        if s > 0 and 1.0 < v < 200.0:
            series.append({"date": d.date().isoformat(), "spot": round(s, 2), "vix": round(v, 2)})
    return series


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
    p = argparse.ArgumentParser(description="Historical replay data for the EQD simulator.")
    p.add_argument("--years", type=int, default=8)
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="output JSON (default: src/eqd_desk/data/history.json, the Python package data)",
    )
    p.add_argument(
        "--mirror",
        default=None,
        help="also write this copy (default: web/src/data/history.json, the React app, "
        "but only when --out is left at its default); pass '' to disable",
    )
    args = p.parse_args(argv)
    mirror = resolve_mirror(args.out, args.mirror)
    if mirror is None and args.mirror is None:
        print("  (custom --out: the React copy is not mirrored; add --mirror PATH to write one)")

    print(f"Fetching {args.years}y of ^GSPC + ^VIX ...")
    series = fetch_series(args.years)
    if len(series) < MIN_POINTS:
        sys.exit(f"too few aligned days ({len(series)})")

    payload = {
        "asof": dt.date.today().isoformat(),
        "source": "Yahoo Finance ^GSPC (spot) + ^VIX (implied ATM, vol points)",
        "count": len(series),
        "series": series,
    }

    text = json.dumps(payload) + "\n"  # compact (one line), with a final newline
    for path in write_outputs(text, args.out, mirror):
        print(f"Wrote {len(series)} daily points -> {path}")
    print(f"Range: {series[0]['date']} .. {series[-1]['date']}")


if __name__ == "__main__":
    main()
