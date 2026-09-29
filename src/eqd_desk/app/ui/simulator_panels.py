"""The trading simulator's panels: the React ``SimulatorView`` terminal, in Streamlit.

Three columns, like the React layout:

- left: **Market** (Simulated / Replay, spot, implied and realised vol, skew or replay day,
  Auto speed, Tick / Auto, Reset), **Desk scorecard**, **Client RFQs** (the queue, the quote
  box with spread and lean, Quote / Pass, Request a quote, the fill line);
- centre: **P&L** (the mark-to-market hero, P&L over time, the cumulative P&L explain, the
  spot & vol path);
- right: **Book & hedging** (net greeks, the three flatten buttons, positions, the desk
  advisor), **Trade ticket** (option / structure / future), **Learn**.

:func:`live_desk` is the body of the page's ``@st.fragment(run_every=…)``: while Auto is on
it reruns on a timer and steps the market (see :mod:`~eqd_desk.app.ui.simulator_clock`), and
any click inside it reruns only the desk, never the app header. The desk advisor
(:func:`advisor_dialog`) is drawn by the page itself, outside that fragment.

The text comes from :mod:`~eqd_desk.app.ui.simulator_display` (the React text) and
:mod:`eqd_desk.content.simulator` (the teaching content, and the tooltips this Streamlit UI
adds), through ``markdown_safe``; the panels themselves hold only control labels and
icons. Every action is a callback of :mod:`~eqd_desk.app.ui.simulator_controls`. Every input
is one of the shared remount-safe widgets (:mod:`~eqd_desk.app.ui.widgets` over
:mod:`~eqd_desk.app.ui.inputs`), so the Auto loop's back-to-back reruns never reset a
value.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

import altair as alt
import pandas as pd
import streamlit as st

from eqd_desk.app.ui import charts, theme
from eqd_desk.app.ui import simulator_controls as ctl
from eqd_desk.app.ui import simulator_display as disp
from eqd_desk.app.ui.education import attribution_terms, learn_header, sim_concepts
from eqd_desk.app.ui.format import THUMB_PERCENT, fmt_signed_money, sign_class
from eqd_desk.app.ui.inputs import steady_number
from eqd_desk.app.ui.readout import ReadoutRow
from eqd_desk.app.ui.sim_session import (
    MAX_QUEUE,
    CumAttribution,
    HistPoint,
    Mode,
    SimSession,
    TicketKind,
    quote_preview,
    ticket_preview,
    ticket_priceable,
)
from eqd_desk.app.ui.simulator_charts import explain_chart, path_chart, pnl_chart
from eqd_desk.app.ui.simulator_clock import AUTO_MAX_MS, AUTO_MIN_MS, AUTO_STEP_MS, auto_interval
from eqd_desk.app.ui.strategy_builder_legs import PRESET_LABELS
from eqd_desk.app.ui.strategy_builder_state import WING_MAX_PCT
from eqd_desk.app.ui.theme import Tone
from eqd_desk.app.ui.widgets import (
    BadgeColor,
    choice,
    hero_number,
    md_color,
    number_slider,
    option_type_toggle,
    readout_table,
    section_header,
    sub_heading,
)
from eqd_desk.content import markdown_safe
from eqd_desk.content.simulator import (
    ADVISOR_HELP,
    ADVISOR_SUBTITLE,
    AUTO_HELP,
    AUTO_SPEED_HELP,
    EMPTY_BOOK_HINT,
    EMPTY_QUEUE_HINT,
    EPISODE_ENDED_MESSAGE,
    FLATTEN_LABEL,
    JOINT_HEDGE_SUBTITLE,
    JOINT_HEDGE_TITLE,
    LEAN_HELP,
    MULTI_TICK_HELP_TEMPLATE,
    OPTION_HEDGE_CAPTION,
    REPLAY_LENGTH_HINT,
    SPREAD_HELP,
    TICK_HELP,
    TICKET_UNPRICEABLE_HINT,
)
from eqd_desk.engine.sim import (
    RFQ,
    Advice,
    BookGreeks,
    advise_book,
    book_greeks,
    book_value,
    realised_vol,
    rfq_fair,
    rfq_risk_impact,
)
from eqd_desk.engine.strategy import LegSide

MODE_LABELS: Final[dict[Mode, str]] = {"simulated": "Simulated", "historical": "Replay"}
"""Labels of the market-mode control."""
KIND_LABELS: Final[dict[TicketKind, str]] = {
    "option": "Option",
    "structure": "Structure",
    "future": "Future",
}
"""Labels of the trade ticket's kind control (the structures are the strategy builder's
presets, :data:`~eqd_desk.app.ui.strategy_builder_legs.PRESET_LABELS`)."""
SIDE_LABELS: Final[dict[LegSide, str]] = {"long": "Buy", "short": "Sell"}
"""Labels of the trade ticket's side control."""

