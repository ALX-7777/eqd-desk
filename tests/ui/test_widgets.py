"""Pure halves of the shared widgets: header stats, section titles, keys, colours."""

from __future__ import annotations

import dataclasses

import pytest

from eqd_desk.app.ui.format import fmt_level, fmt_pct
from eqd_desk.app.ui.widgets import (
    SECTION_HEADING,
    greek_label,
    header_stats,
    header_subtitle,
    md_color,
    safe_help,
    section_title,
    seed_badge_text,
    slider_keys,
)
from eqd_desk.data import UNDERLYINGS, load_snapshot
from eqd_desk.engine import GREEK_UNITS


def test_header_stats_mirror_the_react_market_strip() -> None:
    snap = load_snapshot()
    cfg = UNDERLYINGS["spx"]
    stats = header_stats(snap, cfg)
    assert [s.label for s in stats] == ["^GSPC", "^VIX (ATM 30d)", "r", "q"]
    assert [s.value for s in stats] == [
        fmt_level(snap.spot, 3),
        fmt_pct(snap.atm_vol_30d),
        fmt_pct(snap.r),
        fmt_pct(snap.q),
    ]
    fixed = dataclasses.replace(snap, spot=6312.45, atm_vol_30d=0.146, r=0.043, q=0.013)
    assert [s.value for s in header_stats(fixed, cfg)] == ["6,312.45", "14.60%", "4.30%", "1.30%"]
    assert header_subtitle(fixed) == f"{snap.name} · BSM with dividend yield"
    assert seed_badge_text(fixed) == f"Static seed · {snap.asof}"


def test_slider_keys() -> None:
    assert slider_keys("lab.S") == ("lab.S__slider", "lab.S__input")


def test_md_color() -> None:
    assert md_color("+1.00", "pos") == ":green[+1.00]"
    assert md_color("-1.00", "neg") == ":red[-1.00]"
    assert md_color("14.6%", "accent") == ":primary[14.6%]"
    assert md_color("x", None) == "x"


def test_section_title_is_a_small_heading() -> None:
    # A heading (h6: body-text size), so every panel title is in the page outline.
    assert SECTION_HEADING == "###### "
    assert section_title("Inputs") == "###### **Inputs**"
    assert section_title("Delta", subtitle="vs", highlight="spot") == (
        "###### **Delta** :gray[vs] :primary[spot]"
    )
    assert section_title("Legs", icon=":material/list_alt:") == (
        "###### :gray[:material/list_alt:] **Legs**"
    )
    # plain text in, safe Markdown out
    assert section_title("P&L [$]") == "###### **P&L \\[\\$\\]**"


def test_safe_help_escapes_plain_text_once() -> None:
    assert safe_help("a $1 move vs per $1 spot") == "a \\$1 move vs per \\$1 spot"
    assert safe_help(None) is None
    assert safe_help("") is None


@pytest.mark.parametrize("key", list(GREEK_UNITS))
def test_every_greek_has_a_label(key: str) -> None:
    assert greek_label(key) == GREEK_UNITS[key].label
