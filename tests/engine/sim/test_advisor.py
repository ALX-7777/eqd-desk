"""Desk advisor. Port of the ``desk advisor`` block of
``web/src/engine/sim/__tests__/sim.test.ts``, plus every advice branch and the
JavaScript-compatible number formatting the advice text relies on."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from eqd_desk.engine.sim import (
    RFQ,
    Book,
    BookTrade,
    OptionOrder,
    RfqLeg,
    advise_book,
    book_greeks,
    book_greeks_raw,
    empty_book,
    hedge_trade,
    joint_hedge,
    rfq_risk_impact,
    trade_option,
)
from eqd_desk.engine.sim.advisor import _js_round, _js_str, _money, _pct, _to_fixed
from eqd_desk.engine.types import OptionType
from tests.engine.sim.common import M0, close


def _short(option_type: OptionType, quantity: float, expiry: float, id: int = 1) -> BookTrade:
    return BookTrade(
        id=id,
        type=option_type,
        side="short",
        quantity=quantity,
        K=100,
        expiry_time=expiry,
        traded_price=0,
    )


def _with_trades(*trades: BookTrade, underlying_qty: float = 0.0) -> Book:
    return replace(empty_book(), trades=trades, underlying_qty=underlying_qty)


# --- desk advisor ----------------------------------------------------------------------------


def test_an_empty_book_is_balanced() -> None:
    a = advise_book(empty_book(), M0, 0.2)
    assert len(a) == 1
    assert a[0].severity == "ok"


def test_a_large_net_delta_yields_a_flatten_delta_recommendation() -> None:
    b = replace(empty_book(), underlying_qty=300)
    a = advise_book(b, M0, 0.2)
    assert any(x.action == "flatten-delta" for x in a)


def test_short_vega_at_low_implied_vol_is_a_high_vega_warning() -> None:
    low_vol = replace(M0, atm_vol=0.1)
    b = _with_trades(_short("call", 500, 0.5))
    vega = next(x for x in advise_book(b, low_vol, 0.08) if x.action == "flatten-vega")
    assert vega.severity == "high"


def test_short_gamma_while_realised_above_implied_is_the_top_high_warning() -> None:
    b = _with_trades(_short("call", 200, 0.25))
    a = advise_book(b, M0, 0.35)  # realised 35% > implied 20%
    assert a[0].severity == "high"
    assert any("Short gamma" in x.title for x in a)


def test_actionable_advice_carries_a_concrete_hedge_plan() -> None:
    # long delta ⇒ a FUTURE plan to sell ≈ |delta|
    d_advice = next(
        x
        for x in advise_book(replace(empty_book(), underlying_qty=300), M0, 0.2, 5)
        if x.action == "flatten-delta"
    )
    d_plan = d_advice.plan
    assert d_plan is not None
    assert d_plan.instrument == "future"
    assert d_plan.side == "sell"
    assert d_plan.quantity == close(300, 0)
    # short vega ⇒ buy a 60-day ATM option
    v_book = _with_trades(_short("call", 500, 0.5))
    v_advice = next(
        x
        for x in advise_book(v_book, replace(M0, atm_vol=0.1), 0.08, 5)
        if x.action == "flatten-vega"
    )
    v_plan = v_advice.plan
    assert v_plan is not None
    assert v_plan.instrument == "option"
    assert v_plan.tenor_days == 60
    assert v_plan.side == "buy"
    assert v_plan.quantity > 0


def test_flags_offsetting_client_flow_as_the_cheapest_hedge() -> None:
    short_vol = _with_trades(_short("call", 100, 0.5, 1), _short("put", 100, 0.5, 2))
    assert book_greeks_raw(short_vol, M0).vega < 0  # short vol
    legs = (
        RfqLeg(type="call", side="long", ratio=1, K=100, T=0.5),
        RfqLeg(type="put", side="long", ratio=1, K=100, T=0.5),
    )
    # client SELLS you the straddle ⇒ you buy ⇒ long vega ⇒ offsets your short vega
    sell = RFQ(id=9, label="Straddle", legs=legs, size=50, client_side="sell", born_day=0)
    # client BUYS the straddle ⇒ you sell ⇒ more short vega
    buy = RFQ(id=10, label="Straddle", legs=legs, size=50, client_side="buy", born_day=0)
    assert rfq_risk_impact(sell, short_vol, M0).verdict == "hedges"
    assert rfq_risk_impact(buy, short_vol, M0).verdict == "adds"


def test_combined_hedge_flattens_delta_gamma_and_vega_together() -> None:
    # short straddle: short gamma AND short vega, plus some residual delta
    book = _with_trades(_short("call", 100, 0.5, 1), _short("put", 80, 0.5, 2), underlying_qty=40)
    before = book_greeks_raw(book, M0)
    assert before.gamma < 0
    assert before.vega < 0

    jh = joint_hedge(book, M0, 5)
    assert jh.feasible is True
    assert len(jh.legs) == 3

    # apply the exact suggested legs and confirm all three greeks collapse to ~0
    b = book
    for leg in jh.legs:
        if leg.instrument == "option":
            assert leg.option_type is not None
            assert leg.K is not None
            assert leg.tenor_days is not None
            order = OptionOrder(
                type=leg.option_type,
                side="long" if leg.side == "buy" else "short",
                quantity=leg.quantity,
                K=leg.K,
                T=leg.tenor_days / 365,
            )
            b = trade_option(b, order, M0)
        else:
            b = hedge_trade(b, (1 if leg.side == "buy" else -1) * leg.quantity, M0)
    after = book_greeks_raw(b, M0)
    assert after.gamma == close(0, 6)
    assert after.vega == close(0, 4)
    assert after.delta == close(0, 4)


# --- beyond the TS tests: every branch -----------------------------------------------------


def test_delta_severity_threshold_and_text() -> None:
    # |Δ·S·1%| = 2·100·0.01·... : 200 units ⇒ $200 per 1% ⇒ medium; 1500 ⇒ $1,500 ⇒ high
    medium = advise_book(replace(empty_book(), underlying_qty=-200), M0, None)[0]
    assert (medium.severity, medium.action) == ("medium", "flatten-delta")
    assert medium.title == "Directional risk — net Δ -200.0"
    assert medium.detail.startswith("You're short the market: a 1% rally costs roughly $200.")
    assert medium.plan is not None
    assert medium.plan.side == "buy"
    high = advise_book(replace(empty_book(), underlying_qty=1500), M0, None)[0]
    assert high.severity == "high"
    assert "costs roughly $1,500." in high.detail
    # below $150 per 1% there is nothing to say
    assert advise_book(replace(empty_book(), underlying_qty=100), M0, None)[0].severity == "ok"


def test_advice_is_sorted_by_severity_and_stable() -> None:
    b = _with_trades(_short("call", 5000, 0.25), underlying_qty=100)
    a = advise_book(b, replace(M0, atm_vol=0.1), 0.3, 5)
    ranks = [("high", "medium", "low", "ok").index(x.severity) for x in a]
    assert ranks == sorted(ranks)
    titles = [x.title for x in a]
    # the axe item comes after the theta item (both "low", emitted in that order)
    assert titles.index("Cheapest hedge: axe your quotes to the flow you want") > next(
        i for i, t in enumerate(titles) if t.startswith("Time decay")
    )


def test_gamma_branches() -> None:
    short = _with_trades(_short("call", 200, 0.25))
    quiet_short = advise_book(short, M0, 0.1)
    assert any(x.title == "Short gamma — exposed to a jump" for x in quiet_short)
    long = replace(short, trades=(replace(short.trades[0], side="long"),))
    quiet_long = advise_book(long, M0, 0.1)
    item = next(x for x in quiet_long if x.action == "flatten-gamma")
    assert item.title == "Long gamma in a quiet tape"
    assert item.severity == "low"
    assert item.plan is not None
    assert (item.plan.side, item.plan.tenor_days) == ("sell", 21)
    # long gamma in a hot tape: nothing to flag on gamma
    assert not any(x.action == "flatten-gamma" for x in advise_book(long, M0, 0.5))
    # no realised vol yet ⇒ the gamma check is skipped
    assert not any(x.action == "flatten-gamma" for x in advise_book(short, M0, None))


def test_theta_and_costs_and_axe_texts() -> None:
    long_vol = _with_trades(replace(_short("call", 3000, 0.25), side="long"))
    items = advise_book(long_vol, M0, 0.2)
    theta = next(x for x in items if x.title.startswith("Time decay"))
    assert theta.detail.startswith("You pay $")
    axe = next(x for x in items if x.title.startswith("Cheapest hedge"))
    assert "Wait for a client BUYING vol from you, and lean DOWN to win client BUYS." in axe.detail

    short_vol = _with_trades(_short("call", 3000, 0.25))
    theta = next(x for x in advise_book(short_vol, M0, 0.2) if x.title.startswith("Time decay"))
    assert theta.detail.startswith("You collect $")

    costly = replace(empty_book(), realized_edge=100, total_costs=60)
    eat = next(x for x in advise_book(costly, M0, 0.2) if x.severity == "medium")
    assert eat.title == "Hedging is eating your edge"
    assert eat.detail.startswith("You've paid $60 in hedge costs against $100 of captured edge.")
    assert advise_book(replace(costly, total_costs=50), M0, 0.2)[0].severity == "ok"


def test_axe_on_gamma_when_vega_is_small() -> None:
    # a very short-dated option: material gamma, tiny vega
    b = _with_trades(_short("call", 3, 5 / 365))
    g = book_greeks(b, M0)
    assert abs(g.reported.vega) <= 100
    assert abs(g.raw.gamma) > 1e-6
    axe = next(x for x in advise_book(b, M0, None) if x.title.startswith("Cheapest hedge"))
    assert "a client selling you short-dated options (you go long gamma)" in axe.detail
    assert "lean toward the side that lengthens your gamma" in axe.detail


def test_rfq_risk_impact_greeks_and_neutral_or_gamma_verdicts() -> None:
    rfq = RFQ(
        id=1,
        label="Call",
        legs=(RfqLeg(type="call", side="long", ratio=2, K=100, T=0.25),),
        size=10,
        client_side="buy",
    )
    flat = rfq_risk_impact(rfq, empty_book(), M0)
    assert flat.verdict == "neutral"
    assert flat.note == "Little impact on your book — price it for the edge."
    # you sell 20 calls: the impact is minus 20 calls' greeks
    ref = book_greeks_raw(_with_trades(_short("call", 20, 0.25)), M0)
    assert flat.d_delta == pytest.approx(ref.delta, rel=1e-12)
    assert flat.d_vega == pytest.approx(ref.vega, rel=1e-12)
    assert flat.d_gamma == pytest.approx(ref.gamma, rel=1e-12)
    # a long-gamma book with little vega: a client buying short-dated calls cuts your gamma
    long_gamma = _with_trades(replace(_short("call", 3, 5 / 365), side="long"))
    net = book_greeks_raw(long_gamma, M0)
    assert abs(net.vega) <= 50
    assert net.gamma > 1e-5
    short_dated = replace(rfq, legs=(replace(rfq.legs[0], T=5 / 365, ratio=1),), size=2)
    imp = rfq_risk_impact(short_dated, long_gamma, M0)
    assert imp.verdict == "hedges"
    assert imp.note == (
        "Brings short gamma that offsets your book — lean in (lower your ask) to win it."
    )


def test_joint_hedge_rationale_and_leg_order() -> None:
    book = _with_trades(_short("call", 100, 0.5, 1), underlying_qty=10)
    jh = joint_hedge(book, replace(M0, spot=101.3), 5)
    assert [leg.instrument for leg in jh.legs] == ["option", "option", "future"]
    assert [leg.tenor_days for leg in jh.legs] == [21, 180, None]
    assert jh.legs[0].K == 100  # 101.3 rounded to the 5-grid
    assert "× 21d ATM 100, " in jh.rationale
    assert jh.rationale.endswith(" × future.")


# --- JavaScript-compatible formatting --------------------------------------------------------


def test_js_round_matches_math_round() -> None:
    assert _js_round(2.5) == 3
    assert _js_round(-2.5) == -2
    assert _js_round(0.49999999999999994) == 0
    assert _js_round(-1.5) == -1
    assert math.copysign(1, _js_round(-0.3)) < 0  # JS: -0
    assert math.copysign(1, _js_round(-0.0)) < 0


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (0, "0"),
        (-0.3, "-0"),
        (0.49, "0"),
        (1234.5, "1,235"),
        (-1234.5, "-1,234"),
        (-1234567.5, "-1,234,567"),
        (999.4, "999"),
        (math.nan, "NaN"),
    ],
)
def test_money_matches_to_locale_string(x: float, expected: str) -> None:
    assert _money(x) == expected


@pytest.mark.parametrize(
    ("x", "digits", "expected"),
    [
        (0.25, 1, "0.3"),
        (-0.25, 1, "-0.3"),
        (-0.04, 1, "-0.0"),
        (-0.0, 1, "0.0"),
        (1.005, 2, "1.00"),  # 1.005 is 1.00499999999999989... in binary
        (-0.4, 0, "-0"),
        (2.5, 0, "3"),
        (-2.5, 0, "-3"),
        (-1234.56, 0, "-1235"),
        (12.345, 1, "12.3"),
    ],
)
def test_to_fixed_matches_js(x: float, digits: int, expected: str) -> None:
    assert _to_fixed(x, digits) == expected


def test_pct_and_js_str() -> None:
    assert _pct(0.146) == "14.6%"
    assert _pct(0.1) == "10.0%"
    assert _js_str(6300.0) == "6300"
    assert _js_str(100.5) == "100.5"
