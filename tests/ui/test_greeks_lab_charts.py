"""The greeks lab's greek chart plots the sweep it is given, with the React titles, reference
lines, hover labels and ``fmtNum(v, 3)`` y ticks (asserted on the Vega-Lite spec). The payoff
chart is the shared ``charts.payoff_chart`` (tested in ``test_charts.py``; the page's use of
it in ``tests/app/test_greeks_lab.py``)."""

from __future__ import annotations

from typing import Any

import pytest

from eqd_desk.app.ui import charts
from eqd_desk.app.ui import greeks_lab_charts as lab_charts
from eqd_desk.app.ui import greeks_lab_curves as curves
from eqd_desk.app.ui.format import fmt_num
from eqd_desk.content import GREEK_KEYS, GreekKey
from eqd_desk.content.greeks import XAxisKey
from eqd_desk.data import load_snapshot, seed_inputs

SNAP = load_snapshot()
SEED = seed_inputs(SNAP)


def layers(s: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = s["layer"]
    return out


def mark(layer: dict[str, Any]) -> dict[str, Any]:
    m = layer["mark"]
    return m if isinstance(m, dict) else {"type": m}


def rows(s: dict[str, Any], layer: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = s["datasets"][layer["data"]["name"]]
    return out


def of_type(s: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [lay for lay in layers(s) if mark(lay)["type"] == kind]


def rules_x(s: dict[str, Any]) -> list[tuple[float, list[int]]]:
    """(x, strokeDash) of every vertical reference line."""
    out = []
    for lay in of_type(s, "rule"):
        data = rows(s, lay)
        if "x" in data[0] and "x_text" not in data[0] and lay["encoding"].get("x"):
            out.append((float(data[0]["x"]), mark(lay).get("strokeDash", [])))
    return out


def test_axis_titles_and_panel_title() -> None:
    assert lab_charts.greek_axis_title("delta", "USD") == "Delta (per $1 spot)"
    assert lab_charts.greek_axis_title("vega", "USD") == "Vega (per 1 vol pt)"
    assert lab_charts.greek_axis_title("price", "EUR") == "Price (EUR)"
    assert lab_charts.greek_chart_title("delta", "S") == ("Delta", "spot")
    assert lab_charts.greek_chart_title("gamma", "sigma") == ("Gamma", "implied vol")
    assert lab_charts.greek_chart_title("vega", "T") == ("Vega", "time to expiry (yrs)")


@pytest.mark.parametrize(
    ("x_axis", "expected"),
    [
        ("S", [(SEED.S, [4, 3]), (SEED.K, [1, 4])]),
        ("sigma", [(SEED.sigma, [4, 3])]),
        ("T", [(SEED.T, [4, 3])]),
    ],
)
def test_reference_lines_mark_the_current_level_and_the_strike(
    x_axis: XAxisKey, expected: list[tuple[float, list[int]]]
) -> None:
    rules = lab_charts.greek_rules(SEED, x_axis)
    assert [(r.x, r.style) for r in rules] == [
        (x, "current" if dash == [4, 3] else "strike") for x, dash in expected
    ]
    sweep = curves.greek_sweep(SEED, "call", x_axis, SNAP.spot)
    s = lab_charts.greek_chart(sweep, "delta", x_axis, inputs=SEED, currency="USD").to_dict()
    assert rules_x(s) == expected


@pytest.mark.parametrize("x_axis", curves.X_AXES)
def test_greek_chart_plots_the_selected_greek(x_axis: XAxisKey) -> None:
    sweep = curves.greek_sweep(SEED, "call", x_axis, SNAP.spot)
    s = lab_charts.greek_chart(sweep, "gamma", x_axis, inputs=SEED, currency="USD").to_dict()
    (line,) = of_type(s, "line")
    data = rows(s, line)
    assert [d["x"] for d in data] == list(sweep["x"])
    assert [d["y"] for d in data] == list(sweep["gamma"])
    assert {d["series"] for d in data} == {"Gamma"}
    assert mark(line)["strokeWidth"] == 2.0
    assert line["encoding"]["x"]["title"] == curves.X_AXIS_LABELS[x_axis]
    assert line["encoding"]["x"]["axis"]["format"] == curves.X_AXIS_FORMATS[x_axis]
    assert line["encoding"]["y"]["title"] == "Gamma (Δdelta per $1 spot)"
    assert s["height"] == lab_charts.GREEK_CHART_HEIGHT
    # y ticks as the React tickFormatter (fmtNum(v, 3)); hover as React's labelFormatter
    assert line["encoding"]["y"]["axis"]["labelExpr"] == charts.FMT_NUM_3_LABEL_EXPR
    hover = next(lay for lay in of_type(s, "rule") if "tooltip" in lay["encoding"])
    tips = rows(s, hover)
    assert [t["x_text"] for t in tips] == [curves.x_tick(x_axis, x) for x in sweep["x"]]
    assert [t["t0"] for t in tips] == [fmt_num(y) for y in sweep["gamma"]]
    assert hover["encoding"]["tooltip"][0]["title"] == curves.X_AXIS_LABELS[x_axis]


@pytest.mark.parametrize("x_axis", curves.X_AXES)
def test_every_greek_keeps_fmt_num_3_y_ticks(x_axis: XAxisKey) -> None:
    """The shared line chart falls back to Vega's tick format on a narrow y range; a greek
    sweep's axis includes 0, so every greek (and the price, call and put) keeps the React
    fmtNum(v, 3) ticks on every x axis."""
    for option_type in ("call", "put"):
        sweep = curves.greek_sweep(SEED, option_type, x_axis, SNAP.spot)
        for greek in GREEK_KEYS:
            chart = lab_charts.greek_chart(sweep, greek, x_axis, inputs=SEED, currency="USD")
            (line,) = of_type(chart.to_dict(), "line")
            y_axis = line["encoding"]["y"]["axis"]
            assert y_axis == {"labelExpr": charts.FMT_NUM_3_LABEL_EXPR}, (option_type, greek)


def test_y_tick_expression_follows_fmt_num_3() -> None:
    """The greek chart's y-tick expression (the shared one) mirrors fmtNum(v, 3): zero,
    exponent bounds, 3 − integer digits."""
    expr = charts.FMT_NUM_3_LABEL_EXPR
    assert "datum.value == 0 ? '0'" in expr
    assert "abs(datum.value) >= 1e7 || abs(datum.value) < 1e-4" in expr
    assert "format(datum.value, '.2e')" in expr
    assert "clamp(3 - (floor(log(abs(datum.value)) / LN10) + 1), 0, 8)" in expr


@pytest.mark.parametrize(
    ("greek", "x_axis"),
    [("vanna", "sigma"), ("volga", "sigma"), ("charm", "T"), ("delta", "S")],
)
def test_greek_chart_leaves_room_above_the_top_tick_label(
    greek: GreekKey, x_axis: XAxisKey
) -> None:
    """Regression: ``st.altair_chart`` replaces a missing top-level ``padding`` with
    ``{"bottom": 20}`` (the shared ``config.padding`` never applies), so the plot started at
    the top edge of the canvas and, after switching to vanna vs vol, Vega's autosize left the
    top tick label ("0.0100") half above it. The greek chart carries its own top-level
    padding, which Streamlit keeps, with room for a label centred on the plot's top edge
    (about 6.5 px above it at the 11 px axis font)."""
    sweep = curves.greek_sweep(SEED, "call", x_axis, SNAP.spot)
    s = lab_charts.greek_chart(sweep, greek, x_axis, inputs=SEED, currency="USD").to_dict()
    assert s["padding"] == dict(lab_charts.GREEK_CHART_PADDING)
    assert s["padding"]["top"] >= 8
    assert s["padding"]["bottom"] == 20  # Streamlit's own default, kept
