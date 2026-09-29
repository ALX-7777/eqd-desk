"""Session State and widget callbacks of the simulator page.

The desk itself is one :class:`~eqd_desk.app.ui.sim_session.SimSession` kept under
:data:`SESSION_KEY`; the inputs (market mode, spread, lean, speed, replay length, the trade
ticket) keep their values under the ``sim.*`` keys below. Those are CANONICAL keys, not
widget keys: the remount-safe widgets (:mod:`~eqd_desk.app.ui.inputs`) mirror them (and are
remounted by ``set_value``), so a value survives the Auto run-boundary race described there.
Every button acts through an ``on_click`` callback here, so the change is made before the
rerun and the panels simply render the new state.

:func:`ensure_sim_state` is idempotent and runs at the top of the page, so the page works
however it is reached (navigation, deep link, or ``AppTest``).
"""

from __future__ import annotations

import time
from typing import Final, cast

import streamlit as st

from eqd_desk.app.ui import state
from eqd_desk.app.ui.format import js_round
from eqd_desk.app.ui.inputs import set_value
from eqd_desk.app.ui.sim_session import (
    DEFAULT_WINDOW_LEN,
    Mode,
    SimSession,
    Ticket,
    TicketKind,
    default_ticket,
    desk_config,
    ticket_from_plan,
)
from eqd_desk.app.ui.simulator_clock import AUTO_DEFAULT_MS, auto_stale, auto_steps
from eqd_desk.engine import OptionType
from eqd_desk.engine.presets import PresetName, round_to
from eqd_desk.engine.sim import HedgePlan
from eqd_desk.engine.strategy import LegSide

SESSION_KEY: Final = "sim.session"
"""The :class:`SimSession` (market, book, RFQs, seeded streams)."""
SPREAD_KEY: Final = "sim.spread"
"""Your quote's full bid/ask width, as a fraction of the package's gross premium."""
LEAN_KEY: Final = "sim.lean"
"""Your quote's mid shift, as a fraction of the package's gross premium."""
SPEED_KEY: Final = "sim.speed"
"""Auto speed, ms per simulated day."""
REPLAY_LEN_KEY: Final = "sim.replay_len"
"""Replay window length in trading days (applies on the next reset)."""
MODE_KEY: Final = "sim.mode"
"""The Simulated / Replay choice (mirrors ``SimSession.mode``)."""
ADVISOR_KEY: Final = "sim.advisor_open"
"""Whether the desk-advisor dialog is open."""
ADVISOR_REQUEST_KEY: Final = "sim.advisor_request"
"""One-shot: the Advisor button was just clicked (see :func:`on_open_advisor`)."""
LAST_AUTO_KEY: Final = "sim.last_auto"
"""Monotonic time (s) of the last Auto step (or of Auto being switched on)."""

TK_KIND: Final = "sim.tk_kind"
"""Trade ticket: what it sends (option, structure or future)."""
TK_SIDE: Final = "sim.tk_side"
"""Trade ticket: buy (long) or sell (short)."""
TK_TYPE: Final = "sim.tk_type"
"""Trade ticket: call or put (an option)."""
TK_K: Final = "sim.tk_K"
"""Trade ticket: strike, in index points (an option)."""
TK_DAYS: Final = "sim.tk_days"
"""Trade ticket: tenor in calendar days (an option or a structure)."""
TK_SIZE: Final = "sim.tk_size"
"""Trade ticket: size (contracts)."""
TK_PRESET: Final = "sim.tk_preset"
"""Trade ticket: the preset structure."""
TK_WING: Final = "sim.tk_wing"
"""Trade ticket: a structure's wing, in % of spot."""

DEFAULT_SPREAD: Final = 0.05
"""Opening quote width (5 % of gross premium)."""
DEFAULT_LEAN: Final = 0.0
"""Opening lean (a quote centred on fair value)."""


def ensure_sim_state() -> SimSession:
    """Create the desk and every ``sim.*`` key on first use (idempotent); return the desk."""
    cfg = desk_config(state.snapshot())
    sess = state.ensure_lazy(SESSION_KEY, lambda: SimSession(cfg, state.history().series))
    tk = default_ticket(cfg)
    state.ensure_state(
        {
            SPREAD_KEY: DEFAULT_SPREAD,
            LEAN_KEY: DEFAULT_LEAN,
            SPEED_KEY: AUTO_DEFAULT_MS,
            REPLAY_LEN_KEY: DEFAULT_WINDOW_LEN,
            MODE_KEY: sess.mode,
            ADVISOR_KEY: False,
            LAST_AUTO_KEY: 0.0,
            TK_KIND: tk.kind,
            TK_SIDE: tk.side,
            TK_TYPE: tk.option_type,
            TK_K: js_round(tk.K),
            TK_DAYS: int(tk.days),
            TK_SIZE: int(tk.size),
            TK_PRESET: tk.preset,
            TK_WING: js_round(tk.width_pct * 100),
        }
    )
    return sess


