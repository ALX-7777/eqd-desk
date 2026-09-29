"""Variance swap: fair variance via the model-free replication of the log contract by a
strip of OTM options weighted 1/K² (Demeterfi–Derman–Kamal–Zou).

Splitting the strip at the forward F removes the boundary term::

    K_var = (2·e^(rT)/T) · ∫ Q(K)/K² dK      Q(K) = P(K) for K < F, C(K) for K ≥ F

The fair variance equals −(2/T)·E^Q[ln(S_T/F)] (the log contract); under GBM that is
exactly σ², so a flat surface returns σ². With a real downward skew the strip is overweight
low-strike (high-vol) puts, so the fair vol prints ABOVE the ATM vol: the convexity premium
that makes VIX (a 30-day variance swap on the S&P) trade rich to ATM.

Discrete strip. On an evenly spaced strike grid (spacing ΔK) the integral over the strip
becomes a trapezoid-rule sum (weight ΔK/K², halved at the two end strikes so the sum covers
exactly lo…hi), plus one closed-form correction for the kink at the forward::

    K_var ≈ (2·e^(rT)/T) · Σ wᵢ·Q(Kᵢ)  −  (ΔK/F)²·B₂(θ)/T      wᵢ = ΔK/Kᵢ² (½ at the ends)
    θ = (F − K₀)/ΔK ∈ [0, 1)     K₀ = the grid strike at or just below F
    B₂(θ) = θ² − θ + 1/6         (the second Bernoulli polynomial)

Why: Q(K)/K² is smooth except at F, where the strip switches from puts to calls and its
slope drops by e^(−rT)/F² (put–call parity: C − P = e^(−rT)·(F − K)). An even-grid sum
integrates the smooth part almost exactly but mis-counts that kink by (ΔK²/2)·B₂(θ)·e^(−rT)/F²
(the Euler–Maclaurin term for a kink θ of the way between two strikes). Left in, the error
in variance runs from −(ΔK/F)²/(12T) to +(ΔK/F)²/(6T): negligible at a year, but at 7 days
and 5% vol on the default strip it prints 4.80% for a flat 5% smile. The CBOE VIX formula's
−(1/T)·(F/K₀ − 1)² term (with the put–call average at K₀) removes the θ-dependent part of
the same error; the constant 1/6 is the part it keeps, negligible at listed SPX strike
spacing but not on a 400-strike grid from 0.3F to 3F.

Truncation. Strikes outside ``lo_mult·F … hi_mult·F`` are simply absent, which drops the
tails: it matters only at long tenors and high vol (a flat 60% smile at 1 year prices ≈59.5%
on the default 0.3F–3F strip). A wider strip is not automatically better with a parametric
smile whose wings grow without bound (a quadratic in log-moneyness).

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
    """Replication weight ΔK / K² (half that at the strip's first and last strike)."""
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
    grid_correction: float
    """The forward-kink correction −(ΔK/F)²·B₂(θ)/T already included in
    :attr:`fair_variance` (annualised variance; 0 when F lies outside the strip)."""
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
    vol ``vol_for(K)``: a put for K < F, a call for K ≥ F, weighted ΔK/K² (trapezoid rule:
    half at the first and last grid strike). When F lies inside the strip (``lo ≤ F < hi``)
    the forward-kink correction −(ΔK/F)²·B₂(θ)/T is added.

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
        end = j == 0 or j == n - 1  # trapezoid rule: the strip's ends get half a slice
        weight = (0.5 * dK if end else dK) / (K * K)
        contribution = weight * option_price
        total += contribution
        strip.append(StripPoint(K, weight, option_price, option_type, contribution))

    # Forward-kink correction (module doc): θ = where F sits between its two grid strikes.
    grid_correction = 0.0
    if lo <= F < hi:
        theta = (F - lo) / dK
        theta -= math.floor(theta)
        g = dK / F
        grid_correction = -(g * g) * (theta * theta - theta + 1 / 6) / i.T

    fair_variance = ((2 * math.exp(i.r * i.T)) / i.T) * total + grid_correction
    return VarSwapResult(
        fair_variance=fair_variance,
        fair_vol=math.sqrt(max(fair_variance, 0.0)),
        grid_correction=grid_correction,
        forward=F,
        atm_vol=i.vol_for(F),
        strip=tuple(strip),
    )
