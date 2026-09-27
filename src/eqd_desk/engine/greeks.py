"""Analytic greeks for vanilla European options under BSM with continuous dividend yield
``q``.

Every function is the exact partial derivative of the pricer in
:mod:`eqd_desk.engine.bsm`, in RAW units (see :mod:`eqd_desk.engine.reporting` for unit
scaling).

Sign convention for the time greeks (theta, charm, color): we report ∂/∂t = −∂/∂T, i.e.
the change as CALENDAR TIME advances and time-to-expiry shrinks. A long option therefore
has negative theta in normal conditions.

Each greek is validated against a central finite-difference bump of the pricer in
``tests/engine/test_greeks.py``. That cross-check, not the algebra below, is the source
of truth for the sign conventions.

Symmetric greeks (gamma, vega, vanna, volga, speed, color) are identical for calls and
puts, a consequence of put-call parity: its extra term is linear in S and constant in
σ/T, so its higher derivatives vanish. Those functions take no ``option_type`` argument
by design.
"""

from __future__ import annotations

from eqd_desk.engine.bsm import BsmCore, bsm_core
from eqd_desk.engine.math_utils import norm_cdf, norm_pdf
from eqd_desk.engine.types import BsmInputs, OptionType, RawGreeks

# --- core-based implementations (compute bsm_core once, reuse everywhere) -------------


def _price(c: BsmCore, i: BsmInputs, option_type: OptionType) -> float:
    if option_type == "call":
        return i.S * c.df_q * norm_cdf(c.d1) - i.K * c.df_r * norm_cdf(c.d2)
    return i.K * c.df_r * norm_cdf(-c.d2) - i.S * c.df_q * norm_cdf(-c.d1)


def _delta(c: BsmCore, option_type: OptionType) -> float:
    """Δ = ∂V/∂S. Call: e^(−qT)·N(d1). Put: −e^(−qT)·N(−d1)."""
    return c.df_q * norm_cdf(c.d1) if option_type == "call" else -c.df_q * norm_cdf(-c.d1)


def _gamma(c: BsmCore, S: float) -> float:
    """Γ = ∂²V/∂S² = e^(−qT)·φ(d1)/(S·σ·√T). Same for call and put; always ≥ 0."""
    return (c.df_q * norm_pdf(c.d1)) / (S * c.vol_sqrt_t)


def _vega(c: BsmCore, S: float) -> float:
    """vega = ∂V/∂σ = S·e^(−qT)·φ(d1)·√T (per 1.00 of vol). Same call/put; ≥ 0."""
    return S * c.df_q * norm_pdf(c.d1) * c.sqrt_t


def _theta(c: BsmCore, i: BsmInputs, option_type: OptionType) -> float:
    """Θ = ∂V/∂t = −∂V/∂T (per year).

    Three terms: the always-negative time-value bleed (same for call/put), a
    dividend-carry term, and a discount term.
    """
    bleed = -(i.S * c.df_q * norm_pdf(c.d1) * c.sigma_eff) / (2.0 * c.sqrt_t)
    if option_type == "call":
        return bleed + i.q * i.S * c.df_q * norm_cdf(c.d1) - i.r * i.K * c.df_r * norm_cdf(c.d2)
    return bleed - i.q * i.S * c.df_q * norm_cdf(-c.d1) + i.r * i.K * c.df_r * norm_cdf(-c.d2)


def _rho(c: BsmCore, i: BsmInputs, option_type: OptionType) -> float:
    """ρ = ∂V/∂r (per 1.00 of rate). Call: K·T·e^(−rT)·N(d2). Put: −K·T·e^(−rT)·N(−d2)."""
    if option_type == "call":
        return i.K * c.t_eff * c.df_r * norm_cdf(c.d2)
    return -i.K * c.t_eff * c.df_r * norm_cdf(-c.d2)


def _vanna(c: BsmCore) -> float:
    """vanna = ∂Δ/∂σ = ∂vega/∂S = −e^(−qT)·φ(d1)·d2/σ. Same call/put."""
    return (-c.df_q * norm_pdf(c.d1) * c.d2) / c.sigma_eff


def _volga(c: BsmCore, S: float) -> float:
    """volga (vomma) = ∂vega/∂σ = vega·d1·d2/σ. Same call/put."""
    return (_vega(c, S) * c.d1 * c.d2) / c.sigma_eff


