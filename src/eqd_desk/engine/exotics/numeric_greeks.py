"""Shared numeric (bump) greeks for the exotics.

The spec allows exotic greeks "by bumping"; this is the one place we do it, so every
exotic just supplies a price function of (S, σ, T, r) with its other parameters captured.

Returned greeks are in the SAME desk-reporting units as the vanilla engine::

    delta, gamma  per $1 of spot
    vega          per 1 vol point   (raw ∂/∂σ ÷ 100)
    theta         per calendar day  (−∂/∂T ÷ 365)
    rho           per 1 rate point  (raw ∂/∂r ÷ 100)

For Monte-Carlo pricers, pass a price function that reuses a FIXED seed so the same random
draws are used across bumps (common random numbers); otherwise the sampling noise swamps
the finite differences.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, fields

PriceFn = Callable[[float, float, float, float], float]
"""Price as a function of the four bumped market variables ``(S, sigma, T, r)``, with every
other parameter of the product captured (e.g. by a lambda)."""


@dataclass(frozen=True, slots=True)
class ExoticGreeks:
    """Price plus the first-order greeks and gamma of an exotic, in desk units."""

    price: float
    """Premium (same currency as the underlying)."""
    delta: float
    """∂V/∂S, per $1 of spot."""
    gamma: float
    """∂²V/∂S², per $1 of spot (of delta)."""
    vega: float
    """∂V/∂σ per 1 vol point (raw ÷ 100)."""
    theta: float
    """∂V/∂t = −∂V/∂T per calendar day (raw ÷ 365)."""
    rho: float
    """∂V/∂r per 1 rate point (raw ÷ 100)."""

    def as_dict(self) -> dict[str, float]:
        """Field name → value, in declaration order (price first)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}


H_S_REL = 1e-4
"""Spot bump, RELATIVE to spot (h_S = 1e-4·S)."""
H_SIGMA = 1e-4
"""Vol bump (absolute, decimal vol: 0.01 vol point)."""
H_T = 1e-5
"""Time bump in years (≈ 5 minutes), capped at T/2 so we never bump below expiry."""
H_R = 1e-6
"""Rate bump (absolute, decimal rate: 0.0001 rate point)."""


def numeric_greeks(price: PriceFn, S: float, sigma: float, T: float, r: float) -> ExoticGreeks:
    """Central-difference greeks of ``price`` around ``(S, sigma, T, r)``::

        delta = [P(S+h) − P(S−h)] / 2h                  h = 1e-4·S
        gamma = [P(S+h) − 2·P(S) + P(S−h)] / h²
        vega  = [P(σ+h) − P(σ−h)] / 2h / 100             h = 1e-4
        theta = −[P(T+h) − P(T−h)] / 2h / 365            h = min(1e-5, T/2)
        rho   = [P(r+h) − P(r−h)] / 2h / 100             h = 1e-6

    Nine price evaluations (the spot-bumped prices are shared by delta and gamma; the
    TypeScript evaluates them twice, which gives identical numbers for any deterministic
    or fixed-seed pricer).

    At ``T = 0`` there is no room to bump time, so theta is NaN (the TypeScript's 0/0).

    Raises:
        ValueError: if ``S <= 0`` (the spot bump is relative to S).
    """
    if not S > 0:
        raise ValueError(f"numeric_greeks: spot S must be > 0 (got {S})")
    h_s = H_S_REL * S

    p0 = price(S, sigma, T, r)
    p_up = price(S + h_s, sigma, T, r)
    p_dn = price(S - h_s, sigma, T, r)
    delta = (p_up - p_dn) / (2 * h_s)
    gamma = (p_up - 2 * p0 + p_dn) / (h_s * h_s)

    vega_raw = (price(S, sigma + H_SIGMA, T, r) - price(S, sigma - H_SIGMA, T, r)) / (2 * H_SIGMA)

    # theta = ∂/∂t = −∂/∂T; guard T so we never bump below ~0.
    h_t = min(H_T, T / 2)
    theta_raw = (
        -(price(S, sigma, T + h_t, r) - price(S, sigma, T - h_t, r)) / (2 * h_t)
        if h_t != 0
        else math.nan
    )

    rho_raw = (price(S, sigma, T, r + H_R) - price(S, sigma, T, r - H_R)) / (2 * H_R)

    return ExoticGreeks(
        price=p0,
        delta=delta,
        gamma=gamma,
        vega=vega_raw / 100,
        theta=theta_raw / 365,
        rho=rho_raw / 100,
    )
