"""Historical replay: step the market along a REAL past spot/VIX path instead of
simulating it.

Pure: the history series is supplied by the data layer; this just picks a random window
and maps each point to a :class:`~eqd_desk.engine.sim.market.MarketState` (VIX/100 is the
ATM implied; the skew shape is carried from config). The date is not exposed: you trade an
undisclosed slice of history.

:class:`HistoryPoint` is defined HERE (not in ``eqd_desk.data``) so the engine keeps zero
dependency on the data layer; the data loader builds these points.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from eqd_desk.engine.sim.market import MarketState

REPLAY_VOL_FLOOR: Final = 0.05
"""Floor on the replayed ATM vol (decimal): VIX/100 is never taken below 5%."""


@dataclass(frozen=True, slots=True)
class HistoryPoint:
    """One trading day of real history."""

    date: str
    """ISO date (``YYYY-MM-DD``) of the close."""
    spot: float
    """Index close, in index points (e.g. ^GSPC)."""
    vix: float
    """Vol-index close, in VOL POINTS (e.g. 16.2; divide by 100 for a decimal ATM vol)."""


@dataclass(frozen=True, slots=True)
class ReplayWindow:
    """A contiguous slice of the history series to replay."""

    points: tuple[HistoryPoint, ...]
    """The window's points (``length + 1`` of them when the series is long enough)."""
    start_index: int
    """Index into the full series, for an optional post-hoc reveal."""


@dataclass(frozen=True, slots=True)
class ReplayBase:
    """Market inputs the history does not carry (taken from config / the snapshot)."""

    r: float
    """Continuously-compounded risk-free rate (decimal)."""
    q: float
    """Continuously-compounded dividend yield (decimal)."""
    skew_slope: float
    """Skew slope in log-moneyness (≤ 0 for equity skew)."""
    skew_curv: float
    """Smile curvature in log-moneyness."""
    dt: float
    """Step size in years (1/252 = one trading day)."""


def pick_window(series: Sequence[HistoryPoint], length: int, u: float) -> ReplayWindow:
    """Pick a random window of ``length`` steps (``length + 1`` points) from the series.

    ``u`` is a uniform draw in [0, 1): the start index is ``floor(u·(maxStart + 1))``
    (clamped), where ``maxStart = max(0, len(series) − length − 1)``. A series shorter than
    the window yields the whole series.
    """
    max_start = max(0, len(series) - length - 1)
    start_index = min(max_start, math.floor(u * (max_start + 1)))
    return ReplayWindow(
        points=tuple(series[start_index : start_index + length + 1]), start_index=start_index
    )


def window_steps(win: ReplayWindow) -> int:
    """Number of steps available in a window (points − 1, never negative)."""
    return max(0, len(win.points) - 1)


def replay_state(win: ReplayWindow, i: int, base: ReplayBase) -> MarketState:
    """Market state at step ``i`` of a replay window.

    ``i`` is clamped into the window; the clock is ``idx·dt`` years and the ATM vol is
    ``max(0.05, VIX/100)``.

    Raises:
        ValueError: if the window is empty (the TS engine throws a ``TypeError`` there).
    """
    if len(win.points) == 0:
        raise ValueError("replay_state: the replay window has no points")
    idx = max(0, min(i, len(win.points) - 1))
    p = win.points[idx]
    return MarketState(
        t=idx * base.dt,
        spot=p.spot,
        atm_vol=max(REPLAY_VOL_FLOOR, p.vix / 100),
        r=base.r,
        q=base.q,
        skew_slope=base.skew_slope,
        skew_curv=base.skew_curv,
    )


__all__ = [
    "REPLAY_VOL_FLOOR",
    "HistoryPoint",
    "ReplayBase",
    "ReplayWindow",
    "pick_window",
    "replay_state",
    "window_steps",
]
