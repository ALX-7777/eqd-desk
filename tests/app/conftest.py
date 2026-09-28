"""Shared fixtures for the Streamlit ``AppTest`` suites (``@pytest.mark.app``).

``AppTest`` runs the scripts headless and in-process. Always start from the ENTRYPOINT
(``eqd_desk/app/streamlit_app.py``) so ``st.navigation`` registers the pages, then reach a
page with ``at.switch_page("app_pages/<page>.py").run()``::

    def test_my_page(app_test: AppTestFactory) -> None:
        at = app_test()
        at.run()
        at.switch_page("app_pages/greeks_lab.py").run()
        assert not at.exception
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from streamlit.testing.v1 import AppTest

from eqd_desk.cli import APP_SCRIPT

DEFAULT_TIMEOUT = 30.0
"""Seconds per ``run()``: generous, the first run imports pandas/altair and loads the data."""

AppTestFactory = Callable[[], AppTest]
"""Builds a fresh ``AppTest`` of the whole app (entrypoint + navigation)."""


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