def _charm(c: BsmCore, i: BsmInputs, option_type: OptionType) -> float:
    """charm = ∂Δ/∂t = −∂Δ/∂T (delta decay, per year).

    Building block: ∂Δ_call/∂T = −q·e^(−qT)·N(d1) + ``common``, where
    common = e^(−qT)·φ(d1)·[2(r−q)T − d2·σ√T] / (2T·σ√T) = e^(−qT)·φ(d1)·∂d1/∂T.
    Negating for the time-decay convention gives the forms below (the dividend term flips
    sign between call and put; ``common`` is shared). Validated by finite differences.
    """
    common = (c.df_q * norm_pdf(c.d1) * (2.0 * (i.r - i.q) * c.t_eff - c.d2 * c.vol_sqrt_t)) / (
        2.0 * c.t_eff * c.vol_sqrt_t
    )
    if option_type == "call":
        return i.q * c.df_q * norm_cdf(c.d1) - common
    return -i.q * c.df_q * norm_cdf(-c.d1) - common


def _speed(c: BsmCore, S: float) -> float:
    """speed = ∂Γ/∂S = ∂³V/∂S³ = −(Γ/S)·(d1/(σ√T) + 1). Same call/put."""
    return (-_gamma(c, S) / S) * (c.d1 / c.vol_sqrt_t + 1.0)


def _color(c: BsmCore, i: BsmInputs) -> float:
    """color = ∂Γ/∂t = −∂Γ/∂T (gamma decay, per year)::

        = e^(−qT)·φ(d1)/(2·S·T·σ√T) · [ 2qT + 1 + (2(r−q)T − d2·σ√T)·d1/(σ√T) ]

    Same for call and put. The sign is already that of ∂/∂t: do not negate again.
    """
    bracket = (
        2.0 * i.q * c.t_eff
        + 1.0
        + ((2.0 * (i.r - i.q) * c.t_eff - c.d2 * c.vol_sqrt_t) * c.d1) / c.vol_sqrt_t
    )
    return ((c.df_q * norm_pdf(c.d1)) / (2.0 * i.S * c.t_eff * c.vol_sqrt_t)) * bracket


# --- public single-greek API ------------------------------------------------------------


def delta(i: BsmInputs, option_type: OptionType) -> float:
    """Δ = ∂V/∂S (per $1 of spot)."""
    return _delta(bsm_core(i), option_type)


def gamma(i: BsmInputs) -> float:
    """Γ = ∂²V/∂S² (per $1 of spot, of delta)."""
    return _gamma(bsm_core(i), i.S)


def vega(i: BsmInputs) -> float:
    """vega = ∂V/∂σ (per 1.00 of vol)."""
    return _vega(bsm_core(i), i.S)


def theta(i: BsmInputs, option_type: OptionType) -> float:
    """Θ = ∂V/∂t = −∂V/∂T (per year of calendar time)."""
    return _theta(bsm_core(i), i, option_type)


def rho(i: BsmInputs, option_type: OptionType) -> float:
    """ρ = ∂V/∂r (per 1.00 of rate)."""
    return _rho(bsm_core(i), i, option_type)


def vanna(i: BsmInputs) -> float:
    """vanna = ∂Δ/∂σ = ∂vega/∂S (per 1.00 of vol)."""
    return _vanna(bsm_core(i))


def volga(i: BsmInputs) -> float:
    """volga = ∂vega/∂σ (per 1.00 of vol)."""
    return _volga(bsm_core(i), i.S)


def charm(i: BsmInputs, option_type: OptionType) -> float:
    """charm = ∂Δ/∂t = −∂Δ/∂T (per year)."""
    return _charm(bsm_core(i), i, option_type)


def speed(i: BsmInputs) -> float:
    """speed = ∂Γ/∂S (per $1 of spot)."""
    return _speed(bsm_core(i), i.S)


def color(i: BsmInputs) -> float:
    """color = ∂Γ/∂t = −∂Γ/∂T (per year)."""
    return _color(bsm_core(i), i)


def raw_greeks(i: BsmInputs, option_type: OptionType) -> RawGreeks:
    """Compute price + every greek in one pass (one :func:`bsm_core` evaluation).

    This is what the UI calls on each input change. Returns RAW units; pass the result
    through :func:`eqd_desk.engine.reporting.to_reported` to get desk units.
    """
    c = bsm_core(i)
    return RawGreeks(
        price=_price(c, i, option_type),
        delta=_delta(c, option_type),
        gamma=_gamma(c, i.S),
        vega=_vega(c, i.S),
        theta=_theta(c, i, option_type),
        rho=_rho(c, i, option_type),
        vanna=_vanna(c),
        volga=_volga(c, i.S),
        charm=_charm(c, i, option_type),
        speed=_speed(c, i.S),
        color=_color(c, i),
    )
