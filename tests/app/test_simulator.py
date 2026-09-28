"""AppTest suite of the trading-simulator page (``app_pages/simulator.py``).

Drives the real page headless through its widgets and checks what it SHOWS (decoded from
the rendered tables, metrics, messages) against the session and the engine: the clock, the
RFQ flow (request, select, quote → fill or miss, pass), every hedge, the trade ticket, the
advisor dialog and its plans, Reset, Replay and the episode end, and Auto on its timer.
"""

from __future__ import annotations

import re
import time
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pytest
from streamlit.testing.v1 import AppTest

from eqd_desk.app.ui import simulator_controls as ctl
from eqd_desk.app.ui.format import MINUS, fmt_money, fmt_num
from eqd_desk.app.ui.sim_session import SimSession, Ticket, ticket_preview
from eqd_desk.app.ui.simulator_inputs import gen_key, widget_key
from eqd_desk.content.simulator import (
    ADVISOR_SUBTITLE,
    ATTRIBUTION_TERMS,
    EMPTY_BOOK_HINT,
    EMPTY_QUEUE_HINT,
    EPISODE_ENDED_MESSAGE,
    OPTION_HEDGE_CAPTION,
    SIM_CONCEPTS,
)
from eqd_desk.engine.sim import advise_book, book_greeks_raw, realised_vol
from tests.app.conftest import AppTestFactory

pytestmark = pytest.mark.app

PAGE = "app_pages/simulator.py"
FIRST_FILL = "Filled — you SELL 100× Put @ 280.71 · edge 684.66"
"""The first seeded RFQ quoted at the default 5% spread (react_ref/4d)."""


# ------------------------------------------------------------------ helpers


def open_page(app_test: AppTestFactory) -> AppTest:
    at = app_test()
    at.run()
    at.switch_page(PAGE).run()
    assert not at.exception, at.exception
    return at


def desk(at: AppTest) -> SimSession:
    sess = at.session_state[ctl.SESSION_KEY]
    assert isinstance(sess, SimSession)
    return sess


def wkey(at: AppTest, key: str) -> str:
    """The widget key an input with canonical ``key`` currently renders with."""
    try:
        generation = int(at.session_state[gen_key(key)])
    except KeyError:
        generation = 0
    return widget_key(key, generation)


def click(at: AppTest, key: str) -> AppTest:
    at.button(key=key).click().run()
    assert not at.exception, at.exception
    return at


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def shown(table: Any) -> list[list[str]]:
    """The cell TEXT a (Styler) table displays, row by row."""
    styler = table.proto.arrow_data.styler
    frame = pa.ipc.open_stream(styler.display_values).read_all().to_pandas()
    return [[_unescape(str(v)) for v in row] for row in frame.itertuples(index=False)]


def readout(at: AppTest, first_label: str) -> dict[str, str]:
    """The ``label → value`` text of the readout table whose first row is ``first_label``."""
    for t in at.table:
        rows = shown(t)
        if rows and rows[0][0] == first_label:
            return {r[0]: r[1] for r in rows}
    raise AssertionError(f"no table starting with {first_label!r}")


def texts(at: AppTest) -> list[str]:
    """Every markdown / caption text on the page (escapes removed)."""
    return [_unescape(e.value) for e in (*at.markdown, *at.caption)]


def has(at: AppTest, fragment: str) -> bool:
    """Whether some markdown / caption on the page contains ``fragment``."""
    return any(fragment in t for t in texts(at))


def fill_first_rfq(at: AppTest) -> None:
    click(at, "sim.btn_request")
    click(at, "sim.btn_quote")


# ------------------------------------------------------------------ the page


