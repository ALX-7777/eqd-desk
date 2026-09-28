"""Single-barrier European options (continuously monitored), Reiner–Rubinstein / Merton
closed forms, zero rebate. Carry b = r − q.

Building blocks A, B, C, D (Haug) with φ = +1 call / −1 put and η = +1 down / −1 up. A is
exactly the vanilla price, so knock-in + knock-out = vanilla holds by construction; the MC
cross-check (in tests) validates the A/B/C/D formulas and the in/out table itself.

Teaching point: a knock-out's value (and its delta) collapse to zero AT the barrier, so
gamma explodes there. The barrier is where the hedge is hardest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal, NamedTuple

from eqd_desk.engine.bsm import SIGMA_FLOOR, T_FLOOR
from eqd_desk.engine.bsm import price as vanilla_price
from eqd_desk.engine.exotics.numeric_greeks import ExoticGreeks, numeric_greeks
from eqd_desk.engine.math_utils import norm_cdf
from eqd_desk.engine.types import BsmInputs, OptionType

BarrierKind = Literal["down-in", "down-out", "up-in", "up-out"]
"""Barrier direction (down: H below spot; up: H above spot) and effect (in: the option only
comes alive if H is touched; out: it dies if H is touched)."""

BARRIER_KINDS: tuple[BarrierKind, ...] = ("down-in", "down-out", "up-in", "up-out")


@dataclass(frozen=True, slots=True)
class BarrierInputs:
    """A single-barrier European option. Units as :class:`~eqd_desk.engine.types.BsmInputs`
    (T in years; r, q continuously compounded; σ decimal)."""

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
    """Call or put payoff at expiry (if alive)."""
    H: float
    """Barrier level H (> 0), continuously monitored."""
    kind: BarrierKind
    """Down/up, in/out."""


class _Abcd(NamedTuple):
    """Haug's four building blocks of the single-barrier closed forms."""

    A: float
    B: float
    C: float
    D: float


def _pow(base: float, exponent: float) -> float:
    """``base ** exponent`` for ``base > 0``, returning +inf on overflow like JS
    ``Math.pow`` (Python raises OverflowError instead).

    Only reachable at degenerate vols (σ → floor makes μ = (b − σ²/2)/σ² astronomically
    large); the barrier formula then yields NaN, exactly as the TypeScript does.
    """
    try:
        return math.pow(base, exponent)
    except OverflowError:
        return math.inf


def _abcd(
    S: float,
    K: float,
    H: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    phi: float,
    eta: float,
) -> _Abcd:
    """Haug's building blocks, with μ = (b − σ²/2)/σ² and σ√T on floored σ and T::

        x1 = ln(S/K)/σ√T + (1+μ)σ√T         x2 = ln(S/H)/σ√T + (1+μ)σ√T
        y1 = ln(H²/(S·K))/σ√T + (1+μ)σ√T    y2 = ln(H/S)/σ√T + (1+μ)σ√T

        A = φ·S·e^((b−r)T)·N(φ·x1) − φ·K·e^(−rT)·N(φ·x1 − φ·σ√T)
        B = φ·S·e^((b−r)T)·N(φ·x2) − φ·K·e^(−rT)·N(φ·x2 − φ·σ√T)
        C = φ·S·e^((b−r)T)·(H/S)^(2(μ+1))·N(η·y1)
            − φ·K·e^(−rT)·(H/S)^(2μ)·N(η·y1 − η·σ√T)
        D = φ·S·e^((b−r)T)·(H/S)^(2(μ+1))·N(η·y2)
            − φ·K·e^(−rT)·(H/S)^(2μ)·N(η·y2 − η·σ√T)

    φ = +1 call / −1 put, η = +1 down / −1 up. A is exactly the vanilla BSM price.
    """
    b = r - q
    sig = max(sigma, SIGMA_FLOOR)
    t_eff = max(T, T_FLOOR)
    sig_t = sig * math.sqrt(t_eff)
    mu = (b - 0.5 * sig * sig) / (sig * sig)
    x1 = math.log(S / K) / sig_t + (1 + mu) * sig_t
    x2 = math.log(S / H) / sig_t + (1 + mu) * sig_t
    y1 = math.log((H * H) / (S * K)) / sig_t + (1 + mu) * sig_t
    y2 = math.log(H / S) / sig_t + (1 + mu) * sig_t
    ebr_t = math.exp((b - r) * t_eff)
    er_t = math.exp(-r * t_eff)
    hs_p = _pow(H / S, 2 * (mu + 1))
    hs_m = _pow(H / S, 2 * mu)

    A = phi * S * ebr_t * norm_cdf(phi * x1) - phi * K * er_t * norm_cdf(phi * x1 - phi * sig_t)
    B = phi * S * ebr_t * norm_cdf(phi * x2) - phi * K * er_t * norm_cdf(phi * x2 - phi * sig_t)
    C = phi * S * ebr_t * hs_p * norm_cdf(eta * y1) - phi * K * er_t * hs_m * norm_cdf(
        eta * y1 - eta * sig_t
    )
    D = phi * S * ebr_t * hs_p * norm_cdf(eta * y2) - phi * K * er_t * hs_m * norm_cdf(
        eta * y2 - eta * sig_t
    )
    return _Abcd(A, B, C, D)


