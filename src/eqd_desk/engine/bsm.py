"""Black–Scholes–Merton pricing for vanilla European options with a continuous dividend
yield ``q``, implemented from scratch::

    d1 = (ln(S/K) + (r − q + σ²/2)·T) / (σ·√T)
    d2 = d1 − σ·√T
    Call = S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2)
    Put  = K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1)

All greeks (see :mod:`eqd_desk.engine.greeks`) are derived from the same :func:`bsm_core`
intermediates, so the pricer and the greeks always share one consistent set of d1/d2 and
discount factors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from eqd_desk.engine.math_utils import norm_cdf
from eqd_desk.engine.types import BsmInputs, OptionType

T_FLOOR = 1e-8
"""Lower bound applied to T (in years) so the smooth formulas stay finite as an option
approaches expiry. ~1e-8 yr ≈ 0.3 ms: far below any meaningful trading granularity, so it
never perturbs realistic inputs; it only tames the 1/√T singularity at the instant of
expiry."""

SIGMA_FLOOR = 1e-8
"""Lower bound applied to σ so we never divide by σ·√T. 1e-8 is negligible vs any real
vol; the floored result tends to the discounted-intrinsic limit."""


@dataclass(frozen=True, slots=True)
class BsmCore:
    """Shared intermediates computed once and reused by the pricer and every greek."""

    d1: float
    """d1 of the BSM formula."""
    d2: float
    """d2 = d1 − σ√T."""
    sqrt_t: float
    """√T (using the floored T)."""
    vol_sqrt_t: float
    """σ·√T (using floored σ and T): the single guarded denominator."""
    df_r: float
    """Riskless discount factor e^(−rT)."""
    df_q: float
    """Carry / dividend discount factor e^(−qT)."""
    t_eff: float
    """Effective T after flooring (years)."""
    sigma_eff: float
    """Effective σ after flooring (decimal)."""


def validate_inputs(i: BsmInputs) -> None:
    """Validate inputs.

    Non-positive S/K make ln(S/K) undefined, so these are hard errors (programmer or
    un-validated-UI bugs) rather than silently-clamped values. The ``not (x > 0)`` form
    also rejects NaN.

    Raises:
        ValueError: on any out-of-domain input.
    """
    if not i.S > 0:
        raise ValueError(f"BSM: spot S must be > 0 (got {i.S})")
    if not i.K > 0:
        raise ValueError(f"BSM: strike K must be > 0 (got {i.K})")
    if not i.T >= 0:
        raise ValueError(f"BSM: time T must be >= 0 (got {i.T})")
    if not i.sigma >= 0:
        raise ValueError(f"BSM: vol sigma must be >= 0 (got {i.sigma})")
    if not math.isfinite(i.r):
        raise ValueError(f"BSM: rate r must be finite (got {i.r})")
    if not math.isfinite(i.q):
        raise ValueError(f"BSM: dividend q must be finite (got {i.q})")


def bsm_core(i: BsmInputs) -> BsmCore:
    """Compute the shared BSM intermediates (d1, d2, discount factors, guarded
    denominators). Floors T and σ to keep everything finite at the boundaries."""
    validate_inputs(i)
    t_eff = max(i.T, T_FLOOR)
    sigma_eff = max(i.sigma, SIGMA_FLOOR)
    sqrt_t = math.sqrt(t_eff)
    vol_sqrt_t = sigma_eff * sqrt_t
    df_r = math.exp(-i.r * t_eff)
    df_q = math.exp(-i.q * t_eff)
    d1 = (math.log(i.S / i.K) + (i.r - i.q + 0.5 * sigma_eff * sigma_eff) * t_eff) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return BsmCore(
        d1=d1,
        d2=d2,
        sqrt_t=sqrt_t,
        vol_sqrt_t=vol_sqrt_t,
        df_r=df_r,
        df_q=df_q,
        t_eff=t_eff,
        sigma_eff=sigma_eff,
    )


def call_price(i: BsmInputs) -> float:
    """Call price: S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2)."""
    c = bsm_core(i)
    return i.S * c.df_q * norm_cdf(c.d1) - i.K * c.df_r * norm_cdf(c.d2)


def put_price(i: BsmInputs) -> float:
    """Put price: K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1)."""
    c = bsm_core(i)
    return i.K * c.df_r * norm_cdf(-c.d2) - i.S * c.df_q * norm_cdf(-c.d1)


def price(i: BsmInputs, option_type: OptionType) -> float:
    """Price dispatch by option type."""
    return call_price(i) if option_type == "call" else put_price(i)


def forward(i: BsmInputs) -> float:
    """Forward price F = S·e^((r−q)T).

    The discounted intrinsic on the forward is the σ→0 limit of the BSM price; useful for
    edge-case tests and intuition.
    """
    t_eff = max(i.T, T_FLOOR)
    return i.S * math.exp((i.r - i.q) * t_eff)
