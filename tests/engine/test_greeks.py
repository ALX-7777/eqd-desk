"""Every analytic greek against a central finite difference of the pricer, plus
hard-coded reference values, invariants and the Phase-1 acceptance behaviours."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

import pytest

from eqd_desk.engine import (
    GREEK_NAMES,
    GREEK_UNITS,
    OPTION_TYPES,
    BsmInputs,
    OptionType,
    analyze_option,
    bsm_core,
    charm,
    color,
    delta,
    gamma,
    raw_greeks,
    rho,
    speed,
    theta,
    vanna,
    vega,
    volga,
)
from tests.engine.fd import FD, assert_close

CANONICAL = BsmInputs(S=100, K=100, T=1, r=0.05, q=0, sigma=0.2)

# A q≠0 case is included because q=0 hides the dividend terms in delta/charm/color.
SETS: dict[str, BsmInputs] = {
    "ATM q=0": CANONICAL,
    # deliberately off the d2=0 point so volga/charm are meaningfully nonzero
    "ATM q=3%": BsmInputs(S=100, K=100, T=1, r=0.05, q=0.03, sigma=0.25),
    "OTM call": BsmInputs(S=100, K=120, T=0.5, r=0.03, q=0.01, sigma=0.25),
    "ITM strikes": BsmInputs(S=120, K=100, T=0.75, r=0.04, q=0.02, sigma=0.18),
    "SPX 30d": BsmInputs(S=6312.45, K=6300, T=30 / 365, r=0.043, q=0.013, sigma=0.146),
}

Analytic = Callable[[BsmInputs, OptionType], float]

# greek → (analytic, rtol, atol)
GREEKS: dict[str, tuple[Analytic, float, float]] = {
    "delta": (delta, 1e-5, 1e-8),
    "vega": (lambda i, _t: vega(i), 1e-5, 1e-7),
    "theta": (theta, 1e-5, 1e-7),
    "rho": (rho, 1e-5, 1e-7),
    "gamma": (lambda i, _t: gamma(i), 1e-4, 1e-8),
    "vanna": (lambda i, _t: vanna(i), 1e-4, 1e-7),
    "volga": (lambda i, _t: volga(i), 1e-4, 1e-6),
    "charm": (charm, 1e-4, 1e-6),
    "speed": (lambda i, _t: speed(i), 2e-3, 1e-9),
    "color": (lambda i, _t: color(i), 5e-3, 1e-6),
}


@pytest.mark.parametrize("greek", list(GREEKS))
@pytest.mark.parametrize("option_type", OPTION_TYPES)
@pytest.mark.parametrize("set_name", list(SETS))
def test_greek_matches_finite_difference(
    greek: str, option_type: OptionType, set_name: str
) -> None:
    i = SETS[set_name]
    analytic, rtol, atol = GREEKS[greek]
    # Index-level spot scales the absolute size of the gamma-family greeks down by ~S.
    if i.S > 1000:
        atol *= 1e-2
    assert_close(
        analytic(i, option_type),
        FD[greek](i, option_type),
        rtol,
        atol,
        f"{greek}/{set_name}/{option_type}",
    )


def test_reference_values_canonical() -> None:
    assert delta(CANONICAL, "call") == pytest.approx(0.6368306511756191, abs=5e-8)
    assert delta(CANONICAL, "put") == pytest.approx(-0.36316934882438086, abs=5e-8)
    assert gamma(CANONICAL) == pytest.approx(0.018762017345846895, abs=5e-10)
    assert vega(CANONICAL) == pytest.approx(37.52403469169379, abs=5e-7)
    assert theta(CANONICAL, "call") == pytest.approx(-6.414027546438197, abs=5e-7)
    assert rho(CANONICAL, "call") == pytest.approx(53.232481545376345, abs=5e-7)
    assert vanna(CANONICAL) == pytest.approx(-0.2814302602377034, abs=5e-9)


def test_reported_units() -> None:
    rep = analyze_option(CANONICAL, "call").reported
    assert rep.vega == pytest.approx(0.3752403469169379, abs=5e-9)  # per vol point
    assert rep.theta == pytest.approx(-0.017572678209419718, abs=5e-9)  # per day
    assert rep.rho == pytest.approx(0.5323248154537635, abs=5e-9)  # per rate point
    raw = analyze_option(CANONICAL, "call").raw
    for name in ("price", *GREEK_NAMES):
        divisor = GREEK_UNITS[name].divisor
        assert getattr(rep, name) == pytest.approx(getattr(raw, name) / divisor, rel=1e-15)


@pytest.mark.parametrize("set_name", list(SETS))
def test_invariants(set_name: str) -> None:
    i = SETS[set_name]
    df_q = math.exp(-i.q * i.T)
    assert vega(i) >= 0
    assert gamma(i) >= 0
    dc, dp = delta(i, "call"), delta(i, "put")
    assert 0 <= dc <= df_q + 1e-12
    assert -df_q - 1e-12 <= dp <= 0
    # delta parity: Δc − Δp = e^(−qT)
    assert dc - dp == pytest.approx(df_q, abs=1e-12)
    # symmetric greeks are identical for calls and puts
    c, p = raw_greeks(i, "call"), raw_greeks(i, "put")
    for k in ("gamma", "vega", "vanna", "volga", "speed", "color"):
        assert getattr(c, k) == pytest.approx(getattr(p, k), abs=1e-12)


def test_volga_vanishes_when_d2_is_zero() -> None:
    # S=K=100, T=1, r−q=0.02, σ=0.2 ⇒ d2 = d1 − σ√T = 0.2 − 0.2 = 0, so vega·d1·d2/σ = 0.
    i = BsmInputs(S=100, K=100, T=1, r=0.05, q=0.03, sigma=0.2)
    assert bsm_core(i).d2 == pytest.approx(0, abs=1e-12)
    assert volga(i) == pytest.approx(0, abs=1e-9)


def test_acceptance_atm_gamma_spikes_as_expiry_shrinks() -> None:
    g_long = gamma(replace(CANONICAL, T=1))
    g_mid = gamma(replace(CANONICAL, T=0.25))
    g_short = gamma(replace(CANONICAL, T=1 / 52))
    assert g_long < g_mid < g_short


def test_acceptance_longer_expiry_trades_gamma_for_vega() -> None:
    short, long_ = replace(CANONICAL, T=1 / 52), replace(CANONICAL, T=1)
    assert vega(long_) > vega(short)
    assert gamma(short) > gamma(long_)


@pytest.mark.parametrize("option_type", OPTION_TYPES)
def test_analyze_option_is_consistent(option_type: OptionType) -> None:
    a = analyze_option(CANONICAL, option_type)
    assert a.raw.price == a.reported.price
    assert a.raw.as_dict()["price"] == a.raw.price
    c = bsm_core(CANONICAL)
    assert c.d2 == pytest.approx(c.d1 - c.vol_sqrt_t, abs=1e-12)
