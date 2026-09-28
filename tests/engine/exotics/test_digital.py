"""Digitals: closed forms, the static identities, call-spread replication and the bump
greeks' spike behaviour near the strike.

Ported from ``web/src/engine/exotics/__tests__/digital.test.ts`` (same cases and
tolerances; TS ``toBeCloseTo(x, n)`` is ``|a − b| < 0.5·10⁻ⁿ``), plus Python-side checks of
input validation and the T = 0 theta convention.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import pytest

from eqd_desk.engine import BsmInputs, norm_cdf
from eqd_desk.engine import price as vanilla_price
from eqd_desk.engine.exotics import (
    DigitalInputs,
    asset_or_nothing_price,
    call_spread_replication,
    cash_or_nothing_price,
    digital_greeks,
)

BASE = DigitalInputs(S=100, K=100, T=1, r=0.05, q=0.02, sigma=0.2, type="call", cash=1)


def _d2(i: DigitalInputs) -> float:
    sig = i.sigma
    return (math.log(i.S / i.K) + (i.r - i.q - 0.5 * sig * sig) * i.T) / (sig * math.sqrt(i.T))


# --- cash-or-nothing digital -------------------------------------------------------------


def test_cash_digital_prices_as_discounted_probability() -> None:
    """Q·e^(−rT)·N(±d2)."""
    d2 = _d2(BASE)
    df = math.exp(-BASE.r * BASE.T)
    assert cash_or_nothing_price(BASE) == pytest.approx(df * norm_cdf(d2), abs=5e-13)
    put = cash_or_nothing_price(replace(BASE, type="put"))
    assert put == pytest.approx(df * norm_cdf(-d2), abs=5e-13)


def test_call_plus_put_cash_digitals_is_the_discounted_cash() -> None:
    """Something must pay: call + put = e^(−rT) (for Q = 1)."""
    c = cash_or_nothing_price(BASE)
    p = cash_or_nothing_price(replace(BASE, type="put"))
    assert c + p == pytest.approx(math.exp(-BASE.r * BASE.T), abs=5e-13)


def test_cash_digital_is_bounded_by_zero_and_the_discounted_cash() -> None:
    c = cash_or_nothing_price(BASE)
    assert c >= 0
    assert c <= math.exp(-BASE.r * BASE.T) * BASE.cash + 1e-12


# --- digital identities & replication ----------------------------------------------------


def test_vanilla_call_is_asset_digital_minus_k_cash_digitals() -> None:
    """vanilla call = asset-or-nothing call − K·cash-or-nothing call (Q = 1)."""
    an = asset_or_nothing_price(BASE)
    cn = cash_or_nothing_price(replace(BASE, cash=1))
    i = BsmInputs(S=BASE.S, K=BASE.K, T=BASE.T, r=BASE.r, q=BASE.q, sigma=BASE.sigma)
    assert an - BASE.K * cn == pytest.approx(vanilla_price(i, "call"), abs=5e-11)


def test_tight_call_spread_converges_to_the_digital() -> None:
    digital = cash_or_nothing_price(BASE)
    assert call_spread_replication(BASE, 2) == pytest.approx(digital, abs=5e-3)
    assert call_spread_replication(BASE, 0.2) == pytest.approx(digital, abs=5e-5)
    assert call_spread_replication(BASE, 0.02) == pytest.approx(digital, abs=5e-7)
    # put side too
    put = replace(BASE, type="put")
    assert call_spread_replication(put, 0.02) == pytest.approx(cash_or_nothing_price(put), abs=5e-7)


def test_replication_needs_size_q_over_width() -> None:
    """The spread's size Q/Δ grows without bound: 1/Δ lots of each leg (the pin risk)."""
    i = BsmInputs(S=BASE.S, K=BASE.K - 0.01, T=BASE.T, r=BASE.r, q=BASE.q, sigma=BASE.sigma)
    j = replace(i, K=BASE.K + 0.01)
    one_lot = vanilla_price(i, "call") - vanilla_price(j, "call")
    assert call_spread_replication(BASE, 0.02) == pytest.approx(one_lot / 0.02, rel=1e-12)


# --- digital greeks ----------------------------------------------------------------------


def test_delta_matches_the_analytic_digital_delta() -> None:
    """Q·e^(−rT)·φ(d2)/(S·σ√T), positive for a call."""
    sig = BASE.sigma
    d2 = _d2(BASE)
    phi = math.exp(-0.5 * d2 * d2) / math.sqrt(2 * math.pi)
    analytic = BASE.cash * math.exp(-BASE.r * BASE.T) * phi / (BASE.S * sig * math.sqrt(BASE.T))
    g = digital_greeks(BASE)
    assert g.delta == pytest.approx(analytic, abs=5e-5)
    assert g.delta > 0


def test_gamma_changes_sign_across_the_strike() -> None:
    """Just below the strike gamma is positive, just above it is negative (short T)."""
    short_dated = replace(BASE, T=0.05)
    assert digital_greeks(replace(short_dated, S=98)).gamma > 0
    assert digital_greeks(replace(short_dated, S=102)).gamma < 0


def test_theta_is_nan_at_expiry() -> None:
    """No room to bump T at T = 0: the TS gives 0/0 = NaN and so do we."""
    g = digital_greeks(replace(BASE, T=0))
    assert math.isnan(g.theta)
    assert math.isfinite(g.price)
    assert math.isfinite(g.delta)


@pytest.mark.parametrize(("field", "value"), [("S", 0.0), ("K", 0.0), ("K", -5.0)])
def test_rejects_non_positive_levels(field: str, value: float) -> None:
    changes: dict[str, Any] = {field: value}
    i = replace(BASE, **changes)
    with pytest.raises(ValueError, match="digital"):
        cash_or_nothing_price(i)
    with pytest.raises(ValueError, match="digital"):
        asset_or_nothing_price(i)


def test_levels_just_above_zero_reach_the_limits() -> None:
    """S = 0 / K = 0 are rejected, but a level just above 0 gives the limit the TypeScript
    returns AT 0 (see the Raises notes): a zero-strike call is certain to pay (cash:
    Q·e^(−rT); asset: the prepaid forward S·e^(−qT)); a zero-spot call never pays."""
    tiny = 1e-300
    df = math.exp(-BASE.r * BASE.T)
    dfq = math.exp(-BASE.q * BASE.T)
    call_k0 = replace(BASE, K=tiny)
    put_k0 = replace(call_k0, type="put")
    assert cash_or_nothing_price(call_k0) == pytest.approx(df, rel=1e-15)
    assert asset_or_nothing_price(call_k0) == pytest.approx(BASE.S * dfq, rel=1e-15)
    assert cash_or_nothing_price(put_k0) == 0.0
    assert asset_or_nothing_price(put_k0) == 0.0
    call_s0 = replace(BASE, S=tiny)
    put_s0 = replace(call_s0, type="put")
    assert cash_or_nothing_price(call_s0) == 0.0
    assert asset_or_nothing_price(call_s0) == 0.0
    assert cash_or_nothing_price(put_s0) == pytest.approx(df, rel=1e-15)
    assert asset_or_nothing_price(put_s0) == pytest.approx(0.0, abs=1e-290)