def session() -> SimSession:
    """The desk of this browser session (call :func:`ensure_sim_state` first)."""
    return cast("SimSession", st.session_state[SESSION_KEY])


def speed_ms() -> float:
    """The Auto speed (ms per day)."""
    return float(st.session_state[SPEED_KEY])


def replay_len() -> int:
    """The replay window length (days)."""
    return int(st.session_state[REPLAY_LEN_KEY])


def advisor_open() -> bool:
    """Whether the advisor dialog should be shown."""
    return bool(st.session_state.get(ADVISOR_KEY, False))


def current_ticket() -> Ticket:
    """The trade ticket as the widgets hold it."""
    ss = st.session_state
    return Ticket(
        kind=cast("TicketKind", ss[TK_KIND]),
        side=cast("LegSide", ss[TK_SIDE]),
        option_type=cast("OptionType", ss[TK_TYPE]),
        K=float(ss[TK_K]),
        days=float(ss[TK_DAYS]),
        size=float(ss[TK_SIZE]),
        preset=cast("PresetName", ss[TK_PRESET]),
        width_pct=int(ss[TK_WING]) / 100,
    )


def clock() -> float:
    """The Auto clock, in seconds (``time.monotonic``). Everything that reads the time goes
    through here, so a test can replace it and drive Auto deterministically."""
    return time.monotonic()


def pause_if_stale(now: float | None = None) -> None:
    """Pause Auto when it has been silent for several intervals (the user left the page;
    React pauses Auto on navigation). Called on the page's full runs."""
    sess = session()
    t = clock() if now is None else now
    if sess.playing and auto_stale(t, float(st.session_state[LAST_AUTO_KEY]), speed_ms()):
        sess.set_playing(False)


# ------------------------------------------------------------------ callbacks: the market


MULTI_TICK_DAYS: Final = 5
"""Days the "5 days" button advances (a trading week of Ticks)."""


def on_tick() -> None:
    """Tick: one day, no new client flow."""
    session().tick()


def on_multi_tick() -> None:
    """ "5 days": :data:`MULTI_TICK_DAYS` Ticks at once (no new client flow), stopping at the
    end of a replay episode. Streamlit merges rapid clicks on Tick while a run is in
    flight, so this is the reliable way to move several days without Auto."""
    sess = session()
    for _ in range(MULTI_TICK_DAYS):
        if not sess.tick():
            break


def on_toggle_auto() -> None:
    """Auto / Pause. The first Auto step comes one interval after switching on."""
    sess = session()
    sess.set_playing(not sess.playing)
    st.session_state[LAST_AUTO_KEY] = clock()


def recentre_ticket_strike() -> None:
    """Put the trade ticket's strike back at the money (spot on the strike grid). A fresh
    session can start far from the last one (a replay window opens wherever history was),
    and a strike left behind would price a deep in- or out-of-the-money option."""
    sess = session()
    atm = js_round(round_to(sess.state.market.spot, sess.cfg.strike_step))
    if st.session_state.get(TK_K) != atm:
        set_value(TK_K, atm)


def on_reset() -> None:
    """Reset session (a new window in Replay, with the current replay length); the ticket's
    strike goes back to the money."""
    session().reset(replay_len())
    recentre_ticket_strike()


def on_mode() -> None:
    """Simulated / Replay: switching always starts a fresh session (strike back to the
    money, as on Reset)."""
    mode = cast("Mode", st.session_state[MODE_KEY])
    sess = session()
    if mode != sess.mode:
        sess.switch_mode(mode, replay_len())
        recentre_ticket_strike()


def auto_step(now: float | None = None) -> int:
    """The Auto steps that are due (see :func:`~eqd_desk.app.ui.simulator_clock.auto_steps`);
    returns how many days the market moved (0 when Auto is off or nothing is due)."""
    sess = session()
    if not sess.playing:
        return 0
    t = clock() if now is None else now
    steps, last = auto_steps(t, float(st.session_state[LAST_AUTO_KEY]), speed_ms())
    st.session_state[LAST_AUTO_KEY] = last
    moved = 0
    for _ in range(steps):
        if not sess.auto_tick():
            break
        moved += 1
    return moved


# ------------------------------------------------------------------ callbacks: client flow


def on_request() -> None:
    """Request a quote from a client."""
    session().request_rfq()


def on_select(rfq_id: int) -> None:
    """Put an RFQ in the quote box."""
    session().select_rfq(rfq_id)


