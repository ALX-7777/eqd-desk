"""The app shell: header strip, navigation to every page, and the overview page."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from eqd_desk.app.ui.format import fmt_level, fmt_num, fmt_pct
from eqd_desk.app.ui.nav import PAGES, TOOLS, PageSpec
from eqd_desk.app.ui.state import APP_READY_KEY
from eqd_desk.app.ui.widgets import header_stats, seed_badge_text
from eqd_desk.content import markdown_safe
from eqd_desk.data import UNDERLYINGS, load_snapshot
from eqd_desk.engine import GREEK_UNITS

pytestmark = pytest.mark.app


def markdown_texts(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown]


def assert_header(at: AppTest) -> None:
    snap = load_snapshot()
    texts = markdown_texts(at)
    brand = texts[0]
    assert "EQD Desk" in brand
    assert markdown_safe(f"{snap.name} · BSM with dividend yield") in brand
    for stat in header_stats(snap, UNDERLYINGS["spx"]):
        assert any(stat.label in t and f"`{stat.value}`" in t for t in texts), stat
    assert any(seed_badge_text(snap) in t and "badge" in t for t in texts)


def test_entrypoint_renders_header_with_snapshot_values(app: AppTest) -> None:
    snap = load_snapshot()
    assert_header(app)
    # the values are the snapshot's, formatted like the React header
    texts = " ".join(markdown_texts(app))
    for value in (fmt_level(snap.spot, 3), fmt_pct(snap.atm_vol_30d), fmt_pct(snap.r)):
        assert f"`{value}`" in texts
    assert app.session_state[APP_READY_KEY] is True


@pytest.mark.parametrize("page", PAGES, ids=[p.url_path or "home" for p in PAGES])
def test_every_page_is_reachable(app: AppTest, page: PageSpec) -> None:
    app.switch_page(page.file).run()
    assert not app.exception, app.exception
    assert_header(app)  # the shell renders above every page


def test_home_tool_cards_link_to_each_tool(app: AppTest) -> None:
    links = app.get("page_link")
    assert [(link.proto.label, link.proto.page) for link in links] == [
        (f"Open {spec.title.lower()}", spec.url_path) for spec in TOOLS
    ]
    headings = markdown_texts(app)
    for spec in TOOLS:
        assert any(spec.title in t and spec.icon in t for t in headings)
        assert any(markdown_safe(spec.blurb) == t for t in headings)


def test_home_seed_market_metrics_show_snapshot_values(app: AppTest) -> None:
    snap = load_snapshot()
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Spot · ^GSPC"] == fmt_level(snap.spot, 3)
    assert metrics["ATM vol 30d · ^VIX"] == fmt_pct(snap.atm_vol_30d)
    assert metrics["Rate r"] == fmt_pct(snap.r)
    assert metrics["Dividend yield q"] == fmt_pct(snap.q)
    assert metrics["Skew slope · curvature"] == (
        f"{fmt_num(snap.skew.slope, 3)} · {fmt_num(snap.skew.curv, 3)}"
    )
    captions = [c.value for c in app.caption]
    for note in snap.source_notes:
        assert markdown_safe(note) in captions


def test_home_units_table_lists_every_greek(app: AppTest) -> None:
    units = next(t.value for t in app.table if "Greek" in t.value.columns)
    assert list(units["Greek"]) == [u.label for u in GREEK_UNITS.values()]
    assert list(units["From the raw partial"]) == [u.scale_note for u in GREEK_UNITS.values()]
