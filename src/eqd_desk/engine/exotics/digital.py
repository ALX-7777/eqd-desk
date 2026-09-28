"""Binary (digital) options.

Cash-or-nothing pays a fixed cash amount if the option finishes in the money;
asset-or-nothing pays the asset. Closed form under BSM with carry b = r − q::

    d2 = (ln(S/K) + (r − q − σ²/2)·T) / (σ√T)
    cash-or-nothing call  = Q·e^(−rT)·N(d2)
    cash-or-nothing put   = Q·e^(−rT)·N(−d2)
    asset-or-nothing call = S·e^(−qT)·N(d1),   d1 = d2 + σ√T
    asset-or-nothing put  = S·e^(−qT)·N(−d1)

Identity (tested): vanilla call = asset-or-nothing call − K · cash-or-nothing call(Q=1).
The digital is the limit of a tight call spread (see :func:`call_spread_replication`),
which is exactly why it is un-hedgeable at expiry: the replicating spread needs infinite
size as its width → 0. That is the digital's pin risk.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from eqd_desk.engine.bsm import SIGMA_FLOOR, T_FLOOR
from eqd_desk.engine.bsm import price as vanilla_price
from eqd_desk.engine.exotics.numeric_greeks import ExoticGreeks, numeric_greeks
from eqd_desk.engine.math_utils import norm_cdf
from eqd_desk.engine.types import BsmInputs, OptionType


@dataclass(frozen=True, slots=True)
class DigitalInputs:
    """A European digital. Units as :class:`~eqd_desk.engine.types.BsmInputs` (T in
    years; r, q continuously compounded; σ decimal)."""

    S: float
    """Spot (> 0)."""
    K: float
    """Strike (> 0)."""
    T: float
    """Time to expiry in years."""
    r: float
    """Continuously-compounded risk-free rate (decimal)."""
    q: float
    """Continuously-compounded dividend yield (decimal)."""
    sigma: float
    """Volatility (decimal)."""
    type: OptionType
    """Call pays if S_T > K; put pays if S_T < K."""
    cash: float
    """Fixed cash payout Q if the option finishes in the money (cash-or-nothing only)."""


def _d1d2(S: float, K: float, T: float, r: float, q: float, sigma: float) -> tuple[float, float]:
    """(d1, d2) on floored T and σ; d2 is computed first and d1 = d2 + σ√T."""
    if not S > 0:
        raise ValueError(f"digital: spot S must be > 0 (got {S})")
    if not K > 0:
        raise ValueError(f"digital: strike K must be > 0 (got {K})")
    t_eff = max(T, T_FLOOR)
    sig = max(sigma, SIGMA_FLOOR)
    vol_sqrt_t = sig * math.sqrt(t_eff)
    d2 = (math.log(S / K) + (r - q - 0.5 * sig * sig) * t_eff) / vol_sqrt_t
    return d2 + vol_sqrt_t, d2


def cash_or_nothing_price(i: DigitalInputs) -> float:
    """Cash-or-nothing price: pays ``cash`` (Q) if in the money at expiry.

    Call = Q·e^(−rT)·N(d2); put = Q·e^(−rT)·N(−d2). N(d2) is the risk-neutral probability
    of finishing in the money.

    Raises:
        ValueError: if ``S <= 0`` or ``K <= 0``. The TypeScript does not check these, and
            at a zero level it returns the correct LIMIT, not garbage: at ``K = 0`` the call
            is certain to pay, so it is worth Q·e^(−rT), and the put 0; at ``S = 0`` it is
            the mirror image (call 0, put Q·e^(−rT)). Only ``S = K = 0`` or a negative level
            gives NaN there. Python rejects them all, as the vanilla pricer does, because
            ln(S/K) is undefined at a zero or negative level.
    """
    _, d2 = _d1d2(i.S, i.K, i.T, i.r, i.q, i.sigma)
    df = math.exp(-i.r * max(i.T, T_FLOOR))
    return i.cash * df * norm_cdf(d2) if i.type == "call" else i.cash * df * norm_cdf(-d2)


def asset_or_nothing_price(i: DigitalInputs) -> float:
    """Asset-or-nothing price: pays the asset (S_T) if in the money at expiry.

    Call = S·e^(−qT)·N(d1); put = S·e^(−qT)·N(−d1). ``cash`` is ignored.

    Raises:
        ValueError: if ``S <= 0`` or ``K <= 0``. The TypeScript does not check these, and
            at a zero level it returns the correct LIMIT, not garbage: at ``K = 0`` the call
            always delivers the asset, so it is worth S·e^(−qT) (the prepaid forward), and
            the put 0; at ``S = 0`` both are 0. Only ``S = K = 0`` or a negative level gives
            NaN there. Python rejects them all, as the vanilla pricer does, because ln(S/K)
            is undefined at a zero or negative level.
    """
    d1, _ = _d1d2(i.S, i.K, i.T, i.r, i.q, i.sigma)
    dfq = math.exp(-i.q * max(i.T, T_FLOOR))
    return i.S * dfq * norm_cdf(d1) if i.type == "call" else i.S * dfq * norm_cdf(-d1)


def digital_greeks(i: DigitalInputs) -> ExoticGreeks:
    """Greeks of the cash-or-nothing digital, by bumping (note the delta/gamma spike near
    the strike as expiry approaches)."""

    def px(S: float, sigma: float, T: float, r: float) -> float:
        return cash_or_nothing_price(replace(i, S=S, sigma=sigma, T=T, r=r))

    return numeric_greeks(px, i.S, i.sigma, i.T, i.r)


def call_spread_replication(i: DigitalInputs, width: float) -> float:
    """Price of the tight CALL-SPREAD that replicates a cash-or-nothing digital with the
    given spread width Δ (strike units).

    For a call: long (Q/Δ) calls at K − Δ/2 and short (Q/Δ) calls at K + Δ/2. For a put:
    long (Q/Δ) puts at K + Δ/2 and short (Q/Δ) puts at K − Δ/2. As Δ → 0 this converges to
    the digital price; the (Q/Δ) size is the un-hedgeable bit at expiry. Widths below
    1e-9 are floored to 1e-9.

    Raises:
        ValueError: if a leg strike K ± Δ/2 is not positive (via the vanilla pricer).
    """
    w = max(width, 1e-9)
    n = i.cash / w

    def leg(K: float, option_type: OptionType) -> float:
        return vanilla_price(BsmInputs(S=i.S, K=K, T=i.T, r=i.r, q=i.q, sigma=i.sigma), option_type)

    if i.type == "call":
        lo = leg(i.K - w / 2, "call")
        hi = leg(i.K + w / 2, "call")
        return n * (lo - hi)
    # put digital ≈ long (Q/Δ) puts at K+Δ/2, short (Q/Δ) puts at K−Δ/2
    hi = leg(i.K + w / 2, "put")
    lo = leg(i.K - w / 2, "put")
    return n * (hi - lo)
