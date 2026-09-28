"""The trading book: filled option trades + an underlying (index-proxy) hedge + cash.

Marked off the current market's skew surface (:func:`~eqd_desk.engine.sim.market.vol_for_strike`).
Clean accounting::

    bookValue = cash + Σ(marked option value) + underlyingQty·spot

starts at 0 (no positions, no cash), so bookValue IS the running P&L. Trading away from
fair makes value jump by the edge; hedging in the underlying is value-neutral at execution
(frictionless) or costs exactly the half-spread you cross (see :class:`CostModel`).

Every operation is pure: it returns a NEW :class:`Book` and never mutates its input, so a
UI can keep the previous book for undo / diffing.

Example::

    from eqd_desk.engine.sim import (
        MarketState,
        empty_book,
        evaluate_quote,
        add_fill,
        rfq_fair,
        hedge_to_flat,
        single_option_rfq,
    )

    m = MarketState(t=0, spot=100, atm_vol=0.2, r=0.03, q=0.01)
    rfq = single_option_rfq("call", 100, 0.25, 10, "buy", id=1)
    fair = rfq_fair(rfq, m)
    fill = evaluate_quote(rfq, fair.net, fair.gross, 0.06, 0.1, z=1.0)
    book = hedge_to_flat(add_fill(empty_book(), fill, rfq, m), m)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final

from eqd_desk.engine.bsm import price as vanilla_price
from eqd_desk.engine.greeks import raw_greeks
from eqd_desk.engine.reporting import to_reported
from eqd_desk.engine.sim.market import MarketState, vol_for_strike
from eqd_desk.engine.sim.quote import FillResult
from eqd_desk.engine.sim.rfq import RFQ
from eqd_desk.engine.strategy import Leg, LegSide, MarketParams, analyze_position
from eqd_desk.engine.types import BsmInputs, OptionType, RawGreeks, ReportedGreeks

MIN_REMAINING_T: Final = 1e-6
"""Floor (years, ~30 s) on a trade's remaining maturity when it is re-marked. Trades are
never removed from the book: once past expiry they sit at T = 1e-6, i.e. at (discounted)
intrinsic value."""


@dataclass(frozen=True, slots=True)
class BookTrade:
    """One option trade held in the book."""

    id: int
    """Book-unique trade id (1, 2, 3, ... in booking order)."""
    type: OptionType
    """``"call"`` or ``"put"``."""
    side: LegSide
    """``"long"`` (you own it) or ``"short"`` (you sold it)."""
    quantity: float
    """Number of contracts (positive); sign comes from ``side``."""
    K: float
    """Strike (price units)."""
    expiry_time: float
    """Absolute sim-clock time (years) at which this option expires."""
    traded_price: float
    """Per-contract fair (the mark) at booking time."""


@dataclass(frozen=True, slots=True)
class Book:
    """The whole book. Frozen: every operation returns a new one."""

    trades: tuple[BookTrade, ...]
    """Option trades, in booking order."""
    underlying_qty: float
    """Signed position in the index proxy (delta 1)."""
    cash: float
    """Cash account (premiums received − paid, hedge notional, costs)."""
    realized_edge: float
    """Cumulative edge captured at trade time (a stat)."""
    total_costs: float
    """Cumulative transaction costs paid crossing the market on hedges/tickets."""
    next_id: int
    """Id the next booked trade will get."""


def empty_book() -> Book:
    """A flat book: no trades, no hedge, no cash (so its value, the P&L, is 0)."""
    return Book(
        trades=(), underlying_qty=0.0, cash=0.0, realized_edge=0.0, total_costs=0.0, next_id=1
    )


@dataclass(frozen=True, slots=True)
class CostModel:
    """Market trading costs (half-spreads you cross when you hedge in the market)."""

    underlying_half_spread: float
    """Underlying half-spread as a fraction of spot (e.g. 0.0001 = 1 bp)."""
    option_half_spread: float
    """Option half-spread as a fraction of premium (e.g. 0.01 = 1%)."""


ZERO_COSTS: Final = CostModel(underlying_half_spread=0.0, option_half_spread=0.0)
"""Frictionless trading (the default for every hedge function)."""


@dataclass(frozen=True, slots=True)
class BookGreeks:
    """Net greeks of the book in both unit conventions."""

    raw: RawGreeks
    """Raw mathematical units (per 1.00 of vol, per year, ...), hedge folded into delta."""
    reported: ReportedGreeks
    """Desk units (vega per vol point, theta per day, ...; see
    :mod:`eqd_desk.engine.reporting`)."""


@dataclass(frozen=True, slots=True)
class RfqFair:
    """Fair value of ONE package of an RFQ."""

    net: float
    """Signed fair (Σ ±ratio·premium, debit positive): what the trader quotes around."""
    gross: float
    """Σ ratio·|premium| (≥ 0): the scale for the spread, lean and client noise."""


@dataclass(frozen=True, slots=True)
class OptionOrder:
    """A proactive order to trade an option in the market (your own hedge)."""

    type: OptionType
    """``"call"`` or ``"put"``."""
    side: LegSide
    """``"long"`` = buy, ``"short"`` = sell."""
    quantity: float
    """Contracts (must be > 0 to trade; ≤ 0 is a no-op)."""
    K: float
    """Strike (price units)."""
    T: float
    """Tenor in years, from now."""


def _market_params(m: MarketState) -> MarketParams:
    """The strategy engine's shared market params (S, r, q) for this market state."""
    return MarketParams(S=m.spot, r=m.r, q=m.q)


