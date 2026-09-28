"""Position engine: aggregation, position-level finite-difference greeks, payoff profiles,
preset structures and the skew bet. Port of ``web/src/engine/__tests__/strategy.test.ts``.

TS ``toBeCloseTo(x, n)`` means |a − b| < 0.5·10⁻ⁿ, i.e. ``pytest.approx(x, abs=5·10⁻⁽ⁿ⁺¹⁾)``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace

import pytest

from eqd_desk.engine import GREEK_NAMES, BsmInputs, price
from eqd_desk.engine.presets import PresetParams, build_preset
from eqd_desk.engine.strategy import (
    GREEK_FIELDS,
    Leg,
    MarketParams,
    analyze_position,
    front_expiry,
    leg_inputs,
    leg_value_at,
    payoff_profile,
    position_premium,
    position_value_at,
    signed_qty,
)
from tests.engine.fd import assert_close

M = MarketParams(S=100, r=0.04, q=0.01)


def flat_vol(_K: float, _T: float) -> float:
    return 0.2


def skew_vol(K: float, _T: float) -> float:
    """A representative skewed surface for the skew-bet test (puts richer than calls)."""
    return 0.2 - 0.0015 * (K - 100)


PARAMS = PresetParams(S=100, base_t=0.25, width_pct=0.05, strike_step=5, vol_for=flat_vol)


def butterfly() -> list[Leg]:
    return build_preset("butterfly", PARAMS)


# --- aggregate = signed-quantity-weighted sum of legs ------------------------------------


def test_net_price_equals_sum_of_signed_leg_prices() -> None:
    legs = butterfly()
    a = analyze_position(legs, M)
    manual = sum(la.signed_qty * la.unit.price for la in a.legs)
    assert a.price == pytest.approx(manual, abs=5e-13)
    # and every greek aggregates the same way
    for k in ("delta", "gamma", "vega", "theta", "rho", "vanna"):
        total = sum(la.signed_qty * getattr(la.unit, k) for la in a.legs)
        assert getattr(a.raw, k) == pytest.approx(total, abs=5e-13), k


def test_every_field_aggregates_and_reported_is_rescaled_raw() -> None:
    """Beyond the TS test: all 11 fields (incl. volga/charm/speed/color) aggregate, and the
    aggregate ``reported`` is ``to_reported`` of the aggregate ``raw``."""
    a = analyze_position(build_preset("iron-condor", PARAMS), M)
    assert ("price", *GREEK_NAMES) == GREEK_FIELDS
    for k in GREEK_FIELDS:
        total = sum(la.signed_qty * getattr(la.unit, k) for la in a.legs)
        assert getattr(a.raw, k) == pytest.approx(total, abs=5e-13), k
    assert a.reported.vega == pytest.approx(a.raw.vega / 100, rel=1e-15)
    assert a.reported.theta == pytest.approx(a.raw.theta / 365, rel=1e-15)
    assert a.reported.volga == pytest.approx(a.raw.volga / 10_000, rel=1e-15)


def test_reported_price_equals_raw_price_net_premium() -> None:
    a = analyze_position(butterfly(), M)
    assert a.reported.price == pytest.approx(a.raw.price, abs=5e-13)
    assert a.price == pytest.approx(position_premium(butterfly(), M), abs=5e-13)


def test_leg_breakdown_carries_inputs_and_signed_quantity() -> None:
    legs = butterfly()
    a = analyze_position(legs, M)
    assert [la.leg for la in a.legs] == legs
    assert [la.signed_qty for la in a.legs] == [1, -2, 1]
    for la in a.legs:
        assert la.inputs == leg_inputs(la.leg, M)
        assert (la.inputs.S, la.inputs.r, la.inputs.q) == (M.S, M.r, M.q)


# --- position greeks match finite differences --------------------------------------------

FD_CASES: dict[str, list[Leg]] = {
    "butterfly": butterfly(),
    "risk reversal": build_preset("risk-reversal", replace(PARAMS, base_t=0.5)),
    "calendar": build_preset("calendar", PARAMS),
}


@pytest.mark.parametrize("name", list(FD_CASES))
def test_position_greeks_match_finite_differences(name: str) -> None:
    """delta / gamma / vega / theta / rho of the whole structure vs bumps of its premium."""
    legs = FD_CASES[name]
    a = analyze_position(legs, M)

    def prem(mm: MarketParams) -> float:
        return position_premium(legs, mm)

    d_s = 1e-3 * M.S
    fd_delta = (prem(replace(M, S=M.S + d_s)) - prem(replace(M, S=M.S - d_s))) / (2 * d_s)
    fd_gamma = (prem(replace(M, S=M.S + d_s)) - 2 * prem(M) + prem(replace(M, S=M.S - d_s))) / (
        d_s * d_s
    )

    # parallel vol shift
    def bump_sig(h: float) -> list[Leg]:
        return [replace(leg, sigma=leg.sigma + h) for leg in legs]

    fd_vega = (position_premium(bump_sig(1e-4), M) - position_premium(bump_sig(-1e-4), M)) / (
        2 * 1e-4
    )

    # parallel time shift → theta = −∂/∂T
    def bump_t(h: float) -> list[Leg]:
        return [replace(leg, T=leg.T + h) for leg in legs]

    fd_theta = -(position_premium(bump_t(1e-5), M) - position_premium(bump_t(-1e-5), M)) / (
        2 * 1e-5
    )
    fd_rho = (prem(replace(M, r=M.r + 1e-6)) - prem(replace(M, r=M.r - 1e-6))) / (2 * 1e-6)

    assert_close(a.raw.delta, fd_delta, 1e-4, 1e-6, f"{name} delta")
    assert_close(a.raw.gamma, fd_gamma, 1e-3, 1e-6, f"{name} gamma")
    assert_close(a.raw.vega, fd_vega, 1e-4, 1e-5, f"{name} vega")
    assert_close(a.raw.theta, fd_theta, 1e-4, 1e-5, f"{name} theta")
    assert_close(a.raw.rho, fd_rho, 1e-4, 1e-5, f"{name} rho")


# --- payoff profiles ---------------------------------------------------------------------


def test_bull_call_spread_max_loss_is_debit_max_gain_is_width_minus_debit() -> None:
    legs = build_preset("call-vertical", PARAMS)
    debit = position_premium(legs, M)  # long lower strike, short higher → debit > 0
    assert debit > 0
    pts = payoff_profile(legs, M, 80, 120, 200)
    lo = pts[0].expiry_pnl  # deep OTM → both worthless → −debit
    hi = pts[-1].expiry_pnl  # deep ITM → width − debit
    assert lo == pytest.approx(-debit, abs=5e-7)
    assert hi == pytest.approx(5 - debit, abs=5e-7)  # width = 5


def test_long_straddle_worst_case_at_the_strike_is_minus_premium() -> None:
    legs = build_preset("straddle", PARAMS)
    premium = position_premium(legs, M)
    at_k = position_value_at(legs, 100, front_expiry(legs), M) - premium
    assert at_k == pytest.approx(-premium, abs=5e-7)
    assert premium > 0  # long vol costs money


def test_butterfly_peak_pnl_at_the_body_strike() -> None:
    pts = payoff_profile(butterfly(), M, 80, 120, 400)
    peak = max(pts, key=lambda p: p.expiry_pnl)
    assert abs(peak.S - 100) < 0.5  # body strike (toBeCloseTo(100, 0))
    assert peak.expiry_pnl > 0


def test_calendar_front_expiry_is_the_short_front_leg_and_value_is_finite() -> None:
    legs = build_preset("calendar", PARAMS)
    assert front_expiry(legs) == pytest.approx(0.25, abs=5e-10)
    v = position_value_at(legs, 100, front_expiry(legs), M)
    assert math.isfinite(v)
    # a long calendar (short front, long back) is a debit
    assert position_premium(legs, M) > 0


def test_payoff_profile_grid_and_now_pnl_at_spot_is_zero() -> None:
    """Beyond the TS test: n + 1 evenly spaced points spanning [s_lo, s_hi]; today's P&L at
    today's spot is exactly zero (value-now − premium)."""
    pts = payoff_profile(butterfly(), M, 80, 120, 40)
    assert len(pts) == 41
    assert pts[0].S == 80
    assert pts[-1].S == 120
    at_spot = next(p for p in pts if p.S == 100)
    assert at_spot.now_pnl == pytest.approx(0, abs=1e-12)
    assert len(payoff_profile(butterfly(), M, 80, 120)) == 121  # default n = 120
    with pytest.raises(ValueError, match="n >= 1"):
        payoff_profile(butterfly(), M, 80, 120, 0)


