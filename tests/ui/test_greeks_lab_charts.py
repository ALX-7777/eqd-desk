"""The greeks lab's charts plot the curves they are given, with the React titles, reference
lines, hover labels and ``fmtNum(v, 3)`` y ticks (asserted on the Vega-Lite spec)."""

from __future__ import annotations

from typing import Any

import pytest

from eqd_desk.app.ui import greeks_lab_charts as lab_charts
from eqd_desk.app.ui import greeks_lab_curves as curves
from eqd_desk.app.ui import theme
from eqd_desk.app.ui.format import fmt_num
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
    assert s["config"]["axisY"]["labelExpr"] == lab_charts.FMT_NUM_3_LABEL_EXPR
    hover = next(lay for lay in of_type(s, "rule") if "tooltip" in lay["encoding"])
    tips = rows(s, hover)
    assert [t["x_text"] for t in tips] == [curves.x_tick(x_axis, x) for x in sweep["x"]]
    assert [t["t0"] for t in tips] == [fmt_num(y) for y in sweep["gamma"]]
    assert hover["encoding"]["tooltip"][0]["title"] == curves.X_AXIS_LABELS[x_axis]


def test_payoff_chart_draws_premium_now_under_intrinsic_at_expiry() -> None:
    curve = curves.payoff_curve(SEED, "call", SNAP.spot)
    s = lab_charts.payoff_chart(curve, inputs=SEED, currency="USD").to_dict()
    now, expiry = of_type(s, "line")  # "Now" first: the expiry curve is drawn on top
    assert [d["y"] for d in rows(s, now)] == list(curve["now"])
    assert [d["y"] for d in rows(s, expiry)] == list(curve["expiry"])
    assert {d["series"] for d in rows(s, now)} == {"Now"}
    assert {d["series"] for d in rows(s, expiry)} == {"At expiry"}
    assert (mark(now)["strokeWidth"], mark(expiry)["strokeWidth"]) == (1.5, 2.0)
    scale = now["encoding"]["color"]["scale"]
    assert (scale["domain"], scale["range"]) == (["Now", "At expiry"], [theme.ACCENT, theme.LINE])
    assert rules_x(s) == [(SEED.S, [4, 3]), (SEED.K, [1, 4])]
    assert expiry["encoding"]["y"]["title"] == "Value (USD)"
    assert s["height"] == lab_charts.PAYOFF_CHART_HEIGHT
    hover = next(lay for lay in of_type(s, "rule") if "tooltip" in lay["encoding"])
    assert rows(s, hover)[0]["x_text"] == curves.x_tick("S", float(curve["spot"].iloc[0]))
    assert s["config"]["axisY"]["labelExpr"] == lab_charts.FMT_NUM_3_LABEL_EXPR


def test_label_expr_follows_fmt_num_3() -> None:
    """The Vega expression mirrors fmtNum(v, 3): zero, exponent bounds, 3 − int digits."""
    expr = lab_charts.FMT_NUM_3_LABEL_EXPR
    assert "datum.value == 0 ? '0'" in expr
    assert "abs(datum.value) >= 1e7 || abs(datum.value) < 1e-4" in expr
    assert "format(datum.value, '.2e')" in expr
    assert "clamp(3 - (floor(log(abs(datum.value)) / LN10) + 1), 0, 8)" in expr