def _inputs(m: MarketState, K: float, T: float) -> BsmInputs:
    """BSM inputs for strike ``K`` / tenor ``T`` at the surface vol of this market."""
    return BsmInputs(S=m.spot, K=K, T=T, r=m.r, q=m.q, sigma=vol_for_strike(m, K, T))


def marked_legs(book: Book, m: MarketState) -> list[Leg]:
    """Trades re-expressed as strategy legs marked on the current surface.

    Each leg gets T = remaining maturity (floored at :data:`MIN_REMAINING_T`) and σ = the
    surface vol for its strike at that maturity.
    """
    legs: list[Leg] = []
    for t in book.trades:
        T = max(t.expiry_time - m.t, MIN_REMAINING_T)
        legs.append(
            Leg(
                id=str(t.id),
                type=t.type,
                side=t.side,
                quantity=t.quantity,
                K=t.K,
                T=T,
                sigma=vol_for_strike(m, t.K, T),
            )
        )
    return legs


def _option_value(book: Book, m: MarketState) -> float:
    """Net option value (signed) of the book at the current market."""
    if len(book.trades) == 0:
        return 0.0
    return analyze_position(marked_legs(book, m), _market_params(m)).price


def book_value(book: Book, m: MarketState) -> float:
    """Book mark-to-market value (= running P&L, since it starts at 0)::

    cash + Σ(marked option value) + underlyingQty·spot
    """
    return book.cash + _option_value(book, m) + book.underlying_qty * m.spot


def _zero() -> RawGreeks:
    """All-zero greeks (the empty book)."""
    return RawGreeks(
        price=0.0,
        delta=0.0,
        gamma=0.0,
        vega=0.0,
        theta=0.0,
        rho=0.0,
        vanna=0.0,
        volga=0.0,
        charm=0.0,
        speed=0.0,
        color=0.0,
    )


def book_greeks_raw(book: Book, m: MarketState) -> RawGreeks:
    """Net raw greeks of the book, with the underlying hedge folded into delta.

    ``price`` is the net option value (the hedge and cash are not in it).
    """
    raw = (
        _zero()
        if len(book.trades) == 0
        else analyze_position(marked_legs(book, m), _market_params(m)).raw
    )
    return replace(raw, delta=raw.delta + book.underlying_qty)


def book_greeks(book: Book, m: MarketState) -> BookGreeks:
    """Net greeks of the book in raw and desk-reported units."""
    raw = book_greeks_raw(book, m)
    return BookGreeks(raw=raw, reported=to_reported(raw))


def rfq_fair(rfq: RFQ, m: MarketState) -> RfqFair:
    """Net (signed) and gross (Σ|leg|) fair value of an RFQ package at the current surface.

    The trader quotes around ``net``; the spread/lean are sized off ``gross``. Each leg is
    priced with the surface vol for its strike and tenor.
    """
    net = 0.0
    gross = 0.0
    for leg in rfq.legs:
        p = vanilla_price(_inputs(m, leg.K, leg.T), leg.type)
        net += (1 if leg.side == "long" else -1) * leg.ratio * p
        gross += leg.ratio * abs(p)
    return RfqFair(net=net, gross=gross)


def add_fill(book: Book, fill: FillResult, rfq: RFQ, m: MarketState) -> Book:
    """Add a filled RFQ to the book (you take the opposite side of the client on the whole
    package).

    The package cash flows at the net traded price (× size); each leg is booked at its
    fair (the mark), so book value jumps by exactly ``fill.edge``. A miss returns the book
    unchanged (the same object).
    """
    if not fill.filled or fill.you_side is None:
        return book
    cash_flow = fill.price * rfq.size if fill.you_side == "sell" else -fill.price * rfq.size
    next_id = book.next_id
    trades = list(book.trades)
    for leg in rfq.legs:
        # client buys package ⇒ you short each leg (flip); client sells ⇒ you long it.
        your_side: LegSide = (
            ("short" if leg.side == "long" else "long") if rfq.client_side == "buy" else leg.side
        )
        leg_fair = vanilla_price(_inputs(m, leg.K, leg.T), leg.type)
        trades.append(
            BookTrade(
                id=next_id,
                type=leg.type,
                side=your_side,
                quantity=leg.ratio * rfq.size,
                K=leg.K,
                expiry_time=m.t + leg.T,
                traded_price=leg_fair,
            )
        )
        next_id += 1
    return replace(
        book,
        trades=tuple(trades),
        cash=book.cash + cash_flow,
        realized_edge=book.realized_edge + fill.edge,
        next_id=next_id,
    )