def test_expired_legs_contribute_signed_intrinsic() -> None:
    """Beyond the TS test: at/after its expiry a leg is worth signed intrinsic; before it,
    signed BSM value with the remaining maturity."""
    short_put = Leg(id="p", type="put", side="short", quantity=2, K=100, T=0.25, sigma=0.2)
    assert leg_value_at(short_put, 90, 0.25, M) == pytest.approx(-20, abs=1e-12)
    assert leg_value_at(short_put, 90, 1.0, M) == pytest.approx(-20, abs=1e-12)
    assert leg_value_at(short_put, 110, 0.25, M) == 0
    alive = leg_value_at(short_put, 90, 0.1, M)  # 0.15y of life left
    put_now = price(BsmInputs(S=90, K=100, T=0.15, r=M.r, q=M.q, sigma=0.2), "put")
    assert alive == pytest.approx(-2 * put_now, rel=1e-12)
    # A deep-ITM European put can be worth LESS than intrinsic when r > q (you wait to
    # receive K), so the short position is a smaller liability before expiry than at it.
    assert alive > -20


# --- presets -----------------------------------------------------------------------------


def test_presets_build_the_expected_leg_structures() -> None:
    assert len(build_preset("straddle", PARAMS)) == 2
    assert len(build_preset("butterfly", PARAMS)) == 3
    assert len(build_preset("iron-condor", PARAMS)) == 4
    bfly = build_preset("butterfly", PARAMS)
    assert bfly[1].quantity == 2  # body is 2x
    assert bfly[1].side == "short"
    rr = build_preset("risk-reversal", PARAMS)
    assert next(leg for leg in rr if leg.type == "put").side == "short"
    assert next(leg for leg in rr if leg.type == "call").side == "long"


