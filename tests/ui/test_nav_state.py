"""The page registry points at real scripts, and the pure market helpers of ``ui.state``
reproduce the React constants."""

from __future__ import annotations

import dataclasses

from eqd_desk.app.ui import state
from eqd_desk.app.ui.nav import APP_DIR, HOME, PAGES, TOOLS
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


def test_strike_and_level_steps_match_react() -> None:
    assert state.strike_step(6312.45) == 25.0
    assert state.strike_step(4000.0) == 25.0
    assert state.strike_step(631.0) == 5.0
    assert state.level_step(6312.45) == 1.0
    assert state.level_step(631.0) == 0.5
    assert state.level_step(63.0) == 0.1
    assert state.strike_step() == (25.0 if load_snapshot().spot >= 2000 else 5.0)


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