COLUMN_WIDTHS: Final = (1.05, 2.0, 1.15)
"""Left / centre / right column ratio (the React grid is ~365 / 825 / 360 px at 1600 px)."""


@dataclass(frozen=True, slots=True)
class DeskView:
    """What every panel needs from the desk, computed once per run."""

    greeks: BookGreeks
    pnl: float
    """Mark-to-market P&L (= book value; it starts at 0)."""
    realised: float | None
    """Annualised realised vol of the session's spot path (None before 3 points)."""


def desk_view(sess: SimSession) -> DeskView:
    """Net greeks, P&L and realised vol of the current desk."""
    s = sess.state
    return DeskView(
        greeks=book_greeks(s.book, s.market),
        pnl=book_value(s.book, s.market),
        realised=realised_vol([h.spot for h in s.history], sess.cfg.params.dt),
    )


# ------------------------------------------------------------------ small tables


def stat_table(lines: Sequence[disp.StatLine], units: Sequence[str] | None = None) -> None:
    """A "label · value [· unit]" readout (the React ``.sim-stats`` / book table), each value
    :func:`~eqd_desk.app.ui.simulator_display.settled` (no minus sign or colour on a zero, a
    grey dash for a missing value); a line without a tone prints its value in the body
    colour."""
    shown = [disp.settled(ln) for ln in lines]
    unit_of = list(units) if units is not None else [""] * len(shown)
    readout_table(
        [
            ReadoutRow(ln.label, text=ln.text, unit=unit, tone=ln.tone or "text")
            for ln, unit in zip(shown, unit_of, strict=True)
        ]
    )


def blotter_table(rows: Sequence[disp.BlotterRow]) -> None:
    """The positions blotter: signed size (green long / red short), instrument, days left."""
    frame = pd.DataFrame(
        {
            "qty": [r.qty for r in rows],
            "instrument": [r.instrument for r in rows],
            "note": [r.note for r in rows],
        }
    )
    mono = (
        f"font-family: {theme.MONO_FONT}; font-variant-numeric: tabular-nums; white-space: nowrap"
    )

    def styles(frame: pd.DataFrame) -> pd.DataFrame:
        cells = [
            [
                f"{mono}; font-weight: 600; color: {theme.TONE_COLORS[r.tone]}",
                f"{mono}; color: {theme.TEXT}",
                f"{mono}; color: {theme.TEXT_DIM}; text-align: right",
            ]
            for r in rows
        ]
        return pd.DataFrame(cells, index=frame.index, columns=frame.columns)

    styler = frame.style.hide(axis="index").apply(styles, axis=None)
    st.table(styler, border="horizontal", hide_index=True, hide_header=True)


# ------------------------------------------------------------------ left column


