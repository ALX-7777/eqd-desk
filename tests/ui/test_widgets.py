"""Pure halves of the shared widgets: header stats, readout rows/styles, clamping."""

from __future__ import annotations

import dataclasses
import math

import pytest

from eqd_desk.app.ui import theme
from eqd_desk.app.ui.format import fmt_level, fmt_num, fmt_pct
from eqd_desk.app.ui.widgets import (
    NBSP,
    ReadoutRow,
    clamp,
    greek_label,
    greek_rows,
    group_row,
    header_stats,
    header_subtitle,
    md_color,
    readout_frame,
    readout_styler,
    row_styles,
    row_text,
    seed_badge_text,
    slider_keys,
)
from eqd_desk.content.greeks import GREEK_GROUPS
from eqd_desk.data import UNDERLYINGS, load_snapshot
from eqd_desk.engine import GREEK_UNITS, BsmInputs, analyze_option

A = analyze_option(BsmInputs(S=100, K=100, T=1, r=0.05, q=0.01, sigma=0.2), "call")


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


def test_clamp_and_slider_keys() -> None:
    assert clamp(5.0, 0.0, 10.0) == 5.0
    assert clamp(-1.0, 0.0, 10.0) == 0.0
    assert clamp(11.0, 0.0, 10.0) == 10.0
    assert clamp(math.nan, 2.0, 10.0) == 2.0
    assert slider_keys("lab.S") == ("lab.S__slider", "lab.S__input")


def test_md_color() -> None:
    assert md_color("+1.00", "pos") == ":green[+1.00]"
    assert md_color("-1.00", "neg") == ":red[-1.00]"
    assert md_color("14.6%", "accent") == ":primary[14.6%]"
    assert md_color("x", None) == "x"


def test_greek_rows_grouped_like_the_react_readout() -> None:
    out = greek_rows(A.reported, selected="gamma")
    headings = [r.label for r in out if r.kind == "group"]
    assert headings == [g.title for g in GREEK_GROUPS]
    values = [r for r in out if r.kind == "row"]
    keys = [k for g in GREEK_GROUPS for k in g.keys]
    assert [r.label for r in values] == [GREEK_UNITS[k].label for k in keys]
    assert [r.unit for r in values] == [GREEK_UNITS[k].unit for k in keys]
    # the numbers are the engine's reported (desk-unit) greeks, untouched
    assert [r.value for r in values] == [getattr(A.reported, k) for k in keys]
    assert [r.label for r in values if r.selected] == ["Gamma"]


def test_greek_rows_flat_and_mapping_inputs() -> None:
    flat = greek_rows(
        {"delta": 0.5, "gamma": 0.01, "vega": 0.2}, groups=None, keys=("delta", "vega")
    )
    assert [(r.label, r.value) for r in flat] == [("Delta", 0.5), ("Vega", 0.2)]
    assert all(r.kind == "row" and not r.selected for r in flat)
    assert greek_label("volga") == "Volga"


def test_row_text_and_styles() -> None:
    row = ReadoutRow("Delta", 0.549940123, unit="per $1 spot")
    assert row_text(row) == fmt_num(0.549940123) == "0.54994"
    assert row_text(ReadoutRow("P(autocall)", 0.52, text="52.0%")) == "52.0%"
    assert row_text(group_row("Diagnostics")) == ""

    label, value, unit = row_styles(ReadoutRow("Theta", -2.0, selected=True))
    assert theme.ACCENT_DIM in label
    assert "box-shadow" in label
    assert theme.NEG in value
    assert theme.MONO_FONT in value
    assert "nowrap" in value
    assert theme.TEXT_DIM in unit
    assert theme.POS in row_styles(ReadoutRow("Vega", 7.15))[1]
    assert theme.TEXT_DIM in row_styles(ReadoutRow("Zero", 0.0))[1]
    assert theme.NEG in row_styles(ReadoutRow("Loss", 0.08, tone="neg"))[1]
    head = row_styles(group_row("First order"))
    assert all("uppercase" in css for css in head)
    assert "max-width: 0" in head[0]


def test_readout_frame_keeps_values_numeric_and_escapes_text() -> None:
    rows = [group_row("First order"), ReadoutRow("Delta", 0.5, unit="per $1 spot")]
    df = readout_frame(rows)
    assert list(df.columns) == ["label", "value", "unit"]
    assert df["value"].dtype.kind == "f"  # numeric ⇒ Streamlit right-aligns the column
    assert math.isnan(df["value"][0])
    assert df["value"][1] == 0.5
    assert df["unit"][1] == "per \\$1 spot"  # "$" escaped: no LaTeX in st.table cells


def test_readout_styler_displays_row_texts() -> None:
    rows = [
        group_row("Second order / cross"),
        ReadoutRow("Gamma", 0.0014962, unit="Δdelta per $1 spot", selected=True),
        ReadoutRow("P(capital loss)", 0.08, text="8.0%", tone="neg"),
    ]
    html = readout_styler(rows).to_html()
    assert "0.0014962" in html
    assert "8.0%" in html
    assert f"Second{NBSP}order{NBSP}/{NBSP}cross" in html
    assert f"Δdelta{NBSP}per{NBSP}\\$1{NBSP}spot" in html
    assert theme.ACCENT_DIM in html


@pytest.mark.parametrize("key", list(GREEK_UNITS))
def test_every_greek_has_a_label(key: str) -> None:
    assert greek_label(key) == GREEK_UNITS[key].label
