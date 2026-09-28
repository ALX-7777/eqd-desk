"""Trading simulator (Phase 4): make markets in the index.

Clients send RFQs; you quote a two-way (spread + lean) and win or lose the trade; you are
left with risk; you hedge it (the future for delta, options for vega and gamma, the trade
ticket, the desk advisor); the market moves (a simulated GBM + leverage path, or a replay of
real ^GSPC / ^VIX history) and the P&L explain tells you where the money came from.

The whole desk lives in a fragment: while Auto is on it reruns on a timer (the market steps,
clients send RFQs) without rerunning the rest of the app. Logic lives in ``ui/sim_session``
(the state machine), ``ui/simulator_display`` (the text), ``ui/simulator_controls``
(callbacks) and ``ui/simulator_panels`` (layout).
"""

from __future__ import annotations

import streamlit as st

from eqd_desk.app.ui import simulator_controls as ctl
from eqd_desk.app.ui.simulator_clock import auto_interval
from eqd_desk.app.ui.simulator_panels import live_desk

desk = ctl.ensure_sim_state()
ctl.pause_if_stale()
interval = auto_interval(desk.playing, ctl.speed_ms())


@st.fragment(run_every=interval)
def trading_desk() -> None:
    live_desk(interval)


trading_desk()
