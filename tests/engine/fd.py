"""Central finite-difference harness for validating analytic greeks.

Every analytic greek is checked against a central-difference bump of the pricer here.
Central differences are O(h²) accurate; for cross- and third-derivatives we use slightly
larger steps to keep roundoff in check and loosen the tolerance accordingly (see
``test_greeks.py``). This is a helper module, not a test file.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace
from typing import Literal

from eqd_desk.engine import BsmInputs, OptionType, price

Var = Literal["S", "sigma", "T", "r"]


def bump(i: BsmInputs, v: Var, h: float) -> BsmInputs:
    """Return ``i`` with variable ``v`` shifted by ``h``."""
    return replace(i, **{v: getattr(i, v) + h})


def central1(i: BsmInputs, t: OptionType, v: Var, h: float) -> float:
    """Central first derivative ∂P/∂v."""
    return (price(bump(i, v, h), t) - price(bump(i, v, -h), t)) / (2 * h)


def central2(i: BsmInputs, t: OptionType, v: Var, h: float) -> float:
    """Central second derivative ∂²P/∂v²."""
    up, mid, dn = price(bump(i, v, h), t), price(i, t), price(bump(i, v, -h), t)
    return (up - 2 * mid + dn) / (h * h)


def central3(i: BsmInputs, t: OptionType, v: Var, h: float) -> float:
    """Central third derivative ∂³P/∂v³ (symmetric 4-point stencil)."""
    u2 = price(bump(i, v, 2 * h), t)
    u1 = price(bump(i, v, h), t)
    d1 = price(bump(i, v, -h), t)
    d2 = price(bump(i, v, -2 * h), t)
    return (u2 - 2 * u1 + 2 * d1 - d2) / (2 * h * h * h)


def cross2(i: BsmInputs, t: OptionType, a: Var, ha: float, b: Var, hb: float) -> float:
    """Mixed second derivative ∂²P/∂a∂b (4-point cross stencil)."""
    pp = price(bump(bump(i, a, ha), b, hb), t)
    pm = price(bump(bump(i, a, ha), b, -hb), t)
    mp = price(bump(bump(i, a, -ha), b, hb), t)
    mm = price(bump(bump(i, a, -ha), b, -hb), t)
    return (pp - pm - mp + mm) / (4 * ha * hb)


def spot_scale(i: BsmInputs) -> float:
    """Natural width of the price curve in spot: S·σ√T, normalised to 1·S at σ√T = 0.2.

    Spot bumps are sized relative to it so that short-dated / low-vol options (whose
    curvature lives in a narrow band around the strike) get proportionally finer bumps.
    """
    return i.S * max(i.sigma * math.sqrt(max(i.T, 1e-8)), 1e-4) / 0.2


def _color(i: BsmInputs, t: OptionType) -> float:
    h_s, h_t = 1e-2 * spot_scale(i), 1e-3 * min(1.0, i.T)

    def gamma_at(tt: float) -> float:
        return central2(replace(i, T=tt), t, "S", h_s)

    return -(gamma_at(i.T + h_t) - gamma_at(i.T - h_t)) / (2 * h_t)


FD: dict[str, Callable[[BsmInputs, OptionType], float]] = {
    "delta": lambda i, t: central1(i, t, "S", 1e-4 * spot_scale(i)),
    "vega": lambda i, t: central1(i, t, "sigma", 1e-4),
    "rho": lambda i, t: central1(i, t, "r", 1e-6),
    # time greeks carry the −∂/∂T sign (= ∂/∂t)
    "theta": lambda i, t: -central1(i, t, "T", 1e-5),
    "gamma": lambda i, t: central2(i, t, "S", 1e-3 * spot_scale(i)),
    "volga": lambda i, t: central2(i, t, "sigma", 1e-3),
    "vanna": lambda i, t: cross2(i, t, "S", 1e-3 * spot_scale(i), "sigma", 1e-3),
    "charm": lambda i, t: -cross2(i, t, "S", 1e-3 * spot_scale(i), "T", 1e-5),
    "speed": lambda i, t: central3(i, t, "S", 5e-3 * spot_scale(i)),
    "color": _color,
}
"""Finite-difference estimate of every greek, with bump sizes chosen to beat the analytic
value comfortably."""


def assert_close(
    actual: float, expected: float, rtol: float = 1e-4, atol: float = 1e-7, label: str = ""
) -> None:
    """Mixed absolute+relative tolerance, so legitimately near-zero greeks don't trip a
    pure-relative check: pass iff |actual − expected| ≤ atol + rtol·|expected|."""
    diff = abs(actual - expected)
    bound = atol + rtol * abs(expected)
    assert diff <= bound, f"{label} expected {actual} ≈ {expected} (|Δ|={diff:.3e} > {bound:.3e})"
