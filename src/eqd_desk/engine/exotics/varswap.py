"""Variance swap: fair variance via the model-free replication of the log contract by a
strip of OTM options weighted 1/K² (Demeterfi–Derman–Kamal–Zou).

Splitting the strip at the forward F removes the boundary term::

    K_var = (2·e^(rT)/T) · [ Σ_{K<F} (ΔK/K²)·P(K) + Σ_{K≥F} (ΔK/K²)·C(K) ]

The fair variance equals −(2/T)·E^Q[ln(S_T/F)] (the log contract); under GBM that is
exactly σ², so a flat surface returns σ² (validated in tests). With a real downward skew
the strip is overweight low-strike (high-vol) puts, so the fair vol prints ABOVE the ATM
vol: the convexity premium that makes VIX (a 30-day variance swap on the S&P) trade rich
to ATM.

Pure: the surface is supplied as a ``vol_for(K)`` callback so the engine keeps no data
dependency.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from eqd_desk.engine.bsm import price as vanilla_price
from eqd_desk.engine.types import BsmInputs, OptionType

VolFn = Callable[[float], float]
"""Implied vol (decimal) for a given strike: the smile at the swap's maturity."""


@dataclass(frozen=True, slots=True)
class VarSwapInputs:
    """A variance swap to price by static replication.

    Units: ``T`` in years (> 0); ``r``, ``q`` continuously compounded; vols decimal. The
    fair variance is ANNUALISED (e.g. 0.04 = 20 vol squared).
    """

    S: float
    """Spot (> 0)."""
    T: float
    """Maturity in years (> 0)."""
    r: float
    """Continuously-compounded risk-free rate (decimal)."""
    q: float
    """Continuously-compounded dividend yield (decimal)."""
    vol_for: VolFn
    """Implied vol for a given strike (the smile), e.g. ``lambda K: surface.get_vol(K, T)``."""
    lo_mult: float = 0.3
    """Low strike bound as a multiple of the forward (default 0.3×F)."""
    hi_mult: float = 3.0
    """High strike bound as a multiple of the forward (default 3×F)."""
    n_strikes: int = 400
    """Number of equally-spaced strikes in the replication strip (default 400, >= 2)."""


@dataclass(frozen=True, slots=True)
class StripPoint:
    """One strike of the replication strip."""

    K: float
    """Strike."""
    weight: float
    """Replication weight ΔK / K²."""
    option_price: float
    """OTM option price used at this strike (put below the forward, call at/above it)."""
    type: OptionType
    """Which OTM option is used here."""
    contribution: float
    """Weighted contribution to the fair variance (before the 2·e^(rT)/T factor)."""


@dataclass(frozen=True, slots=True)
class VarSwapResult:
    """Fair variance and the strip that produced it."""

    fair_variance: float
    """Annualised fair variance K_var."""
    fair_vol: float
    """Fair volatility = √(fair variance) (floored at 0 under the root)."""
    forward: float
    """Forward F = S·e^((r−q)T)."""
    atm_vol: float
    """ATM implied vol (at the forward), for comparison."""
    strip: tuple[StripPoint, ...]
    """The replication strip (for plotting the 1/K² contributions)."""


def price_variance_swap(i: VarSwapInputs) -> VarSwapResult:
    """Fair variance of a variance swap by the 1/K²-weighted OTM strip (see module doc).

    Strikes run evenly from ``lo_mult·F`` to ``hi_mult·F`` (``n_strikes`` points, spacing
    ΔK); non-positive strikes are skipped. Each strike prices an OTM vanilla at the smile
    vol ``vol_for(K)``: a put for K < F, a call for K ≥ F.

    Raises:
        ValueError: if ``T <= 0`` or ``n_strikes < 2``, or via the vanilla pricer on a bad
            input. The TypeScript does not check T or n_strikes itself. At ``T = 0`` it
            returns NaN (every OTM option is worth 0 at expiry, and 2/T · 0 = ∞·0). At
            ``T < 0``, or ``n_strikes = 1`` (ΔK = (hi − lo)/0 makes the strike NaN), its
            vanilla pricer throws. At ``n_strikes <= 0`` it silently returns a fair
            variance of 0 with an empty strip.
    """
    if not i.T > 0:
        raise ValueError(f"varswap: maturity T must be > 0 (got {i.T})")
    if i.n_strikes < 2:
        raise ValueError(f"varswap: n_strikes must be >= 2 (got {i.n_strikes})")
    F = i.S * math.exp((i.r - i.q) * i.T)
    lo = i.lo_mult * F
    hi = i.hi_mult * F
    n = i.n_strikes
    dK = (hi - lo) / (n - 1)

    strip: list[StripPoint] = []
    total = 0.0
    for j in range(n):
        K = lo + j * dK
        if K <= 0:
            continue
        option_type: OptionType = "put" if K < F else "call"
        sigma = i.vol_for(K)
        option_price = vanilla_price(
            BsmInputs(S=i.S, K=K, T=i.T, r=i.r, q=i.q, sigma=sigma), option_type
        )
        weight = dK / (K * K)
        contribution = weight * option_price
        total += contribution
        strip.append(StripPoint(K, weight, option_price, option_type, contribution))

    fair_variance = ((2 * math.exp(i.r * i.T)) / i.T) * total
    return VarSwapResult(
        fair_variance=fair_variance,
        fair_vol=math.sqrt(max(fair_variance, 0.0)),
        forward=F,
        atm_vol=i.vol_for(F),
        strip=tuple(strip),
    )