def hedge_trade(book: Book, dq: float, m: MarketState, costs: CostModel = ZERO_COSTS) -> Book:
    """Trade ``dq`` units of the underlying (+ buy, − sell), crossing the market half-spread.

    cost = |dq|·spot·underlyingHalfSpread; cash moves by −dq·spot − cost.
    """
    cost = abs(dq) * m.spot * costs.underlying_half_spread
    return replace(
        book,
        underlying_qty=book.underlying_qty + dq,
        cash=book.cash - dq * m.spot - cost,
        total_costs=book.total_costs + cost,
    )


def hedge_to_flat(book: Book, m: MarketState, costs: CostModel = ZERO_COSTS) -> Book:
    """Trade the underlying to flatten net delta."""
    net_delta = book_greeks_raw(book, m).delta
    return hedge_trade(book, -net_delta, m, costs)


def trade_option(
    book: Book, order: OptionOrder, m: MarketState, costs: CostModel = ZERO_COSTS
) -> Book:
    """Trade an option in the market (your own hedge), crossing the option half-spread.

    Unlike a client fill you DON'T capture edge: you pay the spread, so book value falls
    by exactly the cost (= quantity·|fair|·optionHalfSpread). A non-positive quantity
    returns the book unchanged.
    """
    if order.quantity <= 0:
        return book
    fair = vanilla_price(_inputs(m, order.K, order.T), order.type)
    cost = order.quantity * abs(fair) * costs.option_half_spread
    cash_flow = (
        -fair * order.quantity - cost if order.side == "long" else fair * order.quantity - cost
    )
    trade = BookTrade(
        id=book.next_id,
        type=order.type,
        side=order.side,
        quantity=order.quantity,
        K=order.K,
        expiry_time=m.t + order.T,
        traded_price=fair,
    )
    return replace(
        book,
        trades=(*book.trades, trade),
        cash=book.cash + cash_flow,
        total_costs=book.total_costs + cost,
        next_id=book.next_id + 1,
    )


def trade_structure(
    book: Book, orders: Sequence[OptionOrder], m: MarketState, costs: CostModel = ZERO_COSTS
) -> Book:
    """Trade a multi-leg structure in the market (each leg crosses the option spread)."""
    b = book
    for o in orders:
        b = trade_option(b, o, m, costs)
    return b


def flatten_vega(book: Book, m: MarketState, tenor_t: float, costs: CostModel = ZERO_COSTS) -> Book:
    """Trade an ATM call (K = spot) of tenor ``tenor_t`` years to flatten net vega.

    Quantity = −netVega / legVega (sign ⇒ side). Picks up some gamma/delta on the way.
    No-op when the hedge option has no vega or the book is already flat.
    """
    net_vega = book_greeks_raw(book, m).vega
    K = m.spot
    leg_vega = raw_greeks(_inputs(m, K, tenor_t), "call").vega
    if leg_vega < 1e-9:
        return book
    need = -net_vega / leg_vega
    if abs(need) < 1e-6:
        return book
    order = OptionOrder(
        type="call", side="long" if need >= 0 else "short", quantity=abs(need), K=K, T=tenor_t
    )
    return trade_option(book, order, m, costs)


def flatten_gamma(
    book: Book, m: MarketState, tenor_t: float, costs: CostModel = ZERO_COSTS
) -> Book:
    """Trade an ATM call (K = spot) of tenor ``tenor_t`` years to flatten net gamma.

    Quantity = −netGamma / legGamma (sign ⇒ side). Picks up some vega/delta on the way.
    No-op when the hedge option has no gamma or the book is already flat.
    """
    net_gamma = book_greeks_raw(book, m).gamma
    K = m.spot
    leg_gamma = raw_greeks(_inputs(m, K, tenor_t), "call").gamma
    if leg_gamma < 1e-12:
        return book
    need = -net_gamma / leg_gamma
    if abs(need) < 1e-6:
        return book
    order = OptionOrder(
        type="call", side="long" if need >= 0 else "short", quantity=abs(need), K=K, T=tenor_t
    )
    return trade_option(book, order, m, costs)


__all__ = [
    "MIN_REMAINING_T",
    "ZERO_COSTS",
    "Book",
    "BookGreeks",
    "BookTrade",
    "CostModel",
    "OptionOrder",
    "RfqFair",
    "add_fill",
    "book_greeks",
    "book_greeks_raw",
    "book_value",
    "empty_book",
    "flatten_gamma",
    "flatten_vega",
    "hedge_to_flat",
    "hedge_trade",
    "marked_legs",
    "rfq_fair",
    "trade_option",
    "trade_structure",
]