def market_panel(sess: SimSession, view: DeskView) -> None:
    """Market mode, the market readout, Auto speed, Tick / Auto and Reset."""
    with st.container(border=True):
        slot = section_header("Market", icon=":material/monitoring:")
        with slot:
            choice(
                "Market mode",
                MODE_LABELS,
                key=ctl.MODE_KEY,
                default="simulated",
                on_change=ctl.on_mode,
            )
        stat_table(disp.market_stats(sess.state, sess.mode, view.realised, sess.replay_max))
        if sess.mode == "historical":
            st.caption(markdown_safe(disp.grouped_replay_caption(len(sess.series))))
            number_slider(
                "Replay length",
                key=ctl.REPLAY_LEN_KEY,
                min_value=30,
                max_value=504,
                step=6,
                integer=True,
                display=disp.days_text,
                slider_format="%d d",
                compact=True,
            )
            st.caption(markdown_safe(REPLAY_LENGTH_HINT))
        if sess.at_end:
            st.warning(markdown_safe(EPISODE_ENDED_MESSAGE), icon=":material/flag:")
        number_slider(
            "Auto speed",
            key=ctl.SPEED_KEY,
            min_value=AUTO_MIN_MS,
            max_value=AUTO_MAX_MS,
            step=AUTO_STEP_MS,
            integer=True,
            display=disp.speed_text,
            slider_format="%d ms",
            compact=True,
            help=AUTO_SPEED_HELP,
        )
        with st.container(horizontal=True, gap="small"):
            st.button(
                "Tick",
                key="sim.btn_tick",
                icon=":material/skip_next:",
                on_click=ctl.on_tick,
                disabled=sess.at_end,
                width="stretch",
                help=markdown_safe(TICK_HELP),
            )
            st.button(
                f"{ctl.MULTI_TICK_DAYS} days",
                key="sim.btn_tick_many",
                icon=":material/keyboard_double_arrow_right:",
                on_click=ctl.on_multi_tick,
                disabled=sess.at_end,
                width="stretch",
                help=markdown_safe(MULTI_TICK_HELP_TEMPLATE.format(days=ctl.MULTI_TICK_DAYS)),
            )
        # the clock on its own full-width row: three buttons do not fit the left column on
        # one line at every width
        st.button(
            "Pause" if sess.playing else "Auto",
            key="sim.btn_auto",
            icon=":material/pause:" if sess.playing else ":material/fast_forward:",
            type="primary" if sess.playing else "secondary",
            on_click=ctl.on_toggle_auto,
            disabled=sess.at_end,
            width="stretch",
            help=markdown_safe(AUTO_HELP),
        )
        st.button(
            "Reset session",
            key="sim.btn_reset",
            icon=":material/restart_alt:",
            on_click=ctl.on_reset,
            width="stretch",
        )


def scorecard_panel(sess: SimSession, view: DeskView) -> None:
    """P&L, edge, costs, fill rate and the two risk flags."""
    with st.container(border=True):
        section_header("Desk scorecard", icon=":material/scoreboard:")
        stat_table(disp.scorecard(sess.state, view.greeks, view.pnl))


def chip_label(chip: disp.RfqChip) -> str:
    """Button label of a queue RFQ: ``▲ 100× Put · 273.87 ↓``, the client's side in green
    (buys) or red (sells), the risk flag green (cuts your risk) or orange (adds risk)."""
    arrow = md_color(chip.arrow, "pos" if chip.arrow == disp.BUY_ARROW else "neg")
    text = f"{arrow} {markdown_safe(chip.text)} · {markdown_safe(chip.net)}"
    if not chip.flag:
        return text
    return f"{text} {md_color(chip.flag, 'pos' if chip.verdict == 'hedges' else 'put')}"


IMPACT_TONES: Final[dict[str, Tone]] = {"hedges": "pos", "adds": "put", "neutral": "dim"}
"""Colour of the RFQ risk note."""


