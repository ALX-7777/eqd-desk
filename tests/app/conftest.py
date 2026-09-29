"""Shared fixtures for the Streamlit ``AppTest`` suites (``@pytest.mark.app``).

``AppTest`` runs the scripts headless and in-process. Always start from the ENTRYPOINT
(``eqd_desk/app/streamlit_app.py``) so ``st.navigation`` registers the pages, then reach a
page with ``at.switch_page("app_pages/<page>.py").run()``::

    def test_my_page(app_test: AppTestFactory) -> None:
        at = app_test()
        at.run()
        at.switch_page("app_pages/greeks_lab.py").run()
        assert not at.exception

The shared inputs are remount-safe (:mod:`eqd_desk.app.ui.inputs`): their widget keys carry
a generation suffix that changes when the value is set programmatically, so look a widget up
by its CANONICAL key through :func:`wkey` (choices, toggles), :func:`slider_wkey` and
:func:`field_wkey` (the two halves of a ``number_slider``), resolved again after each run::

    at.button_group(key=wkey(at, "lab.greek")).set_value("gamma").run()
    at.slider(key=slider_wkey(at, "strat.S")).set_value(6400.0).run()
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from streamlit.testing.v1 import AppTest

from eqd_desk.app.ui.inputs import widget_key_in
from eqd_desk.app.ui.widgets import slider_keys
from eqd_desk.cli import APP_SCRIPT

DEFAULT_TIMEOUT = 30.0
"""Seconds per ``run()``: generous, the first run imports pandas/altair and loads the data."""

AppTestFactory = Callable[[], AppTest]
"""Builds a fresh ``AppTest`` of the whole app (entrypoint + navigation)."""


def wkey(at: AppTest, key: str) -> str:
    """The widget key the input with canonical ``key`` renders with now."""
    return widget_key_in(at.session_state, key)


def slider_wkey(at: AppTest, key: str) -> str:
    """The widget key of the slider of the ``number_slider`` with canonical ``key``."""
    return wkey(at, slider_keys(key)[0])


def field_wkey(at: AppTest, key: str) -> str:
    """The widget key of the numeric field of the ``number_slider`` with canonical ``key``."""
    return wkey(at, slider_keys(key)[1])


def new_app() -> AppTest:
    """A fresh, not-yet-run ``AppTest`` of the packaged entrypoint."""
    return AppTest.from_file(str(APP_SCRIPT), default_timeout=DEFAULT_TIMEOUT)


@pytest.fixture
def app_test() -> AppTestFactory:
    """Factory fixture: ``at = app_test(); at.run()``."""
    return new_app


@pytest.fixture
def app() -> AppTest:
    """The app, already run once (on the overview page)."""
    at = new_app()
    at.run()
    assert not at.exception, at.exception
    return at
