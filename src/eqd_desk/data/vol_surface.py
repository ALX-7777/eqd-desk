"""Phase-1 implied-vol surface built from the seed snapshot.

The interface (:meth:`VolSurface.get_vol` of strike and expiry) is the contract later
phases depend on; Phase 4 swaps in a surface that evolves with the simulated spot path
(the leverage effect) without touching the engine. This one is STATIC:

  - the ATM level varies with tenor via linear interpolation of the term structure;
  - the skew shape (a quadratic in log-moneyness, fit near 30 days) is applied at every
    tenor. Holding the skew shape constant across T is a deliberate Phase-1
    simplification: enough to make skew and the cross-greeks visible.

Units: strikes in index points, tenors ``T`` in years, vols as decimals (0.146 = 14.6
vol points).

Dependency direction: this imports the snapshot types only; the engine never imports this
module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache
from itertools import pairwise
from typing import Final, Protocol

from eqd_desk.data.snapshot import MarketSnapshot, load_snapshot

VOL_FLOOR: Final = 0.01
"""Floor so the surface never returns a non-positive vol in the deep wings (1 vol point)."""

T_MIN: Final = 1e-6
"""Tenors below this (in years, ≈ 30 seconds) are read as this value, so a zero or
negative ``T`` still lands on the short end of the term structure."""


class VolSurface(Protocol):
    """An implied-vol surface: the contract every surface (static or simulated) meets."""

    @property
    def spot(self) -> float:
        """Spot the surface is centred on (log-moneyness is measured from it)."""
        ...

    def atm_vol(self, T: float) -> float:
        """ATM implied vol at tenor ``T`` (years), interpolated from the term structure."""
        ...

    def get_vol(self, K: float, T: float) -> float:
        """Implied vol for strike ``K`` at tenor ``T`` (years) via the log-moneyness skew."""
        ...


def _interp_atm(s: MarketSnapshot, tenor: float) -> float:
    """Linear interpolation (with flat extrapolation) of the ATM term structure at
    ``tenor`` (years).

    The knots are used in the order given (the snapshot writes them by increasing tenor).
    With no knots at all, the 30-day ATM anchor is used at every tenor.
    """
    ts = s.term_structure
    if len(ts) == 0:
        return s.atm_vol_30d
    if tenor <= ts[0].t:
        return ts[0].atm_iv
    last = ts[-1]
    if tenor >= last.t:
        return last.atm_iv
    for a, b in pairwise(ts):
        if tenor <= b.t:
            w = (tenor - a.t) / (b.t - a.t)
            return a.atm_iv + w * (b.atm_iv - a.atm_iv)
    return s.atm_vol_30d


@dataclass(frozen=True, slots=True)
class SnapshotVolSurface:
    """The static Phase-1 surface: term-structure ATM level + constant log-moneyness skew.

    σ(K, T) = max(VOL_FLOOR, atm(T) + slope·k + curv·k²),  k = ln(K / spot)

    where atm(T) linearly interpolates the snapshot's ATM term structure (flat beyond the
    first and last knots). Frozen and hashable, so it can be cached.
    """

    snapshot: MarketSnapshot
    """The snapshot the surface is built from (spot, term structure, skew shape)."""

    @property
    def spot(self) -> float:
        """Spot the surface is centred on (the snapshot's spot)."""
        return self.snapshot.spot

    def atm_vol(self, T: float) -> float:
        """ATM implied vol at tenor ``T`` (years), interpolated from the term structure.

        ``T`` is floored at :data:`T_MIN`; the result is floored at :data:`VOL_FLOOR`.
        """
        return max(VOL_FLOOR, _interp_atm(self.snapshot, max(T, T_MIN)))

    def get_vol(self, K: float, T: float) -> float:
        """Implied vol for strike ``K`` (index points) at tenor ``T`` (years).

        σ = max(VOL_FLOOR, atm(T) + slope·k + curv·k²) with k = ln(K / spot). With an equity
        skew (slope < 0) low strikes carry a higher vol than high strikes.

        Raises:
            ValueError: if ``K`` is not a finite positive number (ln(K/S) is undefined).
        """
        if not 0 < K < math.inf:
            raise ValueError(f"vol surface: strike K must be > 0 and finite (got {K})")
        k = math.log(K / self.spot)  # log-moneyness
        atm = _interp_atm(self.snapshot, max(T, T_MIN))
        skew = self.snapshot.skew
        return max(VOL_FLOOR, atm + skew.slope * k + skew.curv * k * k)


def build_surface(s: MarketSnapshot | None = None) -> SnapshotVolSurface:
    """Build a vol surface from a snapshot (default: the committed seed snapshot)."""
    return SnapshotVolSurface(load_snapshot() if s is None else s)


@cache
def default_surface() -> SnapshotVolSurface:
    """Default surface built from the committed seed snapshot (built once, cached)."""
    return build_surface(load_snapshot())