def quote_box(sess: SimSession, rfq: RFQ) -> None:
    """The selected RFQ: its package, the risk note, your spread and lean, the resulting
    bid / ask, and Quote / Pass."""
    s = sess.state
    fair = rfq_fair(rfq, s.market)
    impact = rfq_risk_impact(rfq, s.book, s.market)
    with st.container(border=True):
        st.caption(markdown_safe(disp.rfq_detail(rfq, fair.net)))
        note = md_color(markdown_safe(disp.impact_text(impact)), IMPACT_TONES[impact.verdict])
        st.markdown(f":small[{note}]")
        spread = number_slider(
            "Your spread",
            key=ctl.SPREAD_KEY,
            min_value=0.005,
            max_value=0.2,
            step=0.005,
            display=disp.spread_text,
            slider_format=THUMB_PERCENT,
            compact=True,
            help=SPREAD_HELP,
        )
        lean = number_slider(
            "Lean (skew your price)",
            key=ctl.LEAN_KEY,
            min_value=-0.03,
            max_value=0.03,
            step=0.0025,
            display=disp.lean_text,
            slider_format=THUMB_PERCENT,
            compact=True,
            help=LEAN_HELP,
        )
        bid, ask = disp.bid_ask_text(quote_preview(fair.net, fair.gross, spread, lean))
        with st.container(horizontal=True, horizontal_alignment="distribute"):
            st.markdown(f":green[**{markdown_safe(bid)}**]", width="content")
            st.markdown(f":red[**{markdown_safe(ask)}**]", width="content")
        with st.container(horizontal=True, gap="small"):
            st.button(
                "Quote",
                key="sim.btn_quote",
                type="primary",
                icon=":material/swap_horiz:",
                on_click=ctl.on_quote,
                width="stretch",
            )
            st.button("Pass", key="sim.btn_pass", on_click=ctl.on_pass, width="stretch")


def rfq_panel(sess: SimSession) -> None:
    """The client RFQ queue, the quote box, Request a quote and the last fill."""
    s = sess.state
    with st.container(border=True):
        section_header(
            "Client RFQs", icon=":material/forum:", badge=f"{len(s.queue)} live", badge_color="gray"
        )
        if not s.queue:
            st.caption(markdown_safe(EMPTY_QUEUE_HINT))
        for r in s.queue:
            chip = disp.rfq_chip(
                r, rfq_fair(r, s.market).net, rfq_risk_impact(r, s.book, s.market).verdict
            )
            selected = r.id == s.selected_id
            st.button(
                chip_label(chip),
                key=f"sim.rfq_{r.id}",
                icon=":material/radio_button_checked:"
                if selected
                else ":material/radio_button_unchecked:",
                on_click=ctl.on_select,
                args=(r.id,),
                width="stretch",
                help=markdown_safe(chip.hint) if chip.hint else None,
            )
        sel = s.selected
        if sel is not None:
            quote_box(sess, sel)
        st.button(
            "Request a quote",
            key="sim.btn_request",
            icon=":material/arrow_forward:",
            icon_position="right",
            on_click=ctl.on_request,
            disabled=len(s.queue) >= MAX_QUEUE,
            width="stretch",
        )
        if s.fill is not None:
            if s.fill.won:
                st.success(markdown_safe(s.fill.msg), icon=":material/check_circle:")
            else:
                st.warning(markdown_safe(s.fill.msg), icon=":material/call_missed:")


# ------------------------------------------------------------------ centre column


CHART_MEMO_KEY: Final = "sim.chart_memo"
"""Per-session memo of the three charts (see :func:`desk_charts`)."""


@dataclass(frozen=True, slots=True)
class _ChartMemo:
    history: tuple[HistPoint, ...]
    cum_attr: CumAttribution
    currency: str
    charts: tuple[alt.LayerChart, alt.LayerChart, alt.LayerChart]


