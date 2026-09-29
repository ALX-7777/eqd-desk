"""The modules documented as pure (no Streamlit) really are: importing one, in a fresh
interpreter, must not import ``streamlit``. They are unit-tested without an app and
imported by other pure modules, so a stray ``from …widgets import …`` would silently pull
the whole UI framework into them."""

from __future__ import annotations

import subprocess
import sys

import pytest

PURE_MODULES = (
    "eqd_desk.app.ui.bounds",
    "eqd_desk.app.ui.charts",
    "eqd_desk.app.ui.exotics_charts",
    "eqd_desk.app.ui.exotics_curves",
    "eqd_desk.app.ui.exotics_display",
    "eqd_desk.app.ui.format",
    "eqd_desk.app.ui.greeks_lab_charts",
    "eqd_desk.app.ui.greeks_lab_curves",
    "eqd_desk.app.ui.greeks_lab_inputs",
    "eqd_desk.app.ui.nav",
    "eqd_desk.app.ui.readout",
    "eqd_desk.app.ui.sim_session",
    "eqd_desk.app.ui.simulator_charts",
    "eqd_desk.app.ui.simulator_clock",
    "eqd_desk.app.ui.simulator_display",
    "eqd_desk.app.ui.strategy_builder_charts",
    "eqd_desk.app.ui.strategy_builder_legs",
    "eqd_desk.app.ui.strategy_builder_readout",
    "eqd_desk.app.ui.strategy_curves",
    "eqd_desk.app.ui.theme",
    "eqd_desk.app.ui.units",
)


@pytest.mark.parametrize("module", PURE_MODULES)
def test_pure_module_does_not_import_streamlit(module: str) -> None:
    code = f"import sys, {module}; print('streamlit' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=120
    )
    assert out.stdout.strip() == "False", f"{module} imports streamlit"
