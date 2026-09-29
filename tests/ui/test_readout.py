"""The readout table model (:mod:`eqd_desk.app.ui.readout`): rows, text, colours, line
breaking and the greek rows."""

from __future__ import annotations

import math

import pytest

from eqd_desk.app.ui import theme
from eqd_desk.app.ui.format import fmt_num
from eqd_desk.app.ui.readout import (
    NB_HYPHEN,
    NBSP,
    WORD_JOINER,
    ReadoutRow,
    greek_rows,
    group_row,
    keep_together,
    label_text,
    readout_frame,
    readout_styler,
    row_styles,
    row_text,
    tone_color,
    unit_text,
    value_text,
)
from eqd_desk.content.greeks import GREEK_GROUPS
from eqd_desk.engine import GREEK_UNITS, BsmInputs, analyze_option

A = analyze_option(BsmInputs(S=100, K=100, T=1, r=0.05, q=0.01, sigma=0.2), "call")


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


def test_greek_rows_units_follow_the_currency() -> None:
    usd = {r.label: r.unit for r in greek_rows(A.reported, currency="USD")}
    eur = {r.label: r.unit for r in greek_rows(A.reported, currency="EUR")}
    assert usd["Delta"] == "per $1 spot"
    assert eur["Delta"] == "per €1 spot"
    assert eur["Gamma"] == "Δdelta per €1 spot"
    assert eur["Speed"] == "Δgamma per €1 spot"
    assert eur["Vega"] == usd["Vega"] == "per 1 vol pt"  # no money in it


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
    assert "nowrap" not in unit  # a unit may wrap, so the table fits a narrow column
    assert theme.POS in row_styles(ReadoutRow("Vega", 7.15))[1]
    assert theme.TEXT_DIM in row_styles(ReadoutRow("Zero", 0.0))[1]
    assert theme.NEG in row_styles(ReadoutRow("Loss", 0.08, tone="neg"))[1]
    head = row_styles(group_row("First order"))
    assert all("uppercase" in css for css in head)
    assert "max-width: 0" in head[0]


def test_text_tone_prints_the_value_in_the_body_colour() -> None:
    # probabilities, levels and vols: React prints them uncoloured, whatever their sign
    row = ReadoutRow("P(autocall)", 0.52, text="52.0%", tone="text")
    assert f"color: {theme.TEXT}" in row_styles(row)[1]
    assert tone_color("text") == theme.TEXT
    assert tone_color("pos") == theme.POS


def test_readout_frame_keeps_values_numeric_and_escapes_text() -> None:
    rows = [group_row("First order"), ReadoutRow("Delta", 0.5, unit="per $1 spot")]
    df = readout_frame(rows)
    assert list(df.columns) == ["label", "value", "unit"]
    assert df["value"].dtype.kind == "f"  # numeric ⇒ Streamlit right-aligns the column
    assert math.isnan(df["value"][0])
    assert df["value"][1] == 0.5
    assert df["unit"][1] == "per \\$1 spot"  # "$" escaped: no LaTeX in st.table cells


@pytest.mark.parametrize(
    ("unit", "shown"),
    [
        # a unit breaks between its words ...
        ("Δdelta per $1 spot", f"Δdelta per $1{NBSP}spot"),
        ("Δvega per 1 vol pt", f"Δvega per 1{NBSP}vol{NBSP}pt"),
        ("Δgamma per day", "Δgamma per day"),
        ("early redeem", "early redeem"),
        ("vanilla 6,312.45", "vanilla 6,312.45"),
        # ... never inside a quantity, before "=" or after an operator
        ("per 1 rate pt", f"per 1{NBSP}rate{NBSP}pt"),
        ("fair − ATM", f"fair −{NBSP}ATM"),
        ("desk = raw ÷100", f"desk{NBSP}= raw ÷100"),
        ("", ""),
    ],
)
def test_unit_text_breaks_between_words_only(unit: str, shown: str) -> None:
    assert unit_text(unit) == shown


def test_keep_together_and_label_text() -> None:
    assert keep_together("Down-out") == f"Down{NB_HYPHEN}out"
    assert keep_together("P(capital loss)") == f"P(capital{NBSP}loss)"
    # a label keeps a hyphenated word whole but may wrap at a space
    assert label_text("Down-in") == f"Down{NB_HYPHEN}in"
    assert label_text("P(capital loss)") == "P(capital loss)"


def test_readout_styler_displays_row_texts() -> None:
    rows = [
        group_row("Second order / cross"),
        ReadoutRow("Gamma", 0.0014962, unit="Δdelta per $1 spot", selected=True),
        ReadoutRow("P(capital loss)", 0.08, text="8.0%", tone="neg"),
        ReadoutRow("Down-out", 12.0, text="12.00", tone="text"),
    ]
    html = readout_styler(rows).to_html()
    assert "0.0014962" in html
    assert "8.0%" in html
    assert f"Second{NBSP}order{NBSP}/{NBSP}cross" in html  # headings on one line
    assert f"Down{NB_HYPHEN}out" in html  # a hyphenated label never splits there
    assert "P(capital loss)" in html  # ... but may wrap at a space
    assert f"Δdelta per \\$1{NBSP}spot" in html  # units break between words
    assert theme.ACCENT_DIM in html


def test_value_text_never_splits_after_a_hyphen() -> None:
    assert value_text("-9.56186e-7") == f"-{WORD_JOINER}9.56186e-{WORD_JOINER}7"
    assert value_text("0.54994") == "0.54994"
    assert value_text("2026-06-23").replace(WORD_JOINER, "") == "2026-06-23"
    html = readout_styler([ReadoutRow("Speed", -9.56186e-7, text="-9.56186e-7")]).to_html()
    assert f"e-{WORD_JOINER}7" in html