def desk_charts(sess: SimSession) -> tuple[alt.LayerChart, alt.LayerChart, alt.LayerChart]:
    """The P&L, P&L-explain and spot & vol charts of the desk, rebuilt only when the market
    has moved. ``SimState.history`` and ``cum_attr`` are immutable and replaced only by a
    market step, so an identity check is an exact change test: a quote, a hedge or a slider
    move reuses the charts (building them is most of a rerun's cost)."""
    s = sess.state
    currency = sess.cfg.currency
    memo = st.session_state.get(CHART_MEMO_KEY)
    if (
        isinstance(memo, _ChartMemo)
        and memo.history is s.history
        and memo.cum_attr is s.cum_attr
        and memo.currency == currency
    ):
        return memo.charts
    built = (
        pnl_chart(s.history, currency),
        explain_chart(s.cum_attr, currency),
        path_chart(s.history),
    )
    st.session_state[CHART_MEMO_KEY] = _ChartMemo(s.history, s.cum_attr, currency, built)
    return built


TREND_BADGES: Final[dict[disp.PnlTrend, tuple[BadgeColor, str]]] = {
    "up": ("green", ":material/trending_up:"),
    "down": ("red", ":material/trending_down:"),
    "flat": ("gray", ":material/trending_flat:"),
}
"""Colour and icon of the P&L panel's badge."""


def pnl_panel(sess: SimSession, view: DeskView) -> None:
    """The P&L hero, P&L over time, the cumulative P&L explain and the spot & vol path."""
    s = sess.state
    currency = sess.cfg.currency
    with st.container(border=True):
        trend = disp.pnl_trend(view.pnl)
        colour, icon = TREND_BADGES[trend]
        section_header(
            "P&L", icon=":material/show_chart:", badge=trend, badge_color=colour, badge_icon=icon
        )
        caption = disp.pnl_caption(currency)
        value, tone = disp.settled_value(fmt_signed_money(view.pnl), sign_class(view.pnl))
        hero_number(
            caption[:1].upper() + caption[1:],
            value,
            detail=disp.edge_costs_text(s.book),
            tone=tone,
        )
        pnl, explain, path = desk_charts(sess)
        charts.show_chart(pnl, key="sim.chart_pnl")
        sub_heading("P&L explain (cumulative)")
        charts.show_chart(explain, key="sim.chart_explain")
        sub_heading("Spot & vol path")
        charts.show_chart(path, key="sim.chart_path")


# ------------------------------------------------------------------ right column


FLATTEN_BUTTONS: Final[tuple[tuple[str, disp.FlattenTarget, str, Callable[[], None]], ...]] = (
    ("Δ", "delta", "sim.btn_flat_delta", ctl.on_flatten_delta),
    ("Vega", "vega", "sim.btn_flat_vega", ctl.on_flatten_vega),
    ("Γ", "gamma", "sim.btn_flat_gamma", ctl.on_flatten_gamma),
)
"""The hedge buttons after the "Flatten" label: label (the greek), target greek, key,
callback. One word each, so the row stays on one line in the narrow right column at every
width (React's "Flatten vega (opt)" wraps unevenly); the caption under the row names the
instruments and each tooltip spells out the trade and its cost."""


def book_panel(sess: SimSession, view: DeskView) -> None:
    """Net greeks, the hedge buttons, the positions blotter and the advisor button."""
    s = sess.state
    with st.container(border=True):
        slot = section_header("Book & hedging", icon=":material/account_balance:")
        with slot:
            st.button(
                "Advisor",
                key="sim.btn_advisor",
                icon=":material/lightbulb:",
                on_click=ctl.on_open_advisor,
                help=markdown_safe(ADVISOR_HELP),
            )
        stat_table(
            disp.book_rows(view.greeks, s.book.underlying_qty),
            units=disp.book_units(sess.cfg.currency),
        )
        st.caption(markdown_safe(disp.tick_theta_caption(sess.cfg.params.dt)))
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.markdown(f":small[:gray[**{markdown_safe(FLATTEN_LABEL)}**]]", width="content")
            for label, target, key, action in FLATTEN_BUTTONS:
                st.button(
                    label,
                    key=key,
                    on_click=action,
                    width="stretch",
                    help=markdown_safe(disp.flatten_help(target)),
                )
        st.caption(markdown_safe(f"{disp.flatten_instruments()} {OPTION_HEDGE_CAPTION}"))
        sub_heading(disp.positions_heading(s.book))
        rows = disp.blotter_rows(s.book, s.market)
        if rows:
            blotter_table(rows)
        else:
            st.caption(markdown_safe(EMPTY_BOOK_HINT))