def on_quote() -> None:
    """Quote the selected RFQ with the current spread and lean."""
    ss = st.session_state
    session().quote(float(ss[SPREAD_KEY]), float(ss[LEAN_KEY]))


def on_pass() -> None:
    """Pass on the selected RFQ."""
    session().pass_rfq()


# ------------------------------------------------------------------ callbacks: hedging


def on_flatten_delta() -> None:
    """Flatten Δ with the future."""
    session().flatten_delta()


def on_flatten_vega() -> None:
    """Flatten vega with a 60-day ATM call."""
    session().flatten_vega()


def on_flatten_gamma() -> None:
    """Flatten gamma with a 60-day ATM call."""
    session().flatten_gamma()


def on_execute_ticket() -> None:
    """Execute the trade ticket at market."""
    session().execute_ticket(current_ticket())


def set_ticket(tk: Ticket) -> None:
    """Write a ticket into the trade ticket (from a callback): each field that changes is
    set with :func:`~eqd_desk.app.ui.inputs.set_value`, which remounts its widget
    with the new value."""
    fields: tuple[tuple[str, object], ...] = (
        (TK_KIND, tk.kind),
        (TK_SIDE, tk.side),
        (TK_TYPE, tk.option_type),
        (TK_K, js_round(tk.K)),
        (TK_DAYS, int(tk.days)),
        (TK_SIZE, int(tk.size)),
        (TK_PRESET, tk.preset),
        (TK_WING, js_round(tk.width_pct * 100)),
    )
    for key, value in fields:
        if st.session_state.get(key) != value:
            set_value(key, value)


# ------------------------------------------------------------------ callbacks: advisor


def on_open_advisor() -> None:
    """Open the desk advisor, pausing Auto.

    The dialog is drawn by the PAGE, outside the Auto fragment: drawn inside it, every timer
    run redrew it, racing its own buttons (a close that reopened, a plan that never loaded),
    and opening it as Auto switched off could crash the browser app ("Cannot set a node at
    a delta path"). The button sits in the fragment, so its click reruns only the desk;
    :data:`ADVISOR_REQUEST_KEY` asks that run for the full-app rerun that draws the dialog
    (:func:`take_advisor_request`). Auto is paused so nothing moves behind the dialog and its
    overlay never hides a running clock (React keeps Auto running, but its overlay covers
    Pause too)."""
    session().set_playing(False)
    st.session_state[ADVISOR_KEY] = True
    st.session_state[ADVISOR_REQUEST_KEY] = True


def take_advisor_request() -> bool:
    """Whether the advisor was just opened from the desk (and forget it): the desk run then
    reruns the whole app so the page draws the dialog. One-shot, so the full run that follows
    does not rerun again."""
    return bool(st.session_state.pop(ADVISOR_REQUEST_KEY, False))


def on_close_advisor() -> None:
    """Close the desk advisor (its ✕, Esc or a click outside)."""
    st.session_state[ADVISOR_KEY] = False


def on_load_plan(plan: HedgePlan) -> None:
    """Load an advisor plan into the trade ticket (review the size, then execute)."""
    set_ticket(ticket_from_plan(current_ticket(), plan))
    st.session_state[ADVISOR_KEY] = False


def on_execute_joint() -> None:
    """Execute the combined hedge (two options, then the future last)."""
    session().execute_joint()
    st.session_state[ADVISOR_KEY] = False


__all__ = [
    "ADVISOR_KEY",
    "ADVISOR_REQUEST_KEY",
    "LAST_AUTO_KEY",
    "LEAN_KEY",
    "MODE_KEY",
    "MULTI_TICK_DAYS",
    "REPLAY_LEN_KEY",
    "SESSION_KEY",
    "SPEED_KEY",
    "SPREAD_KEY",
    "TK_DAYS",
    "TK_K",
    "TK_KIND",
    "TK_PRESET",
    "TK_SIDE",
    "TK_SIZE",
    "TK_TYPE",
    "TK_WING",
    "advisor_open",
    "auto_step",
    "clock",
    "current_ticket",
    "ensure_sim_state",
    "on_close_advisor",
    "on_execute_joint",
    "on_execute_ticket",
    "on_flatten_delta",
    "on_flatten_gamma",
    "on_flatten_vega",
    "on_load_plan",
    "on_mode",
    "on_multi_tick",
    "on_open_advisor",
    "on_pass",
    "on_quote",
    "on_request",
    "on_reset",
    "on_select",
    "on_tick",
    "on_toggle_auto",
    "pause_if_stale",
    "recentre_ticket_strike",
    "replay_len",
    "session",
    "set_ticket",
    "speed_ms",
    "take_advisor_request",
]
