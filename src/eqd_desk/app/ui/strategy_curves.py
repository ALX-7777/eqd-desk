"""Curves of the strategy builder (port of ``web/src/components/StrategyPlots.tsx``): the
structure's P&L against terminal spot, its break-evens, and any aggregate greek swept across
spot, a parallel vol shift, or elapsed calendar time.

Pure: legs + market in, DataFrames out; the page only draws them. Every sweep uses the React
grid (``N = 120`` intervals, x computed as ``lo + ((hi - lo) * i) / N`` by
:func:`~eqd_desk.app.ui.charts.sweep_x`) and evaluates the engine at exactly those x, so each
plotted number equals the React app's for the same position.

Two spots are in play, as in React:

- ``spot`` — the SNAPSHOT spot. It fixes the plotted range (70 % … 130 % of it), so the
  axes stay put while the user drags the spot slider.
- ``market.S`` — the spot slider. It is where the structure is valued ("now") and where the
  dashed "current" marker sits.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

import pandas as pd

from eqd_desk.app.ui.charts import sweep_x
from eqd_desk.app.ui.format import js_round, to_fixed
from eqd_desk.engine import ReportedGreeks
from eqd_desk.engine.strategy import (
    GREEK_FIELDS,
    Leg,
    MarketParams,
    analyze_position,
    front_expiry,
    payoff_profile,
    position_premium,
    position_value_at,
)

N_POINTS: Final = 120
"""Sample intervals of every curve (React ``N``): 121 points."""

SPOT_LO: Final = 0.7
"""Low end of the spot axis, as a fraction of the snapshot spot."""
SPOT_HI: Final = 1.3
"""High end of the spot axis, as a fraction of the snapshot spot."""

VOL_SHIFT: Final = 0.10
"""Half-width of the parallel vol shift axis (decimal: ±10 vol points)."""

MIN_SWEEP_VOL: Final = 0.01
"""Floor on a leg's vol while sweeping the vol shift (1 vol point), as React."""
MIN_SWEEP_T: Final = 1e-6
"""Floor on a leg's remaining maturity (years) while sweeping elapsed time, as React."""
FRONT_EXPIRY_GAP: Final = 1e-4
"""The time axis stops this many years (~53 min) short of the front expiry, as React."""

StrategyXAxis = Literal["S", "vol", "time"]
"""What the aggregate greek is plotted against: spot, a parallel vol shift, elapsed time."""

X_AXIS_OPTIONS: Final[Mapping[StrategyXAxis, str]] = MappingProxyType(
    {"S": "Spot", "vol": "Vol", "time": "Time"}
)
"""Segmented-control labels of the x-axis picker, in React's order."""


def spot_range(spot: float) -> tuple[float, float]:
    """``(0.7·spot, 1.3·spot)``: the spot axis of both charts (``spot`` = snapshot spot)."""
    return spot * SPOT_LO, spot * SPOT_HI


def unique_strikes(legs: Sequence[Leg]) -> tuple[float, ...]:
    """Distinct strikes in leg order (React ``Array.from(new Set(legs.map(l => l.K)))``):
    the dotted markers of the P&L chart."""
    return tuple(dict.fromkeys(leg.K for leg in legs))


# ------------------------------------------------------------------ P&L vs spot


def payoff_frame(
    legs: Sequence[Leg], market: MarketParams, spot: float, n: int = N_POINTS
) -> pd.DataFrame:
    """The P&L profile over the spot axis (engine ``payoff_profile``).

    Columns: ``S`` (terminal spot), ``expiry`` (P&L at the FRONT expiry, the classic payoff
    diagram, correct for calendars) and ``now`` (P&L if spot moved there today: the smooth
    mark-to-market). Both are net of the premium paid at ``market``, so they cross zero at
    the break-evens.
    """
    lo, hi = spot_range(spot)
    pts = payoff_profile(legs, market, lo, hi, n)
    return pd.DataFrame(
        {
            "S": [p.S for p in pts],
            "expiry": [p.expiry_pnl for p in pts],
            "now": [p.now_pnl for p in pts],
        }
    )


def _bisect(f: Callable[[float], float], a: float, b: float, fa: float) -> float:
    """A root of the continuous ``f`` in ``[a, b]``, given ``f(a)`` and ``f(b)`` of
    opposite signs, to full double precision."""
    for _ in range(200):
        mid = 0.5 * (a + b)
        if mid in (a, b):  # adjacent doubles: cannot split further
            break
        fm = f(mid)
        if fm == 0:
            return mid
        if (fm < 0) == (fa < 0):
            a, fa = mid, fm
        else:
            b = mid
    return 0.5 * (a + b)


def break_evens(
    legs: Sequence[Leg], market: MarketParams, spot: float, n: int = N_POINTS
) -> tuple[float, ...]:
    """Terminal spots on the chart's axis where the P&L at the front expiry is zero, in
    increasing order.

    The P&L is sampled on the chart grid PLUS every strike in range (the kinks of an expiry
    payoff; between kinks a single-expiry structure's P&L is a straight line, so no crossing
    can hide between two samples), and each sign change is refined by bisection on the exact
    engine value. A sample that is exactly zero counts once (a flat stretch of zero P&L, like
    an empty position, has no break-even).
    """
    if not legs:
        return ()
    lo, hi = spot_range(spot)
    premium = position_premium(legs, market)
    at_t = front_expiry(legs)

    def pnl(s: float) -> float:
        return position_value_at(legs, s, at_t, market) - premium

    xs = sorted({*sweep_x(lo, hi, n), *(k for k in unique_strikes(legs) if lo < k < hi)})
    ys = [pnl(x) for x in xs]
    roots: list[float] = []
    for i, (x, y) in enumerate(zip(xs, ys, strict=True)):
        if y == 0:
            if i == 0 or ys[i - 1] != 0:
                roots.append(x)
            continue
        if i + 1 < len(xs) and ys[i + 1] != 0 and (ys[i + 1] < 0) != (y < 0):
            roots.append(_bisect(pnl, x, xs[i + 1], y))
    if len(roots) == len(xs):  # identically zero: no meaningful break-even
        return ()
    return tuple(roots)


