"""Input bounds and grids shared by the pages: one definition per rule, so the greeks lab,
the strategy builder, the exotics and the simulator agree by construction.

- :class:`Bounds` — a slider's range and increment.
- :data:`RATE_BOUNDS`, :data:`DIV_BOUNDS`, :data:`T_BOUNDS` — the r, q and time-to-expiry
  sliders (React ``InputPanel.tsx``; the strategy builder and the exotics reuse the r / q
  ranges).
- :data:`SPOT_RANGE_FACTORS` — spot and strike sliders (and the spot sweeps) span 0.6× to
  1.4× the SNAPSHOT spot.
- :func:`level_step` — the increment of a spot / strike slider.
- :func:`listed_strike_step` — the index's listed-strike grid (exotics, simulator).

The strategy builder rounds its legs to a finer, three-tier grid of its own
(:func:`eqd_desk.app.ui.strategy_builder_legs.strike_step_for`, React ``strikeStepFor``).

Units: levels in index points, T in years, r and q as continuously compounded decimals.
Pure: no Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Bounds:
    """Range and increment of one slider (React ``min`` / ``max`` / ``step``)."""

    lo: float
    hi: float
    step: float


RATE_BOUNDS: Final = Bounds(-0.02, 0.10, 0.0005)
"""Rate r: −2 % … 10 %, in steps of 5 bp."""

DIV_BOUNDS: Final = Bounds(0.0, 0.06, 0.0005)
"""Dividend yield q: 0 … 6 %, in steps of 5 bp."""

T_BOUNDS: Final = Bounds(0.003, 2.0, 0.003)
"""Time to expiry of a vanilla (years): about a day to two years, in steps of about a day.
Also the greeks lab's sweep range against time."""

SPOT_RANGE_FACTORS: Final = (0.6, 1.4)
"""Spot and strike sliders span these multiples of the snapshot spot (so the range stays
put while spot is dragged); the spot sweeps and payoff charts use the same range."""


def level_step(spot: float) -> float:
    """Increment of a spot / strike slider, in index points: 1 for an index at or above
    2,000 (SPX, SX5E), 0.5 at or above 200, else 0.1 (React ``stepFor``)."""
    if spot >= 2000:
        return 1.0
    if spot >= 200:
        return 0.5
    return 0.1


def listed_strike_step(spot: float) -> float:
    """The index's listed-strike grid, in index points: 25 for an index at or above 2,000
    (SPX, SX5E), else 5 (React ``snapshot.spot >= 2000 ? 25 : 5`` in the exotics views and
    the simulator)."""
    return 25.0 if spot >= 2000 else 5.0


__all__ = [
    "DIV_BOUNDS",
    "RATE_BOUNDS",
    "SPOT_RANGE_FACTORS",
    "T_BOUNDS",
    "Bounds",
    "level_step",
    "listed_strike_step",
]