def ticket_panel(sess: SimSession) -> None:
    """The trade ticket: an option, a preset structure or the future, at market."""
    s = sess.state
    step = int(sess.cfg.strike_step)
    with st.container(border=True):
        section_header("Trade ticket", icon=":material/receipt_long:")
        kind = choice("Ticket kind", KIND_LABELS, key=ctl.TK_KIND, default="option")
        if kind == "structure":
            choice("Structure", PRESET_LABELS, key=ctl.TK_PRESET, default="straddle", kind="pills")
        with st.container(horizontal=True, gap="small"):
            choice("Side", SIDE_LABELS, key=ctl.TK_SIDE, default="long")
            if kind == "option":
                option_type_toggle(key=ctl.TK_TYPE)
        cols = st.columns(3 if kind != "future" else 1, gap="small")
        if kind == "option":
            with cols[0]:
                steady_number("Strike", key=ctl.TK_K, min_value=step, step=step)
        elif kind == "structure":
            with cols[0]:
                # the strategy builder's cap: a wider iron condor has a strike at or below 0
                steady_number(
                    "Wing %", key=ctl.TK_WING, min_value=1, max_value=WING_MAX_PCT, step=1
                )
        if kind != "future":
            with cols[1]:
                steady_number("Exp (d)", key=ctl.TK_DAYS, min_value=1, max_value=3650, step=5)
        with cols[-1]:
            steady_number("Size", key=ctl.TK_SIZE, min_value=1, step=1)
        ticket = ctl.current_ticket()
        priceable = ticket_priceable(ticket, s.market, sess.cfg.strike_step)
        if priceable:
            preview = ticket_preview(ticket, s.market, sess.cfg.strike_step)
            left, _ = disp.ticket_preview_text(preview)
            right, tone = disp.ticket_cost_view(preview)
            with st.container(horizontal=True, horizontal_alignment="distribute"):
                st.markdown(f":gray[{markdown_safe(left)}]", width="content")
                st.markdown(md_color(markdown_safe(right), tone), width="content")
        else:
            st.caption(markdown_safe(TICKET_UNPRICEABLE_HINT))
        st.button(
            "Execute @ market",
            key="sim.btn_execute",
            type="primary",
            icon=":material/bolt:",
            on_click=ctl.on_execute_ticket,
            disabled=not priceable,
            width="stretch",
        )


def learn_panel() -> None:
    """The market-making concepts and how to read each P&L-explain term, one expander each
    (the column stays short and every term is one click away)."""
    with st.container(border=True):
        learn_header(badge="market-making")
        sim_concepts()
        with st.expander("P&L explain terms", icon=":material/functions:"):
            attribution_terms(heading=None)


# ------------------------------------------------------------------ advisor


def _advice_card(i: int, a: Advice) -> None:
    with st.container(border=True):
        st.markdown(f"{disp.severity_marker(a.severity)} **{markdown_safe(a.title)}**")
        st.markdown(markdown_safe(a.detail))
        if a.plan is None:
            return
        side, text = disp.plan_line(a.plan)
        colour = "green" if a.plan.side == "buy" else "red"
        st.markdown(f":{colour}-badge[{side}] `{text}`")
        st.caption(markdown_safe(a.plan.rationale))
        st.button(
            "Load into ticket",
            key=f"sim.load_plan_{i}",
            type="primary",
            icon=":material/arrow_forward:",
            icon_position="right",
            on_click=ctl.on_load_plan,
            args=(a.plan,),
        )


