"""EQD Desk: the Streamlit entrypoint (``eqd-desk`` / ``streamlit run`` this file).

Runs before every page: page config (the browser tab names the page: "Greeks lab · EQD
Desk"), the idempotent app-wide state init, the header strip (brand + seed market) and the
top navigation. The pages themselves live in ``app_pages/`` and are registered once in
:mod:`eqd_desk.app.ui.nav`.
"""

from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path

import streamlit as st

# Hosts that run this file from a plain checkout without installing the project (possible on
# Streamlit Community Cloud) would not find the ``eqd_desk`` package: put ``src/`` on the
# path in that case only. Installed runs (eqd-desk CLI, uv run, Docker) never take this branch.
if find_spec("eqd_desk") is None:  # pragma: no cover - depends on the hosting environment
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eqd_desk.app.ui import state
from eqd_desk.app.ui.nav import APP_ICON, APP_NAME, PAGES, page_spec
from eqd_desk.app.ui.widgets import app_header

st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide")

state.init_app_state()

page = st.navigation(
    [
        st.Page(
            spec.path,
            title=spec.title,
            icon=spec.icon,
            url_path=spec.url_path or None,
            default=i == 0,
        )
        for i, spec in enumerate(PAGES)
    ],
    position="top",
)
# Additive: only the tab title changes, to the page's own (the call above sets the defaults).
st.set_page_config(page_title=page_spec(page.title).tab_title)

snap = state.snapshot()
app_header(snap, state.underlying(snap))

page.run()
