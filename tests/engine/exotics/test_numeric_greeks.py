"""The shared bump-greek stencil: on a vanilla (where the analytic greeks are known) it must
reproduce the engine's desk-reported greeks, in the same units."""

from __future__ import annotations

import math

import pytest

from eqd_desk.engine import BsmInputs, OptionType, analyze_option, price
from eqd_desk.engine.exotics import ExoticGreeks, PriceFn, numeric_greeks

CASES = [
    BsmInputs(S=100, K=100, T=1, r=0.05, q=0.0, sigma=0.2),
    BsmInputs(S=100, K=120, T=0.5, r=0.03, q=0.01, sigma=0.25),
    BsmInputs(S=6312.45, K=6300, T=30 / 365, r=0.043, q=0.013, sigma=0.146),
]


def _vanilla(i: BsmInputs, option_type: OptionType) -> PriceFn:
    def px(S: float, sigma: float, T: float, r: float) -> float:
        return price(BsmInputs(S=S, K=i.K, T=T, r=r, q=i.q, sigma=sigma), option_type)

    return px


@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize("i", CASES)
def test_bump_greeks_equal_analytic_desk_greeks(i: BsmInputs, option_type: OptionType) -> None:
    got = numeric_greeks(_vanilla(i, option_type), i.S, i.sigma, i.T, i.r)
    want = analyze_option(i, option_type).reported
    assert got.price == price(i, option_type)
    for name in ("delta", "gamma", "vega", "theta", "rho"):
        assert getattr(got, name) == pytest.approx(getattr(want, name), rel=2e-5, abs=1e-9), name


def test_uses_nine_price_evaluations() -> None:
    calls: list[tuple[float, float, float, float]] = []

    def px(S: float, sigma: float, T: float, r: float) -> float:
        calls.append((S, sigma, T, r))
        return S + sigma + T + r

    numeric_greeks(px, 100, 0.2, 1, 0.05)
    assert len(calls) == 9
    assert len(set(calls)) == 9


def test_theta_is_nan_at_zero_expiry() -> None:
    g = numeric_greeks(lambda S, _sig, _T, _r: S, 100, 0.2, 0, 0.05)
    assert math.isnan(g.theta)
    assert g.delta == pytest.approx(1)


def test_time_bump_is_capped_at_half_the_expiry() -> None:
    """For T < 2e-5 the time bump is T/2, so we never price at negative T."""
    seen: list[float] = []

    def px(S: float, _sigma: float, T: float, _r: float) -> float:
        seen.append(T)
        return S * T

    g = numeric_greeks(px, 100, 0.2, 1e-6, 0.05)
    assert min(seen) == pytest.approx(0.5e-6)
    assert g.theta == pytest.approx(-100 / 365)


def test_rejects_non_positive_spot() -> None:
    with pytest.raises(ValueError, match="spot"):
        numeric_greeks(lambda S, _sig, _T, _r: S, 0, 0.2, 1, 0.05)


def test_as_dict_lists_every_field_in_order() -> None:
    g = ExoticGreeks(price=1, delta=2, gamma=3, vega=4, theta=5, rho=6)
    assert g.as_dict() == {"price": 1, "delta": 2, "gamma": 3, "vega": 4, "theta": 5, "rho": 6}
