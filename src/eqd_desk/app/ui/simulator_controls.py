"""Session State and widget callbacks of the simulator page.

The desk itself is one :class:`~eqd_desk.app.ui.sim_session.SimSession` kept under
:data:`SESSION_KEY`; the inputs (market mode, spread, lean, speed, replay length, the trade
ticket) keep their values under the ``sim.*`` keys below. Those are CANONICAL keys, not
widget keys: the widgets of :mod:`~eqd_desk.app.ui.simulator_inputs` mirror them (and are
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
from eqd_desk.app.ui.simulator_inputs import set_value
from eqd_desk.engine.presets import PresetName
from eqd_desk.engine.sim import HedgePlan
from eqd_desk.engine.strategy import LegSide
from eqd_desk.engine.types import OptionType

SESSION_KEY: Final = "sim.session"
"""The :class:`SimSession` (market, book, RFQs, seeded streams)."""
SPREAD_KEY: Final = "sim.spread"
LEAN_KEY: Final = "sim.lean"
"""Your quote: full width and mid shift, as fractions of the package's gross premium."""
SPEED_KEY: Final = "sim.speed"
"""Auto speed, ms per simulated day."""
REPLAY_LEN_KEY: Final = "sim.replay_len"
"""Replay window length in trading days (applies on the next reset)."""
MODE_KEY: Final = "sim.mode"
"""The Simulated / Replay choice (mirrors ``SimSession.mode``)."""
ADVISOR_KEY: Final = "sim.advisor_open"
"""Whether the desk-advisor dialog is open."""
LAST_AUTO_KEY: Final = "sim.last_auto"
"""Monotonic time (s) of the last Auto step (or of Auto being switched on)."""

TK_KIND: Final = "sim.tk_kind"
TK_SIDE: Final = "sim.tk_side"
TK_TYPE: Final = "sim.tk_type"
TK_K: Final = "sim.tk_K"
TK_DAYS: Final = "sim.tk_days"
TK_SIZE: Final = "sim.tk_size"
TK_PRESET: Final = "sim.tk_preset"
TK_WING: Final = "sim.tk_wing"
"""Trade-ticket fields (kind, side, call/put, strike, tenor in days, size, preset, wing %)."""

DEFAULT_SPREAD: Final = 0.05
DEFAULT_LEAN: Final = 0.0


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


def pause_if_stale(now: float | None = None) -> None:
    """Pause Auto when it has been silent for several intervals (the user left the page;
    React pauses Auto on navigation). Called on the page's full runs."""
    sess = session()
    t = time.monotonic() if now is None else now
    if sess.playing and auto_stale(t, float(st.session_state[LAST_AUTO_KEY]), speed_ms()):
        sess.set_playing(False)


# ------------------------------------------------------------------ callbacks: the market


def on_tick() -> None:
    """Tick: one day, no new client flow."""
    session().tick()


def on_toggle_auto() -> None:
    """Auto / Pause. The first Auto step comes one interval after switching on."""
    sess = session()
    sess.set_playing(not sess.playing)
    st.session_state[LAST_AUTO_KEY] = time.monotonic()


def on_reset() -> None:
    """Reset session (a new window in Replay, with the current replay length)."""
    session().reset(replay_len())


def on_mode() -> None:
    """Simulated / Replay: switching always starts a fresh session."""
    mode = cast("Mode", st.session_state[MODE_KEY])
    sess = session()
    if mode != sess.mode:
        sess.switch_mode(mode, replay_len())


def auto_step(now: float | None = None) -> int:
    """The Auto steps that are due (see :func:`~eqd_desk.app.ui.simulator_clock.auto_steps`);
    returns how many days the market moved (0 when Auto is off or nothing is due)."""
    sess = session()
    if not sess.playing:
        return 0
    t = time.monotonic() if now is None else now
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
    set with :func:`~eqd_desk.app.ui.simulator_inputs.set_value`, which remounts its widget
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
    """Open the desk advisor."""
    st.session_state[ADVISOR_KEY] = True


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
    "LAST_AUTO_KEY",
    "LEAN_KEY",
    "MODE_KEY",
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
    "on_open_advisor",
    "on_pass",
    "on_quote",
    "on_request",
    "on_reset",
    "on_select",
    "on_tick",
    "on_toggle_auto",
    "pause_if_stale",
    "replay_len",
    "session",
    "set_ticket",
    "speed_ms",
]