@st.dialog(
    "Desk advisor", width="large", icon=":material/lightbulb:", on_dismiss=ctl.on_close_advisor
)
def advisor_dialog() -> None:
    """Ranked advice on the live book, each with a concrete hedge you can load into the
    ticket, and the combined hedge when both gamma and vega are exposed. The page draws it,
    OUTSIDE the desk fragment, while the advisor is open (see
    :func:`~eqd_desk.app.ui.simulator_controls.on_open_advisor`).

    A click in the dialog reruns only the dialog. Its two actions ("Load into ticket",
    "Execute combined hedge") close the advisor in their callbacks, so the dialog run that
    follows finds it closed and reruns the whole app: the dialog goes and the desk behind
    it shows the new book and ticket. (Checking here, rather than after each button, still
    works when the action changed the cards so that its button is not drawn again: after
    the combined hedge the book no longer needs one.)"""
    if not ctl.advisor_open():
        st.rerun()
    sess = ctl.session()
    s = sess.state
    view = desk_view(sess)
    st.caption(markdown_safe(ADVISOR_SUBTITLE))
    for i, a in enumerate(advise_book(s.book, s.market, view.realised, sess.cfg.strike_step)):
        _advice_card(i, a)
    jh = sess.joint()
    if not disp.show_joint(jh, view.greeks):
        return
    with st.container(border=True):
        st.markdown(
            f":primary[:material/balance:] **{markdown_safe(JOINT_HEDGE_TITLE)}** "
            f":gray[{markdown_safe(JOINT_HEDGE_SUBTITLE)}]"
        )
        for leg in jh.legs:
            side, text, role = disp.joint_leg_line(leg)
            colour = "green" if leg.side == "buy" else "red"
            st.markdown(f":{colour}-badge[{side}] `{text}` :gray[{markdown_safe(role)}]")
        st.caption(markdown_safe(jh.rationale))
        st.button(
            "Execute combined hedge",
            key="sim.joint_execute",
            type="primary",
            icon=":material/arrow_forward:",
            icon_position="right",
            on_click=ctl.on_execute_joint,
        )


# ------------------------------------------------------------------ the live desk


def live_desk(registered: float | None) -> None:
    """The fragment body: one Auto step when due, then the three columns. ``registered`` is
    the fragment's ``run_every``; when Auto was switched or its speed changed the app reruns
    once to register the new timer, and when the Advisor was just clicked it reruns once so
    the page draws the dialog (outside this fragment, see
    :func:`~eqd_desk.app.ui.simulator_controls.on_open_advisor`).

    The columns are FILLED left, right, then centre: every widget is sent before the charts,
    which are most of a run's cost (~250 ms after a market step). While Auto runs, the next
    timer run can arrive before the current one has finished streaming; widgets not yet
    re-sent at that point lose their browser-side state and come back at their defaults (the
    trade ticket's strike, tenor and size would reset to their minimums). Charts are stateless,
    so they go last. The on-screen order (and the phone stacking) is the column order.
    """
    sess = ctl.session()
    if registered is not None:
        ctl.auto_step()
    advisor_requested = ctl.take_advisor_request()
    if advisor_requested or auto_interval(sess.playing, ctl.speed_ms()) != registered:
        st.rerun()
    view = desk_view(sess)
    left, centre, right = st.columns(COLUMN_WIDTHS, gap="small")
    with left:
        market_panel(sess, view)
        scorecard_panel(sess, view)
        rfq_panel(sess)
    with right:
        book_panel(sess, view)
        ticket_panel(sess)
        learn_panel()
    with centre:
        pnl_panel(sess, view)


__all__ = [
    "COLUMN_WIDTHS",
    "DeskView",
    "advisor_dialog",
    "blotter_table",
    "book_panel",
    "chip_label",
    "desk_charts",
    "desk_view",
    "learn_panel",
    "live_desk",
    "market_panel",
    "pnl_panel",
    "quote_box",
    "rfq_panel",
    "scorecard_panel",
    "stat_table",
    "ticket_panel",
]