def test_presets_seed_each_leg_vol_from_the_provider_and_support_multi_expiry() -> None:
    legs = build_preset("calendar", replace(PARAMS, vol_for=lambda _K, T: 0.2 + T * 0.01))
    assert legs[0].T != legs[1].T  # calendar spans two expiries
    for leg in legs:
        assert leg.sigma == pytest.approx(0.2 + leg.T * 0.01, abs=5e-10)


def test_presets_unique_leg_ids() -> None:
    ids = [leg.id for leg in build_preset("iron-condor", PARAMS)]
    assert len(set(ids)) == len(ids)


# --- risk reversal expresses a skew bet --------------------------------------------------


def test_skew_makes_the_long_call_short_put_risk_reversal_cheaper_than_flat_vol() -> None:
    flat = build_preset("risk-reversal", replace(PARAMS, base_t=0.5))
    skewed = build_preset("risk-reversal", replace(PARAMS, base_t=0.5, vol_for=skew_vol))
    # Under put-skew the short put collects more, so the structure is cheaper.
    assert position_premium(skewed, M) < position_premium(flat, M)


# --- edge cases --------------------------------------------------------------------------


def test_empty_position_is_all_zeros() -> None:
    empty: Sequence[Leg] = []
    a = analyze_position(empty, M)
    assert a.price == 0
    assert a.raw.delta == 0
    assert all(v == 0 for v in a.raw.as_dict().values())
    assert all(v == 0 for v in a.reported.as_dict().values())
    assert a.legs == ()
    assert front_expiry(empty) == 0
    assert position_premium(empty, M) == 0
    short3 = Leg(id="x", type="call", side="short", quantity=3, K=100, T=1, sigma=0.2)
    assert signed_qty(short3) == -3
    assert signed_qty(replace(short3, side="long")) == 3
