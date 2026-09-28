"""Behaviour of the simulator's session state machine (:mod:`eqd_desk.app.ui.sim_session`).

The step-by-step equality with the React component is in ``test_sim_session_parity.py``;
here each rule of the desk loop is checked on its own against the engine: the seeded
streams, the clock, RFQ arrival / expiry / selection, quoting (fill and miss), every hedge
and ticket, the combined hedge, reset and replay.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from eqd_desk.app.ui.sim_session import (
    COSTS,
    DEFAULT_WINDOW_LEN,
    EXPIRE_DAYS,
    HEDGE_TENOR,
    MAX_QUEUE,
    NOISE_FRAC,
    RESEED_MARKET,
    SEED_MARKET,
    SEED_NOISE,
    SEED_REPLAY,
    SEED_RFQ,
    CumAttribution,
    FillNote,
    SimSession,
    default_ticket,
    desk_config,
    fill_message,
    initial_state,
    joint_orders,
    js_number,
    miss_message,
    order_fair,
    plan_quantity,
    quote_preview,
    structure_orders,
    ticket_from_plan,
    ticket_preview,
)
from eqd_desk.content.simulator import FILL_MESSAGE_TEMPLATE, MISS_MESSAGE_TEMPLATE
from eqd_desk.data import load_history, load_snapshot
from eqd_desk.engine.presets import PresetParams, build_preset
from eqd_desk.engine.rng import Mulberry32, NormalSampler
from eqd_desk.engine.sim import (
    DEFAULT_SIM_PARAMS,
    HedgePlan,
    OptionOrder,
    attribute,
    book_greeks,
    book_greeks_raw,
    book_value,
    evaluate_quote,
    gbm_leverage_process,
    generate_rfq,
    pick_window,
    replay_state,
    rfq_fair,
    single_option_rfq,
    window_steps,
)

SNAP = load_snapshot()
CFG = desk_config(SNAP)
SERIES = load_history().series


def fresh() -> SimSession:
    """A new desk on the seed snapshot."""
    return SimSession(CFG, SERIES)


# ------------------------------------------------------------------ configuration & start


def test_desk_config_mirrors_the_snapshot() -> None:
    m = CFG.initial_market
    assert (m.t, m.spot, m.atm_vol, m.r, m.q) == (0.0, SNAP.spot, SNAP.atm_vol_30d, SNAP.r, SNAP.q)
    assert (m.skew_slope, m.skew_curv) == (SNAP.skew.slope, SNAP.skew.curv)
    assert CFG.params == replace(DEFAULT_SIM_PARAMS, base_vol=SNAP.atm_vol_30d)
    assert CFG.replay_base.dt == CFG.params.dt == 1 / 252
    assert (CFG.replay_base.r, CFG.replay_base.skew_slope) == (SNAP.r, SNAP.skew.slope)
    assert CFG.strike_step == 25.0
    assert CFG.currency == SNAP.currency


def test_initial_state_is_flat_at_day_zero() -> None:
    s = fresh().state
    assert s.day == 0
    assert s.market == CFG.initial_market
    assert s.book.trades == ()
    assert book_value(s.book, s.market) == 0.0
    assert (s.queue, s.selected_id, s.fill, s.quotes, s.fills) == ((), None, None, 0, 0)
    assert len(s.history) == 1
    assert (s.history[0].spot, s.history[0].vol, s.history[0].pnl) == (
        SNAP.spot,
        SNAP.atm_vol_30d,
        0.0,
    )
    assert s.cum_attr == CumAttribution()


# ------------------------------------------------------------------ the clock


def test_tick_steps_the_seeded_market_stream() -> None:
    desk = fresh()
    normal = NormalSampler(Mulberry32(SEED_MARKET))
    expected = CFG.initial_market
    for day in range(1, 6):
        expected = gbm_leverage_process.step(expected, CFG.params, normal).state
        assert desk.tick()
        assert desk.state.day == day
        assert desk.state.market == expected
        assert desk.state.history[-1].spot == expected.spot
    assert len(desk.state.history) == 6
    assert desk.state.market.t == pytest.approx(5 / 252)


def test_tick_brings_no_client_flow() -> None:
    desk = fresh()
    for _ in range(20):
        desk.tick()
    assert desk.state.queue == ()
    # the arrival stream is untouched: its next draw is still the first one
    assert desk.arrival() == Mulberry32(0xA771)()


def test_step_explains_the_held_book_and_marks_the_history() -> None:
    desk = fresh()
    desk.request_rfq()
    assert desk.quote(0.05, 0.0) is True  # the first seeded RFQ fills (see the parity golden)
    before_market, book = desk.state.market, desk.state.book
    desk.tick()
    after = desk.state.market
    att = attribute(book, before_market, after)
    assert desk.state.cum_attr == CumAttribution().plus(att)
    assert desk.state.history[-1].pnl == book_value(book, after)
    # the explain reconciles: every term plus the residual is the P&L of the step
    assert desk.state.cum_attr.total == pytest.approx(
        book_value(book, after) - book_value(book, before_market), abs=1e-9
    )


def test_auto_tick_needs_auto_on() -> None:
    desk = fresh()
    assert desk.auto_tick() is False
    assert desk.state.day == 0
    desk.set_playing(True)
    assert desk.auto_tick() is True
    assert desk.state.day == 1


def test_auto_brings_rfqs_expires_them_and_caps_the_queue() -> None:
    desk = fresh()
    desk.set_playing(True)
    arrivals = Mulberry32(0xA771)
    rfqs = Mulberry32(SEED_RFQ)
    seen_full = False
    for _ in range(80):
        before = desk.state.queue
        day = desk.state.day + 1
        live = [r for r in before if day - r.born_day <= EXPIRE_DAYS]
        desk.auto_tick()
        queue = desk.state.queue
        if len(live) < MAX_QUEUE and arrivals() < 0.4:
            new = generate_rfq(desk.state.market.spot, 25, rfqs, queue[-1].id, day)
            assert queue[:-1] == tuple(live)
            assert queue[-1] == new
        else:
            assert queue == tuple(live)
        assert all(day - r.born_day <= EXPIRE_DAYS for r in queue)
        assert len(queue) <= MAX_QUEUE
        seen_full = seen_full or len(queue) == MAX_QUEUE
        # the oldest live RFQ is selected when the selection is gone
        if queue:
            assert desk.state.selected_id in {r.id for r in queue}
    assert seen_full


def test_selection_falls_back_to_the_oldest_live_rfq() -> None:
    desk = fresh()
    first = desk.request_rfq()
    second = desk.request_rfq()
    assert first is not None
    assert second is not None
    desk.select_rfq(second.id)
    assert desk.state.selected == second
    for _ in range(EXPIRE_DAYS + 1):
        desk.tick()
    assert desk.state.queue == ()
    assert desk.state.selected_id is None


# ------------------------------------------------------------------ client flow


def test_request_rfq_uses_the_rfq_stream_and_selects_the_first() -> None:
    desk = fresh()
    desk.tick()
    stream = Mulberry32(SEED_RFQ)
    r1 = desk.request_rfq()
    assert r1 == generate_rfq(desk.state.market.spot, 25, stream, 1, 1)
    r2 = desk.request_rfq()
    assert r2 == generate_rfq(desk.state.market.spot, 25, stream, 2, 1)
    assert desk.state.selected_id == 1
    assert desk.state.queue == (r1, r2)


def test_request_rfq_refuses_a_full_queue_and_clears_the_fill_line() -> None:
    desk = fresh()
    desk.state = replace(desk.state, fill=FillNote("old", won=True))
    for _ in range(MAX_QUEUE):
        assert desk.request_rfq() is not None
    assert desk.state.fill is None
    assert desk.request_rfq() is None
    assert len(desk.state.queue) == MAX_QUEUE
    assert desk.next_rfq_id == MAX_QUEUE + 1


def test_quote_fill_books_the_trade_at_the_edge() -> None:
    desk = fresh()
    rfq = desk.request_rfq()
    assert rfq is not None
    m = desk.state.market
    fair = rfq_fair(rfq, m)
    z = NormalSampler(Mulberry32(SEED_NOISE))()
    expected = evaluate_quote(rfq, fair.net, fair.gross, 0.05, NOISE_FRAC, z, 0.0)
    assert desk.quote(0.05, 0.0) is True
    s = desk.state
    assert expected.filled
    assert (s.quotes, s.fills, s.queue, s.selected_id) == (1, 1, (), None)
    assert s.book.realized_edge == expected.edge
    assert book_value(s.book, m) == pytest.approx(expected.edge, abs=1e-9)
    # the fill line of react_ref/4d_sim_after_ticks_advisor.png
    assert s.fill == FillNote("Filled — you SELL 100× Put @ 280.71 · edge 684.66", won=True)


def test_quote_miss_counts_the_quote_only() -> None:
    desk = fresh()
    rfq = desk.request_rfq()
    assert rfq is not None
    # client BUYS; the first client noise is z = 0.81, so an ask 13% of gross above fair
    # (spread 20%, lean +3%) is above their valuation (fair + 8%·z of gross)
    assert desk.quote(0.2, 0.03) is False
    s = desk.state
    assert (s.quotes, s.fills) == (1, 0)
    assert s.book.trades == ()
    assert s.fill == FillNote(miss_message(rfq), won=False)
    assert s.queue == ()


def test_quote_without_a_selection_does_nothing() -> None:
    desk = fresh()
    assert desk.quote(0.05, 0.0) is None
    assert desk.state.quotes == 0
    # and no noise draw was consumed
    assert desk.noise_normal() == NormalSampler(Mulberry32(SEED_NOISE))()


def test_quote_moves_the_selection_to_the_next_rfq() -> None:
    desk = fresh()
    desk.request_rfq()
    second = desk.request_rfq()
    assert second is not None
    desk.quote(0.05, 0.0)
    assert desk.state.selected_id == second.id


def test_pass_removes_the_selected_rfq_without_stats() -> None:
    desk = fresh()
    first = desk.request_rfq()
    second = desk.request_rfq()
    assert first is not None
    assert second is not None
    desk.pass_rfq()
    s = desk.state
    assert s.queue == (second,)
    assert s.selected_id == second.id
    assert (s.quotes, s.fills, s.fill) == (0, 0, None)


# ------------------------------------------------------------------ hedging


def _filled_desk() -> SimSession:
    desk = fresh()
    desk.request_rfq()
    desk.quote(0.05, 0.0)
    for _ in range(3):
        desk.tick()
    return desk


def test_flatten_delta_zeroes_net_delta_at_one_bp() -> None:
    desk = _filled_desk()
    s = desk.state
    delta = book_greeks_raw(s.book, s.market).delta
    assert abs(delta) > 1
    desk.flatten_delta()
    b = desk.state.book
    assert abs(book_greeks_raw(b, s.market).delta) < 1e-9
    assert b.underlying_qty == pytest.approx(-delta)
    assert b.total_costs == pytest.approx(abs(delta) * s.market.spot * COSTS.underlying_half_spread)


@pytest.mark.parametrize(
    ("method", "greek"), [("flatten_vega", "vega"), ("flatten_gamma", "gamma")]
)
def test_flatten_vega_and_gamma_trade_a_60_day_atm_call(method: str, greek: str) -> None:
    desk = _filled_desk()
    m = desk.state.market
    getattr(desk, method)()
    b = desk.state.book
    hedge = b.trades[-1]
    assert (hedge.type, hedge.K) == ("call", m.spot)
    assert hedge.expiry_time == pytest.approx(m.t + HEDGE_TENOR)
    assert abs(getattr(book_greeks_raw(b, m), greek)) < 1e-9
    assert b.total_costs > 0


def test_execute_option_ticket_books_it_at_fair_plus_cost() -> None:
    desk = fresh()
    tk = replace(default_ticket(CFG), option_type="put", side="short", K=6200, days=30, size=20)
    preview = ticket_preview(tk, desk.state.market, CFG.strike_step)
    desk.execute_ticket(tk)
    b = desk.state.book
    (trade,) = b.trades
    assert (trade.type, trade.side, trade.quantity, trade.K) == ("put", "short", 20, 6200)
    assert trade.expiry_time == pytest.approx(30 / 365)
    assert trade.traded_price == pytest.approx(preview.value)
    assert b.total_costs == pytest.approx(preview.cost)
    assert book_value(b, desk.state.market) == pytest.approx(-preview.cost)


def test_execute_structure_ticket_books_every_leg() -> None:
    desk = fresh()
    tk = replace(default_ticket(CFG), kind="structure", preset="butterfly", side="short", size=2)
    desk.execute_ticket(tk)
    b = desk.state.book
    legs = build_preset(
        "butterfly",
        PresetParams(
            S=SNAP.spot, base_t=60 / 365, width_pct=0.05, strike_step=25, vol_for=lambda k, t: 0
        ),
    )
    assert [(t.type, t.K, t.quantity) for t in b.trades] == [
        (leg.type, leg.K, leg.quantity * 2) for leg in legs
    ]
    # selling the structure flips every leg
    assert [t.side for t in b.trades] == ["short", "long", "short"]


def test_execute_future_ticket_trades_the_underlying() -> None:
    desk = fresh()
    desk.execute_ticket(replace(default_ticket(CFG), kind="future", side="short", size=7))
    b = desk.state.book
    assert b.trades == ()
    assert b.underlying_qty == -7
    assert b.total_costs == pytest.approx(7 * SNAP.spot * COSTS.underlying_half_spread)


def test_execute_joint_flattens_delta_gamma_and_vega() -> None:
    desk = _filled_desk()
    desk.flatten_delta()
    jh = desk.joint()
    assert jh.feasible
    orders = joint_orders(jh, desk.state.market, CFG.strike_step)
    assert [o.T for o in orders] == [21 / 365, 180 / 365]
    assert all(
        o.quantity == plan_quantity(leg.quantity) for o, leg in zip(orders, jh.legs, strict=False)
    )
    before = len(desk.state.book.trades)
    desk.execute_joint(jh)
    b, m = desk.state.book, desk.state.market
    assert len(b.trades) == before + 2
    g = book_greeks(b, m)
    assert abs(g.raw.delta) < 1e-9  # the future goes last
    # rounded option sizes leave only a small residual of gamma and vega
    assert abs(g.reported.vega) < 60
    assert abs(g.raw.gamma) < 0.01


# ------------------------------------------------------------------ ticket helpers


def test_default_ticket_is_ten_atm_60_day_calls() -> None:
    tk = default_ticket(CFG)
    assert (tk.kind, tk.side, tk.option_type, tk.K, tk.days, tk.size) == (
        "option",
        "long",
        "call",
        6300,
        60,
        10,
    )
    assert (tk.preset, tk.width_pct) == ("straddle", 0.05)


def test_structure_orders_scale_by_size_and_flip_on_sell() -> None:
    m = CFG.initial_market
    buy = structure_orders(
        replace(default_ticket(CFG), preset="risk-reversal", size=3, width_pct=0.04), m, 25
    )
    sell = structure_orders(
        replace(default_ticket(CFG), preset="risk-reversal", size=3, width_pct=0.04, side="short"),
        m,
        25,
    )
    assert [(o.type, o.side, o.quantity) for o in buy] == [("put", "short", 3), ("call", "long", 3)]
    assert [o.side for o in sell] == ["long", "short"]
    assert [o.K for o in buy] == [o.K for o in sell]


def test_ticket_preview_prices_every_kind() -> None:
    m = CFG.initial_market
    opt = ticket_preview(default_ticket(CFG), m, 25)
    fair = order_fair(OptionOrder("call", "long", 10, 6300, 60 / 365), m)
    assert (opt.label, opt.value, opt.cost) == ("price", fair, 10 * fair * 0.01)
    assert f"{opt.value:.2f}" == "174.27"  # react_ref/4a_simulator.png
    fut = ticket_preview(replace(default_ticket(CFG), kind="future"), m, 25)
    assert (fut.label, fut.value) == ("spot", m.spot)
    assert fut.cost == pytest.approx(10 * m.spot * 1e-4)
    st = ticket_preview(replace(default_ticket(CFG), kind="structure"), m, 25)
    orders = structure_orders(replace(default_ticket(CFG), kind="structure"), m, 25)
    assert st.label == "net"
    assert st.value == pytest.approx(sum(order_fair(o, m) * o.quantity for o in orders))
    assert st.cost == pytest.approx(sum(order_fair(o, m) * o.quantity * 0.01 for o in orders))


def test_ticket_from_plan_loads_future_and_option_plans() -> None:
    tk = default_ticket(CFG)
    fut = ticket_from_plan(
        tk, HedgePlan(instrument="future", side="sell", quantity=29.8, rationale="")
    )
    assert (fut.kind, fut.side, fut.size, fut.K, fut.days) == ("future", "short", 30, tk.K, tk.days)
    opt = ticket_from_plan(
        tk,
        HedgePlan(
            instrument="option",
            side="buy",
            quantity=0.2,
            rationale="",
            option_type="put",
            K=6200,
            tenor_days=21,
        ),
    )
    assert (opt.kind, opt.side, opt.option_type, opt.K, opt.days, opt.size) == (
        "option",
        "long",
        "put",
        6200,
        21,
        1,
    )


def test_plan_quantity_rounds_like_javascript_and_is_at_least_one() -> None:
    assert [plan_quantity(q) for q in (0.0, 0.4, 1.5, 2.5, 217.6)] == [1, 1, 2, 3, 218]


def test_quote_preview_and_messages() -> None:
    q = quote_preview(100.0, 200.0, 0.05, 0.01)
    assert (q.mid, q.bid, q.ask) == (102.0, 97.0, 107.0)
    rfq = single_option_rfq("put", 6150, 1, 100, "buy", id=1)
    assert fill_message("sell", rfq, 280.714, 684.66) == FILL_MESSAGE_TEMPLATE.format(
        side="SELL", size="100", label="Put", price="280.71", edge="684.66"
    )
    assert miss_message(rfq) == MISS_MESSAGE_TEMPLATE.format(label="Put")
    assert [js_number(x) for x in (100.0, 25, 6312.45, 0.5)] == ["100", "25", "6312.45", "0.5"]


# ------------------------------------------------------------------ reset & replay


def test_reset_reseeds_and_keeps_the_rfq_stream_going() -> None:
    desk = fresh()
    desk.request_rfq()
    desk.request_rfq()
    desk.tick()
    desk.set_playing(True)
    desk.reset()
    s = desk.state
    assert s == initial_state(CFG, "simulated", None)
    assert (desk.playing, desk.next_rfq_id, desk.reset_count) == (False, 1, 1)
    # the market stream restarts from SEED + 1·stride …
    desk.tick()
    expected = gbm_leverage_process.step(
        CFG.initial_market, CFG.params, NormalSampler(Mulberry32(SEED_MARKET + RESEED_MARKET))
    ).state
    assert desk.state.market == expected
    # … while the RFQ stream continues where it was (third draw sequence)
    stream = Mulberry32(SEED_RFQ)
    generate_rfq(SNAP.spot, 25, stream, 0)  # every RFQ takes five draws, whatever the spot
    generate_rfq(SNAP.spot, 25, stream, 0)
    third = generate_rfq(desk.state.market.spot, 25, stream, 1, 1)
    assert desk.request_rfq() == third


def test_replay_picks_a_window_and_steps_along_it() -> None:
    desk = fresh()
    desk.switch_mode("historical", 30)
    win = pick_window(SERIES, 30, Mulberry32(SEED_REPLAY)())
    assert desk.window == win
    assert desk.state.market == replay_state(win, 0, CFG.replay_base)
    assert desk.replay_max == window_steps(win) == 30
    for i in range(1, 31):
        assert desk.tick()
        assert desk.state.market == replay_state(win, i, CFG.replay_base)
    assert desk.at_end
    assert desk.tick() is False
    assert desk.state.day == 30
    desk.set_playing(True)
    assert desk.playing is False  # Auto cannot start at the end of an episode


def test_first_replay_window_matches_the_reference_screenshot() -> None:
    desk = fresh()
    desk.switch_mode("historical", DEFAULT_WINDOW_LEN)
    assert desk.window is not None
    assert desk.window.start_index == 1786
    assert (desk.state.market.spot, desk.state.market.atm_vol) == (6329.94, 0.1752)  # 4b


def test_auto_pauses_at_the_end_of_an_episode() -> None:
    desk = fresh()
    desk.switch_mode("historical", 30)
    desk.set_playing(True)
    for _ in range(30):
        desk.auto_tick()
    assert desk.state.day == 30
    assert desk.playing is False
    assert desk.auto_tick() is False


def test_switching_back_to_simulated_drops_the_window() -> None:
    desk = fresh()
    desk.switch_mode("historical")
    desk.switch_mode("simulated")
    assert desk.window is None
    assert desk.replay_max is None
    assert desk.state.market == CFG.initial_market
    assert desk.reset_count == 2


def test_cum_attribution_total_and_order() -> None:
    cum = CumAttribution(1, 2, 3, 4, 5, 6, 7)
    assert list(cum.as_dict()) == ["delta", "gamma", "theta", "vega", "vanna", "volga", "residual"]
    assert cum.total == 28
    assert math.isclose(CumAttribution().total, 0.0)
