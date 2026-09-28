"""The trading book: accounting, costs, market hedges and structure RFQs. Port of the
``book accounting``, ``transaction costs & market hedges`` and ``structure RFQs`` blocks of
``web/src/engine/sim/__tests__/sim.test.ts``, plus immutability, no-op branches and a
finite-difference check of the book's greeks against its mark-to-market value."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eqd_desk.engine import BsmInputs, price, to_reported
from eqd_desk.engine.presets import PresetParams, build_preset
from eqd_desk.engine.sim import (
    RFQ,
    BookTrade,
    ClientSide,
    OptionOrder,
    RfqLeg,
    add_fill,
    book_greeks,
    book_greeks_raw,
    book_value,
    empty_book,
    evaluate_quote,
    flatten_gamma,
    flatten_vega,
    hedge_to_flat,
    hedge_trade,
    marked_legs,
    rfq_fair,
    single_option_rfq,
    trade_option,
    trade_structure,
    vol_for_strike,
)
from tests.engine.sim.common import COSTS, M0, SKEW_MARKET, close

# --- book accounting -----------------------------------------------------------------------


def test_empty_book_has_zero_value_and_greeks() -> None:
    b = empty_book()
    assert book_value(b, M0) == 0
    assert book_greeks_raw(b, M0).delta == 0


def test_selling_a_call_to_a_client_short_delta_cash_in_value_is_edge() -> None:
    rfq = single_option_rfq("call", 100, 0.25, 10, "buy", 1)
    # Quote around the REAL BSM fair (the book marks at the same value).
    fair = price(BsmInputs(S=100, K=100, T=0.25, r=0.03, q=0.01, sigma=0.2), "call")
    fill = evaluate_quote(rfq, fair, fair, 0.06, 0.1, 1.0)  # fills (you sell at ask)
    assert fill.filled is True
    b = add_fill(empty_book(), fill, rfq, M0)
    assert book_greeks_raw(b, M0).delta < 0  # short a call
    # value ≈ the edge captured (you sold above fair)
    assert book_value(b, M0) == close(fill.edge, 6)


def test_hedge_to_flat_zeroes_net_delta_and_is_value_neutral() -> None:
    rfq = single_option_rfq("call", 100, 0.25, 50, "buy", 1)
    fill = evaluate_quote(rfq, 5, 5, 0.06, 0.1, 1.0)
    b = add_fill(empty_book(), fill, rfq, M0)
    value_before = book_value(b, M0)
    hedged = hedge_to_flat(b, M0)
    assert book_greeks_raw(hedged, M0).delta == close(0, 6)
    assert book_value(hedged, M0) == close(value_before, 6)  # frictionless


# --- transaction costs & market hedges -----------------------------------------------------


def test_costed_hedge_to_flat_zeroes_delta_and_reduces_value_by_the_spread() -> None:
    rfq = single_option_rfq("call", 100, 0.25, 50, "buy", 1)
    fair = price(BsmInputs(S=100, K=100, T=0.25, r=0.03, q=0.01, sigma=0.2), "call")
    b = add_fill(empty_book(), evaluate_quote(rfq, fair, fair, 0.06, 0.1, 1.0), rfq, M0)
    before = book_value(b, M0)
    hedged = hedge_to_flat(b, M0, COSTS)
    assert book_greeks_raw(hedged, M0).delta == close(0, 6)
    assert book_value(hedged, M0) < before
    assert hedged.total_costs > 0


def test_trading_an_option_in_the_market_costs_exactly_the_spread() -> None:
    order = OptionOrder(type="call", side="long", quantity=10, K=100, T=0.25)
    b = trade_option(empty_book(), order, M0, COSTS)
    assert book_value(b, M0) == close(-b.total_costs, 6)
    assert b.total_costs > 0
    assert len(b.trades) == 1


def test_flatten_vega_zeroes_net_vega_and_flatten_gamma_zeroes_net_gamma() -> None:
    rfq = single_option_rfq("put", 95, 0.5, 30, "sell", 1)
    fair = price(BsmInputs(S=100, K=95, T=0.5, r=0.03, q=0.01, sigma=0.2), "put")
    b = add_fill(empty_book(), evaluate_quote(rfq, fair, fair, 0.06, 0.1, -1.0), rfq, M0)
    assert book_greeks_raw(flatten_vega(b, M0, 0.25, COSTS), M0).vega == close(0, 4)
    assert book_greeks_raw(flatten_gamma(b, M0, 0.25, COSTS), M0).gamma == close(0, 6)


def test_trade_structure_books_every_leg_and_charges_each_cost() -> None:
    legs = build_preset(
        "straddle",
        PresetParams(S=100, base_t=0.25, width_pct=0.05, strike_step=5, vol_for=lambda K, T: 0.2),
    )
    orders = [
        OptionOrder(type=leg.type, side=leg.side, quantity=leg.quantity * 5, K=leg.K, T=leg.T)
        for leg in legs
    ]
    b = trade_structure(empty_book(), orders, M0, COSTS)
    assert len(b.trades) == 2
    assert b.total_costs > 0
    assert book_greeks_raw(b, M0).vega > 0  # long straddle ⇒ long vega


# --- structure RFQs ------------------------------------------------------------------------

STRADDLE = RFQ(
    id=1,
    label="Straddle",
    legs=(
        RfqLeg(type="call", side="long", ratio=1, K=100, T=0.25),
        RfqLeg(type="put", side="long", ratio=1, K=100, T=0.25),
    ),
    size=10,
    client_side="buy",
    born_day=0,
)


def test_net_gross_fair_filled_package_books_all_legs_value_is_edge() -> None:
    fair = rfq_fair(STRADDLE, M0)
    assert fair.net > 0
    assert fair.gross >= fair.net - 1e-9
    fill = evaluate_quote(STRADDLE, fair.net, fair.gross, 0.06, 0.1, 1.0)
    assert fill.filled is True
    b = add_fill(empty_book(), fill, STRADDLE, M0)
    assert len(b.trades) == 2
    assert book_greeks_raw(b, M0).vega < 0  # client bought ⇒ you short vol
    assert book_value(b, M0) == close(fill.edge, 6)


def test_a_credit_structure_risk_reversal_still_quotes_via_gross() -> None:
    rr = RFQ(
        id=2,
        label="Risk reversal",
        legs=(
            RfqLeg(type="put", side="short", ratio=1, K=90, T=0.5),
            RfqLeg(type="call", side="long", ratio=1, K=110, T=0.5),
        ),
        size=10,
        client_side="buy",
        born_day=0,
    )
    fair = rfq_fair(rr, M0)
    assert fair.gross > abs(fair.net)  # gross defined even if net ≈ 0
    fill = evaluate_quote(rr, fair.net, fair.gross, 0.08, 0.1, 2.0)
    assert fill.filled is True
    assert len(add_fill(empty_book(), fill, rr, M0).trades) == 2


# --- beyond the TS tests -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("client_side", "your_sides"),
    [("buy", ("long", "short")), ("sell", ("short", "long"))],
)
def test_add_fill_flips_legs_when_the_client_buys_and_keeps_them_when_they_sell(
    client_side: ClientSide, your_sides: tuple[str, str]
) -> None:
    rr_legs = (
        RfqLeg(type="put", side="short", ratio=1, K=90, T=0.5),
        RfqLeg(type="call", side="long", ratio=2, K=110, T=0.5),
    )
    rfq = RFQ(id=3, label="RR", legs=rr_legs, size=5, client_side=client_side)
    fair = rfq_fair(rfq, SKEW_MARKET)
    z = 5.0 if client_side == "buy" else -5.0
    fill = evaluate_quote(rfq, fair.net, fair.gross, 0.02, 0.1, z)
    assert fill.filled is True
    b = add_fill(replace(empty_book(), next_id=7), fill, rfq, SKEW_MARKET)
    assert tuple(t.side for t in b.trades) == your_sides
    assert [t.id for t in b.trades] == [7, 8]
    assert b.next_id == 9
    assert [t.quantity for t in b.trades] == [5, 10]
    call_sigma = vol_for_strike(SKEW_MARKET, 110, 0.5)
    call_fair = price(BsmInputs(S=100, K=110, T=0.5, r=0.03, q=0.01, sigma=call_sigma), "call")
    assert b.trades[1].traded_price == pytest.approx(call_fair, rel=1e-15)
    assert b.realized_edge == fill.edge
    assert book_value(b, SKEW_MARKET) == pytest.approx(fill.edge, abs=1e-9)


def test_operations_never_mutate_and_misses_or_zero_orders_are_no_ops() -> None:
    b0 = empty_book()
    rfq = single_option_rfq("call", 100, 0.25, 10, "buy", 1)
    miss = evaluate_quote(rfq, 5, 5, 0.06, 0.1, 0.0)
    assert add_fill(b0, miss, rfq, M0) is b0
    zero = OptionOrder(type="call", side="long", quantity=0, K=100, T=0.25)
    assert trade_option(b0, zero, M0, COSTS) is b0
    b1 = hedge_trade(b0, 3, M0, COSTS)
    assert b0 == empty_book()  # the input is untouched
    assert b1.underlying_qty == 3
    assert b1.cash == pytest.approx(-300 - 3 * 100 * 0.0001, rel=1e-15)
    assert b1.total_costs == pytest.approx(0.03, rel=1e-12)
    # flat books: nothing to flatten
    assert flatten_vega(b0, M0, 0.25) is b0
    assert flatten_gamma(b0, M0, 0.25) is b0


def test_marked_legs_use_remaining_maturity_and_surface_vol() -> None:
    book = replace(
        empty_book(),
        trades=(
            BookTrade(
                id=1, type="put", side="short", quantity=20, K=90, expiry_time=0.5, traded_price=2
            ),
            BookTrade(
                id=2, type="call", side="long", quantity=1, K=110, expiry_time=0.1, traded_price=0
            ),
        ),
    )
    later = replace(SKEW_MARKET, t=0.2)
    legs = marked_legs(book, later)
    assert [leg.id for leg in legs] == ["1", "2"]
    assert legs[0].T == pytest.approx(0.3, rel=1e-14)
    assert legs[1].T == 1e-6  # expired: floored
    assert legs[0].sigma == vol_for_strike(later, 90, legs[0].T)


def test_book_greeks_reported_is_rescaled_raw_and_hedge_folds_into_delta() -> None:
    book = replace(
        empty_book(),
        underlying_qty=-4,
        trades=(
            BookTrade(
                id=1, type="call", side="long", quantity=10, K=100, expiry_time=0.5, traded_price=0
            ),
        ),
    )
    g = book_greeks(book, SKEW_MARKET)
    assert g.reported == to_reported(g.raw)
    options_only = book_greeks_raw(replace(book, underlying_qty=0), SKEW_MARKET)
    assert g.raw.delta == pytest.approx(options_only.delta - 4, rel=1e-15)
    assert g.raw.gamma == options_only.gamma


def test_book_delta_and_gamma_match_finite_differences_of_book_value() -> None:
    """Flat surface: the book's delta/gamma are the spot derivatives of its value."""
    book = replace(
        empty_book(),
        underlying_qty=7,
        cash=123.0,
        trades=(
            BookTrade(
                id=1, type="put", side="short", quantity=20, K=95, expiry_time=0.5, traded_price=0
            ),
            BookTrade(
                id=2, type="call", side="long", quantity=15, K=105, expiry_time=0.3, traded_price=0
            ),
        ),
    )
    h = 1e-3
    up, dn = replace(M0, spot=100 + h), replace(M0, spot=100 - h)
    fd_delta = (book_value(book, up) - book_value(book, dn)) / (2 * h)
    fd_gamma = (book_value(book, up) - 2 * book_value(book, M0) + book_value(book, dn)) / (h * h)
    g = book_greeks_raw(book, M0)
    assert g.delta == pytest.approx(fd_delta, rel=1e-6)
    assert g.gamma == pytest.approx(fd_gamma, rel=1e-4)