def barrier_price(i: BarrierInputs) -> float:
    """Price of a single-barrier European option (continuous monitoring, zero rebate).

    If the barrier is already breached (spot at or beyond it), a knock-out is dead (0) and
    a knock-in is simply the vanilla from here. Otherwise the in/out × up/down × call/put
    table below combines Haug's A, B, C, D (the K > H and K ≤ H rows differ because the
    barrier either does or does not cut through the in-the-money region)::

                      call K>H     call K≤H         put K>H          put K≤H
        down-in       C            A − B + D        B − C + D        A
        up-in         A            B − C + D        A − B + D        C
        down-out      A − C        B − D            A − B + C − D    0
        up-out        0            A − B + C − D    B − D            A − C

    Raises:
        ValueError: if ``H <= 0`` (as the TypeScript), or ``S <= 0`` / ``K <= 0``. The
            TypeScript does not check S or K, and what it returns depends on the branch:

            - ``K = 0``: the correct finite limit (a zero-strike call is the asset, so
              knock-in + knock-out = S·e^(−qT), the prepaid forward; puts are 0).
            - ``S = 0``, down barrier: counted as breached, so a knock-out returns 0 and a
              knock-in throws from the vanilla pricer.
            - ``S = 0``, up barrier: NaN (0·∞ in the (H/S)^p terms), except a call with
              K > H, which returns 0.
            - negative S or K: NaN, 0, a throw or a meaningless finite number.

            Python rejects them all, as the vanilla pricer does, because the logs
            ln(S/K), ln(S/H) are undefined at a zero or negative level.
    """
    if not i.H > 0:
        raise ValueError(f"barrier: H must be > 0 (got {i.H})")
    if not i.S > 0:
        raise ValueError(f"barrier: spot S must be > 0 (got {i.S})")
    if not i.K > 0:
        raise ValueError(f"barrier: strike K must be > 0 (got {i.K})")
    is_call = i.type == "call"
    is_down = i.kind in ("down-in", "down-out")
    is_out = i.kind in ("down-out", "up-out")

    # Already breached? Knock-out is dead; knock-in is just the vanilla from here.
    breached = i.S <= i.H if is_down else i.S >= i.H
    if breached:
        if is_out:
            return 0.0
        return vanilla_price(BsmInputs(S=i.S, K=i.K, T=i.T, r=i.r, q=i.q, sigma=i.sigma), i.type)

    phi = 1.0 if is_call else -1.0
    eta = 1.0 if is_down else -1.0
    A, B, C, D = _abcd(i.S, i.K, i.H, i.T, i.r, i.q, i.sigma, phi, eta)
    k_gt_h = i.K > i.H

    match i.kind:
        case "down-in":
            v = (C if k_gt_h else A - B + D) if is_call else (B - C + D if k_gt_h else A)
        case "up-in":
            v = (A if k_gt_h else B - C + D) if is_call else (A - B + D if k_gt_h else C)
        case "down-out":
            v = (A - C if k_gt_h else B - D) if is_call else (A - B + C - D if k_gt_h else 0.0)
        case "up-out":
            v = (0.0 if k_gt_h else A - B + C - D) if is_call else (B - D if k_gt_h else A - C)
    # Clamp tiny negative numerical noise. max(v, 0.0) keeps NaN, like JS Math.max.
    return max(v, 0.0)


def barrier_greeks(i: BarrierInputs) -> ExoticGreeks:
    """Greeks of a barrier option, by bumping (see
    :func:`~eqd_desk.engine.exotics.numeric_greeks.numeric_greeks`). Gamma blows up near
    the barrier."""

    def px(S: float, sigma: float, T: float, r: float) -> float:
        return barrier_price(replace(i, S=S, sigma=sigma, T=T, r=r))

    return numeric_greeks(px, i.S, i.sigma, i.T, i.r)
