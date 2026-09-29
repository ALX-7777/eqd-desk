"""The page registry points at real scripts (and names each browser tab), and ``ui.state``
shares one copy of the market data."""

from __future__ import annotations

import dataclasses

from eqd_desk.app.ui import state
from eqd_desk.app.ui.nav import APP_DIR, APP_NAME, HOME, PAGES, TOOLS, page_spec
from eqd_desk.cli import APP_SCRIPT
from eqd_desk.data import UNDERLYINGS, load_snapshot


def test_page_registry() -> None:
    assert APP_DIR == APP_SCRIPT.parent
    assert PAGES[0] is HOME
    assert TOOLS == PAGES[1:]
    assert len(TOOLS) == 4
    for page in PAGES:
        assert page.path.is_file(), page.file
        assert page.path == APP_DIR / page.file
        assert page.icon.startswith(":material/")
        assert page.icon.endswith(":")
        assert page.title == page.title.capitalize()  # sentence case
        assert page.blurb
    slugs = [p.url_path for p in PAGES]
    assert slugs[0] == ""
    assert len(set(slugs)) == len(slugs)


def test_shared_data_accessors() -> None:
    snap = state.snapshot()
    assert snap is load_snapshot()  # cached once per process, never copied
    assert state.surface() is state.surface()
    assert state.history().meta.count == len(state.history().series)
    assert state.underlying(snap) == UNDERLYINGS["spx"]
    unknown = dataclasses.replace(snap, underlying="nope")
    assert state.underlying(unknown) == UNDERLYINGS["spx"]
    sx5e = dataclasses.replace(snap, underlying="sx5e")
    assert state.underlying(sx5e) == UNDERLYINGS["sx5e"]


def test_each_page_names_its_browser_tab() -> None:
    assert HOME.tab_title == APP_NAME == "EQD Desk"
    assert [p.tab_title for p in TOOLS] == [f"{p.title} · EQD Desk" for p in TOOLS]
    assert len({p.tab_title for p in PAGES}) == len(PAGES)  # every tab title is distinct
    for page in PAGES:
        assert page_spec(page.title) is page
    assert page_spec("no such page") is HOME