# ------------------------------------------------------------------ greek vs x


@dataclass(frozen=True, slots=True)
class AxisMeta:
    """The x axis of the aggregate-greek chart (React ``buildAxisMeta``)."""

    key: StrategyXAxis
    label: str
    """"Spot", "Vol shift" or "Time elapsed" (the chart heading says ``vs <label>``)."""
    lo: float
    """First x of the sweep (engine units: index points, decimal vol shift, years)."""
    hi: float
    """Last x of the sweep."""
    current: float
    """Where the dashed "now" marker sits (the spot slider; 0 shift; 0 elapsed)."""
    plot_scale: float
    """Multiplier from engine units to plotted units (vol shift → vol points, years →
    days), so the axis reads in trader units."""
    axis_title: str
    """Axis title in plotted units."""
    axis_format: str | None
    """d3 format of the plotted axis ticks (``None`` = Vega's default)."""

    def tick(self, x_plot: float) -> str:
        """The React tick/tooltip text of a PLOTTED x: ``"6312"``, ``"+5pt"``, ``"12d"``."""
        match self.key:
            case "vol":
                return f"{'+' if x_plot >= 0 else ''}{to_fixed(x_plot, 0)}pt"
            case "time":
                return f"{js_round(x_plot)}d"
            case "S":
                return to_fixed(x_plot, 0)


def build_axis_meta(
    x_axis: StrategyXAxis, legs: Sequence[Leg], market: MarketParams, spot: float
) -> AxisMeta:
    """Range and labels of the greek sweep (React ``buildAxisMeta``):

    - ``S``: spot over 70 % … 130 % of the snapshot spot, marker at the spot slider;
    - ``vol``: a parallel shift of every leg's vol by −10 … +10 points, marker at 0;
    - ``time``: calendar time elapsed from today to just before the front expiry (at least
      one day), marker at 0.
    """
    match x_axis:
        case "vol":
            return AxisMeta(
                "vol", "Vol shift", -VOL_SHIFT, VOL_SHIFT, 0.0, 100.0, "Vol shift (vol pts)", "+d"
            )
        case "time":
            hi = max(front_expiry(legs) - FRONT_EXPIRY_GAP, 1 / 365)
            return AxisMeta("time", "Time elapsed", 0.0, hi, 0.0, 365.0, "Days elapsed", "d")
        case "S":
            lo, hi_s = spot_range(spot)
            return AxisMeta("S", "Spot", lo, hi_s, market.S, 1.0, "Spot", None)


def greeks_at(
    x_axis: StrategyXAxis, legs: Sequence[Leg], market: MarketParams, x: float
) -> ReportedGreeks:
    """The position's price and greeks (reported units) at one x of the sweep (React
    ``evalGreek``):

    - ``S``: revalued at spot ``x``;
    - ``vol``: every leg's vol shifted by ``x`` (floored at 1 point);
    - ``time``: ``x`` years have passed (each leg's maturity shortened, floored at 1e-6 y),
      spot and vols unchanged.
    """
    match x_axis:
        case "vol":
            shifted = [
                dataclasses.replace(leg, sigma=max(MIN_SWEEP_VOL, leg.sigma + x)) for leg in legs
            ]
            return analyze_position(shifted, market).reported
        case "time":
            aged = [dataclasses.replace(leg, T=max(MIN_SWEEP_T, leg.T - x)) for leg in legs]
            return analyze_position(aged, market).reported
        case "S":
            return analyze_position(legs, dataclasses.replace(market, S=x)).reported


def greek_sweep(
    x_axis: StrategyXAxis,
    legs: Sequence[Leg],
    market: MarketParams,
    spot: float,
    n: int = N_POINTS,
) -> pd.DataFrame:
    """Every aggregate greek (and the price) along the chosen axis.

    Columns: ``x`` (engine units), ``x_plot`` (``x × plot_scale``: spot, vol points or
    days) and one column per field of :data:`~eqd_desk.engine.strategy.GREEK_FIELDS`
    (``price``, ``delta``, …, ``color``) in reported desk units. Picking the plotted greek
    is then a column lookup.
    """
    meta = build_axis_meta(x_axis, legs, market, spot)
    xs = sweep_x(meta.lo, meta.hi, n)
    rows = [greeks_at(x_axis, legs, market, x).as_dict() for x in xs]
    frame = pd.DataFrame({"x": xs, "x_plot": [x * meta.plot_scale for x in xs]})
    for f in GREEK_FIELDS:
        frame[f] = [row[f] for row in rows]
    return frame


def sweep_heading(meta: AxisMeta) -> str:
    """The lower-case axis name of the chart heading ("Net Delta vs ``spot``")."""
    return meta.label.lower()


__all__ = [
    "FRONT_EXPIRY_GAP",
    "MIN_SWEEP_T",
    "MIN_SWEEP_VOL",
    "N_POINTS",
    "SPOT_HI",
    "SPOT_LO",
    "VOL_SHIFT",
    "X_AXIS_OPTIONS",
    "AxisMeta",
    "StrategyXAxis",
    "break_evens",
    "build_axis_meta",
    "greek_sweep",
    "greeks_at",
    "payoff_frame",
    "spot_range",
    "sweep_heading",
    "unique_strikes",
]