def test_page_renders_the_desk_at_the_seed(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    market = readout(at, "Spot")
    assert market == {
        "Spot": "6,312.45",
        "ATM vol (implied)": "14.60%",
        "Realised vol": "—",
        "Skew slope": "-0.480",
    }  # react_ref/4a_simulator.png
    card = readout(at, "P&L")
    assert card["Fill rate"] == "0% (0/0)"
    assert card["Costs paid"] == f"{MINUS}0.00"
    book = readout(at, "Delta")
    assert list(book) == ["Delta", "Gamma", "Vega", "Theta", "Hedge (underlying)"]
    assert at.metric[0].value.endswith("[+0.00]")
    page = texts(at)
    for text in (EMPTY_QUEUE_HINT, EMPTY_BOOK_HINT, OPTION_HEDGE_CAPTION):
        assert text in page
    assert [e.label for e in at.expander] == [c.title for c in SIM_CONCEPTS]
    assert all(any(t.label in p for p in page) for t in ATTRIBUTION_TERMS)
    assert [at.button(key=k).label for k in ("sim.btn_tick", "sim.btn_auto")] == ["Tick", "Auto"]
    # the trade ticket's price & cost preview (react_ref/4a: price 174.27, cost −17.43)
    assert has(at, "price 174.27")
    assert has(at, f"cost {MINUS}17.43")


def test_tick_advances_the_clock_and_the_spot(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    click(at, "sim.btn_tick")
    s = desk(at).state
    assert s.day == 1
    assert s.market.t == pytest.approx(1 / 252)
    assert len(s.history) == 2
    assert s.market.spot != 6312.45
    assert readout(at, "Spot")["Spot"] == fmt_money(s.market.spot)
    click(at, "sim.btn_tick")
    click(at, "sim.btn_tick")
    s = desk(at).state
    rv = realised_vol([h.spot for h in s.history], 1 / 252)
    assert rv is not None
    assert readout(at, "Spot")["Realised vol"] == f"{rv * 100:.2f}%"


# ------------------------------------------------------------------ client flow


def test_request_a_quote_shows_the_rfq_and_the_quote_box(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    click(at, "sim.btn_request")
    rfq = desk(at).state.queue[0]
    chip = at.button(key=f"sim.rfq_{rfq.id}")
    assert "100× Put · 273.87" in _unescape(chip.label)  # react_ref/4c_sim_rfq.png
    page = texts(at)
    assert "CLIENT BUYS · +1 P6150 · net 273.87" in page
    assert has(at, "bid 267.02")
    assert has(at, "ask 280.71")
    assert has(at, "1 live")
    assert EMPTY_QUEUE_HINT not in page


def test_quote_fills_and_updates_the_book_and_scorecard(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    fill_first_rfq(at)
    assert [_unescape(s.value) for s in at.success] == [FIRST_FILL]
    card = readout(at, "P&L")
    assert card["Fill rate"] == "100% (1/1)"
    assert card["Edge captured"] == "684.66"
    assert card["P&L"] == "+684.66"
    assert at.metric[0].value.endswith("[+684.66]")
    assert has(at, "Positions (1)")
    blotter = shown(at.table[-1])
    assert blotter == [[f"{MINUS}100", "P 6,150.00", "365d"]]
    assert desk(at).state.queue == ()


def test_quote_can_miss(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    click(at, "sim.btn_request")
    at.slider(key=wkey(at, ctl.SPREAD_KEY)).set_value(0.2).run()
    at.slider(key=wkey(at, ctl.LEAN_KEY)).set_value(0.03).run()
    assert (at.session_state[ctl.SPREAD_KEY], at.session_state[ctl.LEAN_KEY]) == (0.2, 0.03)
    click(at, "sim.btn_quote")
    assert [_unescape(w.value) for w in at.warning] == ["Missed Put — client traded elsewhere"]
    assert readout(at, "P&L")["Fill rate"] == "0% (0/1)"
    assert desk(at).state.book.trades == ()


def test_select_and_pass(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    click(at, "sim.btn_request")
    click(at, "sim.btn_request")
    first, second = desk(at).state.queue
    assert desk(at).state.selected_id == first.id
    click(at, f"sim.rfq_{second.id}")
    assert desk(at).state.selected_id == second.id
    click(at, "sim.btn_pass")
    s = desk(at).state
    assert s.queue == (first,)
    assert s.selected_id == first.id
    assert s.quotes == 0


def test_request_is_disabled_when_the_queue_is_full(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    for _ in range(4):
        click(at, "sim.btn_request")
    assert at.button(key="sim.btn_request").disabled
    assert has(at, "4 live")


# ------------------------------------------------------------------ hedging


def test_flatten_delta_zeroes_net_delta_with_the_future(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    fill_first_rfq(at)
    click(at, "sim.btn_tick")
    s = desk(at).state
    delta = book_greeks_raw(s.book, s.market).delta
    click(at, "sim.btn_flat_delta")
    b = desk(at).state.book
    assert abs(book_greeks_raw(b, s.market).delta) < 1e-9
    assert b.underlying_qty == pytest.approx(-delta)
    assert readout(at, "Delta")["Hedge (underlying)"] == fmt_num(b.underlying_qty, 3)
    assert shown(at.table[-1])[0][1:] == ["FUTURE", "Δ-hedge"]


@pytest.mark.parametrize(
    ("key", "greek"), [("sim.btn_flat_vega", "vega"), ("sim.btn_flat_gamma", "gamma")]
)
def test_flatten_vega_and_gamma(app_test: AppTestFactory, key: str, greek: str) -> None:
    at = open_page(app_test)
    fill_first_rfq(at)
    click(at, key)
    s = desk(at).state
    assert len(s.book.trades) == 2
    assert abs(getattr(book_greeks_raw(s.book, s.market), greek)) < 1e-9
    assert s.book.total_costs > 0


def test_trade_ticket_executes_an_option(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    s = desk(at).state
    preview = ticket_preview(_ticket(at), s.market, 25)
    click(at, "sim.btn_execute")
    (trade,) = desk(at).state.book.trades
    assert (trade.type, trade.side, trade.quantity, trade.K) == ("call", "long", 10, 6300)
    assert trade.expiry_time == pytest.approx(60 / 365)
    assert readout(at, "P&L")["Costs paid"] == f"{MINUS}{fmt_money(preview.cost)}"
    assert has(at, "Positions (1)")


def _ticket(at: AppTest) -> Ticket:
    """The ticket as the page's widgets hold it (``current_ticket`` outside a script run)."""
    ss = at.session_state
    return Ticket(
        kind=ss[ctl.TK_KIND],
        side=ss[ctl.TK_SIDE],
        option_type=ss[ctl.TK_TYPE],
        K=float(ss[ctl.TK_K]),
        days=float(ss[ctl.TK_DAYS]),
        size=float(ss[ctl.TK_SIZE]),
        preset=ss[ctl.TK_PRESET],
        width_pct=ss[ctl.TK_WING] / 100,
    )


def test_trade_ticket_structure_and_future(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    at.button_group(key=wkey(at, ctl.TK_KIND)).set_value("structure").run()
    at.button_group(key=wkey(at, ctl.TK_PRESET)).set_value("risk-reversal").run()
    at.button_group(key=wkey(at, ctl.TK_SIDE)).set_value("short").run()
    at.number_input(key=wkey(at, ctl.TK_SIZE)).set_value(3).run()
    assert not at.exception
    assert has(at, "[net ")
    click(at, "sim.btn_execute")
    trades = desk(at).state.book.trades
    assert [(t.type, t.side, t.quantity) for t in trades] == [
        ("put", "long", 3),
        ("call", "short", 3),
    ]
    at.button_group(key=wkey(at, ctl.TK_KIND)).set_value("future").run()
    at.button_group(key=wkey(at, ctl.TK_SIDE)).set_value("long").run()
    at.number_input(key=wkey(at, ctl.TK_SIZE)).set_value(7).run()
    click(at, "sim.btn_execute")
    assert desk(at).state.book.underlying_qty == 7
    assert has(at, "[spot 6,312.45]")
    # the option fields survived the round trip through the other ticket kinds
    at.button_group(key=wkey(at, ctl.TK_KIND)).set_value("option").run()
    assert (
        at.number_input(key=wkey(at, ctl.TK_K)).value,
        at.number_input(key=wkey(at, ctl.TK_DAYS)).value,
    ) == (
        6300,
        60,
    )


# ------------------------------------------------------------------ advisor


def test_advisor_dialog_opens_and_loads_a_plan_into_the_ticket(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    fill_first_rfq(at)
    click(at, "sim.btn_tick")
    click(at, "sim.btn_advisor")
    assert at.session_state[ctl.ADVISOR_KEY] is True
    assert ADVISOR_SUBTITLE in texts(at)
    s = desk(at).state
    rv = realised_vol([h.spot for h in s.history], 1 / 252)
    advice = advise_book(s.book, s.market, rv, 25)
    assert all(any(a.title in t for t in texts(at)) for a in advice)
    plans = [a.plan for a in advice if a.plan is not None]
    assert plans
    click(at, _first_load_key(advice))
    plan = plans[0]
    assert at.session_state[ctl.ADVISOR_KEY] is False
    assert ADVISOR_SUBTITLE not in texts(at)
    expected_kind = "future" if plan.instrument == "future" else "option"
    expected_side = "long" if plan.side == "buy" else "short"
    expected_size = max(1, round(plan.quantity))
    assert at.session_state[ctl.TK_KIND] == expected_kind
    assert at.session_state[ctl.TK_SIDE] == expected_side
    assert at.session_state[ctl.TK_SIZE] == expected_size
    # the loaded fields were remounted (new generation) and the widgets SHOW the plan
    assert at.session_state[gen_key(ctl.TK_SIZE)] == 1
    assert at.number_input(key=wkey(at, ctl.TK_SIZE)).value == expected_size
    assert at.button_group(key=wkey(at, ctl.TK_SIDE)).value == expected_side
    assert at.button_group(key=wkey(at, ctl.TK_KIND)).value == expected_kind


def _first_load_key(advice: list[Any]) -> str:
    i = next(i for i, a in enumerate(advice) if a.plan is not None)
    return f"sim.load_plan_{i}"


def test_advisor_executes_the_combined_hedge(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    fill_first_rfq(at)
    click(at, "sim.btn_advisor")
    before = len(desk(at).state.book.trades)
    click(at, "sim.joint_execute")
    s = desk(at).state
    assert len(s.book.trades) == before + 2
    assert abs(book_greeks_raw(s.book, s.market).delta) < 1e-9
    assert at.session_state[ctl.ADVISOR_KEY] is False


# ------------------------------------------------------------------ session


def test_reset_starts_a_fresh_session(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    fill_first_rfq(at)
    click(at, "sim.btn_tick")
    click(at, "sim.btn_reset")
    sess = desk(at)
    s = sess.state
    assert (s.day, s.book.trades, s.queue, s.fill, s.quotes) == (0, (), (), None, 0)
    assert sess.reset_count == 1
    assert readout(at, "Spot")["Spot"] == "6,312.45"
    assert not at.success


def test_replay_mode_loads_a_window(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    at.button_group(key=wkey(at, ctl.MODE_KEY)).set_value("historical").run()
    assert not at.exception
    sess = desk(at)
    assert sess.mode == "historical"
    assert sess.window is not None
    assert sess.window.start_index == 1786
    market = readout(at, "Spot")
    assert market["Spot"] == "6,329.94"  # react_ref/4b_simulator_replay.png
    assert market["ATM vol (implied)"] == "17.52%"
    assert market["Replay day"] == "0 / 120"
    assert has(at, "2010 days on file")
    click(at, "sim.btn_tick")
    assert readout(at, "Spot")["Replay day"] == "1 / 120"
    assert desk(at).state.market.spot == sess.window.points[1].spot


def test_episode_end_disables_tick_and_auto(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    at.button_group(key=wkey(at, ctl.MODE_KEY)).set_value("historical").run()
    at.slider(key=wkey(at, ctl.REPLAY_LEN_KEY)).set_value(30).run()
    click(at, "sim.btn_reset")
    sess = desk(at)
    assert sess.replay_max == 30
    for _ in range(30):
        sess.tick()
    at.run()
    assert [_unescape(w.value) for w in at.warning] == [EPISODE_ENDED_MESSAGE]
    assert at.button(key="sim.btn_tick").disabled
    assert at.button(key="sim.btn_auto").disabled
    assert readout(at, "Spot")["Replay day"] == "30 / 30"


def test_auto_steps_the_market_on_its_timer(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    click(at, "sim.btn_auto")
    sess = desk(at)
    assert sess.playing
    assert at.button(key="sim.btn_auto").label == "Pause"
    assert sess.state.day == 0  # the first step comes one interval later
    # one interval (650 ms) later the fragment's timer reruns it: one day, client flow on
    at.session_state[ctl.LAST_AUTO_KEY] = time.monotonic() - 0.7
    at.run()
    assert desk(at).state.day == 1
    assert readout(at, "Spot")["Spot"] == fmt_money(desk(at).state.market.spot)
    click(at, "sim.btn_auto")
    assert not desk(at).playing
    assert at.button(key="sim.btn_auto").label == "Auto"


def test_auto_pauses_when_the_user_was_away(app_test: AppTestFactory) -> None:
    at = open_page(app_test)
    click(at, "sim.btn_auto")
    at.session_state[ctl.LAST_AUTO_KEY] = time.monotonic() - 60
    at.run()
    assert not desk(at).playing
    assert desk(at).state.day == 0


def test_widgets_are_sent_before_the_charts(
    app_test: AppTestFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While Auto runs, a timer run can arrive before the previous one has finished
    streaming, and widgets not yet re-sent then come back at their defaults (seen in the
    browser: the ticket's strike / tenor / size reset to their minimums). So every widget
    panel must be filled before the slow, stateless charts; the columns keep their places."""
    from eqd_desk.app.ui import simulator_panels as panels

    order: list[str] = []
    for name in (
        "market_panel",
        "scorecard_panel",
        "rfq_panel",
        "pnl_panel",
        "book_panel",
        "ticket_panel",
        "learn_panel",
    ):
        original = getattr(panels, name)

        def recorded(*args: Any, _name: str = name, _fn: Any = original, **kw: Any) -> None:
            order.append(_name)
            _fn(*args, **kw)

        monkeypatch.setattr(panels, name, recorded)
    at = open_page(app_test)
    assert order[-1] == "pnl_panel"
    assert set(order) == {
        "market_panel",
        "scorecard_panel",
        "rfq_panel",
        "pnl_panel",
        "book_panel",
        "ticket_panel",
        "learn_panel",
    }
    # the on-screen order is unchanged: the P&L panel is still the middle column
    assert len(at.columns) >= 3
    assert "P&L" in at.columns[1].markdown[0].value


def test_inputs_always_carry_their_current_value_as_default(app_test: AppTestFactory) -> None:
    """Under Auto the browser may remount a widget, which then restarts from its proto
    DEFAULT (seen in the browser: the ticket's strike / tenor / size reset to 25 / 1 / 1).
    Every simulator input is therefore created with its current value as that default, and
    a user edit never touches the canonical keys other than through the widget."""
    at = open_page(app_test)
    click(at, "sim.btn_request")  # the quote box (spread, lean) is on screen
    at.number_input(key=wkey(at, ctl.TK_K)).set_value(6400).run()
    at.number_input(key=wkey(at, ctl.TK_DAYS)).set_value(35).run()
    at.number_input(key=wkey(at, ctl.TK_SIZE)).set_value(4).run()
    at.button_group(key=wkey(at, ctl.TK_TYPE)).set_value("put").run()
    at.button_group(key=wkey(at, ctl.TK_SIDE)).set_value("short").run()
    at.slider(key=wkey(at, ctl.SPREAD_KEY)).set_value(0.1).run()
    at.slider(key=wkey(at, ctl.LEAN_KEY)).set_value(-0.01).run()
    at.slider(key=wkey(at, ctl.SPEED_KEY)).set_value(900).run()
    assert not at.exception
    ss = at.session_state
    assert (ss[ctl.TK_K], ss[ctl.TK_DAYS], ss[ctl.TK_SIZE]) == (6400, 35, 4)
    assert (ss[ctl.TK_TYPE], ss[ctl.TK_SIDE]) == ("put", "short")
    assert (ss[ctl.SPREAD_KEY], ss[ctl.LEAN_KEY], ss[ctl.SPEED_KEY]) == (0.1, -0.01, 900)
    # a remount would restore exactly these values
    numbers: tuple[tuple[str, float], ...] = ((ctl.TK_K, 6400), (ctl.TK_DAYS, 35), (ctl.TK_SIZE, 4))
    for key, value in numbers:
        assert at.number_input(key=wkey(at, key)).proto.default == value
    sliders: tuple[tuple[str, float], ...] = (
        (ctl.SPREAD_KEY, 0.1),
        (ctl.LEAN_KEY, -0.01),
        (ctl.SPEED_KEY, 900),
    )
    for key, value in sliders:
        assert list(at.slider(key=wkey(at, key)).proto.default) == [pytest.approx(value)]
    type_group = at.button_group(key=wkey(at, ctl.TK_TYPE))
    assert list(type_group.proto.default) == [1]  # "put" is option 1 of (call, put)
    assert list(at.button_group(key=wkey(at, ctl.MODE_KEY)).proto.default) == [0]
    # the ticket executes what the widgets show
    click(at, "sim.btn_execute")
    (trade,) = desk(at).state.book.trades
    assert (trade.type, trade.side, trade.quantity, trade.K) == ("put", "short", 4, 6400)
    assert trade.expiry_time == pytest.approx(35 / 365)
