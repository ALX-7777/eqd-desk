#!/usr/bin/env python3
"""
fetch_history.py — pull real daily history for the trading simulator's
"historical replay" mode.

It fetches the index level (^GSPC) and the vol index (^VIX) and writes a JSON
series the app replays: on each Reset the simulator picks a random undisclosed
window and you trade against the real path. This is seed/realism data only — it
never touches the reactive loop.

Usage:
    pip install yfinance pandas numpy
    python scripts/fetch_history.py --years 8 --out src/data/history.json
"""

import argparse
import datetime as dt
import json
import sys

try:
    import yfinance as yf
except ImportError:
    sys.exit("yfinance is required. Run: pip install yfinance pandas numpy")


def fetch_series(years: int):
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

    series = []
    for d in common:
        s = float(spot.loc[d])
        v = float(vol.loc[d])
        if s > 0 and 1.0 < v < 200.0:
            series.append({"date": d.date().isoformat(), "spot": round(s, 2), "vix": round(v, 2)})
    return series


def main():
    p = argparse.ArgumentParser(description="Historical replay data for the EQD simulator.")
    p.add_argument("--years", type=int, default=8)
    p.add_argument("--out", default="src/data/history.json")
    args = p.parse_args()

    print(f"Fetching {args.years}y of ^GSPC + ^VIX ...")
    series = fetch_series(args.years)
    if len(series) < 100:
        sys.exit(f"too few aligned days ({len(series)})")

    payload = {
        "asof": dt.date.today().isoformat(),
        "source": "Yahoo Finance ^GSPC (spot) + ^VIX (implied ATM, vol points)",
        "count": len(series),
        "series": series,
    }

    import os

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f)
    print(f"Wrote {len(series)} daily points -> {args.out}")
    print(f"Range: {series[0]['date']} .. {series[-1]['date']}")


if __name__ == "__main__":
    main()
