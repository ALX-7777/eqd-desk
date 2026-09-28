"""The chart builders produce valid Vega-Lite with the intended encodings, reference lines,
tooltips and terminal styling (asserted on the spec, no browser needed)."""

from __future__ import annotations

import itertools
from typing import Any

import altair as alt
import pandas as pd
import pytest

from eqd_desk.app.ui import charts, theme
from eqd_desk.app.ui.charts import RULE_STYLES, HRule, RuleStyle, Series, VRule
from eqd_desk.app.ui.format import fmt_money, fmt_num, fmt_pct


def spec(chart: Any) -> dict[str, Any]:
    """The chart's Vega-Lite dict (``to_dict`` validates it against the schema)."""
    out: dict[str, Any] = chart.to_dict()
    return out


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


def sample_frame() -> pd.DataFrame:
    xs = charts.sweep_x(90.0, 110.0, 20)
    return pd.DataFrame({"S": xs, "a": [x - 100 for x in xs], "b": [0.5 * x for x in xs]})


# ------------------------------------------------------------------ sweep_x


def test_sweep_x_matches_the_react_formula() -> None:
    lo, hi, n = 3787.47, 8837.43, 100
    xs = charts.sweep_x(lo, hi, n)
    assert len(xs) == n + 1
    assert xs[0] == lo
    assert xs == [lo + ((hi - lo) * i) / n for i in range(n + 1)]
    assert all(b > a for a, b in itertools.pairwise(xs))
    with pytest.raises(ValueError, match="n must be"):
        charts.sweep_x(0.0, 1.0, 0)


# ------------------------------------------------------------------ line_chart


def test_line_chart_single_series_encodings_and_style() -> None:
    df = sample_frame()
    s = spec(
        charts.line_chart(
            df,
            x="S",
            series=Series("a", "Delta"),
            x_title="Spot",
            y_title="Delta (per $1 spot)",
            vrules=[VRule(101.0), VRule(100.0, "strike")],
        )
    )
    lines = of_type(s, "line")
    assert len(lines) == 1
    enc = lines[0]["encoding"]
    assert enc["x"]["field"] == "x"
    assert enc["x"]["type"] == "quantitative"
    assert enc["x"]["title"] == "Spot"
    # x spans exactly the data (Recharts dataMin/dataMax): no nice rounding, no forced zero
    assert enc["x"]["scale"] == {"domain": [90.0, 110.0], "nice": False, "zero": False}
    assert enc["y"]["title"] == "Delta (per $1 spot)"
    assert enc["y"]["scale"]["zero"] is True
    assert enc["color"]["scale"] == {"domain": ["Delta"], "range": [theme.LINE]}
    assert enc["color"]["legend"] is None  # one series → no legend
    assert mark(lines[0])["strokeWidth"] == 2.0
    # the plotted data is the input data
    assert [r["y"] for r in rows(s, lines[0])] == list(df["a"])
    assert [r["x"] for r in rows(s, lines[0])] == list(df["S"])
    # terminal look
    cfg = s["config"]
    assert cfg["background"] == "transparent"
    assert cfg["axis"]["labelFont"] == theme.MONO_FONT
    assert cfg["axis"]["gridColor"] == theme.GRID
    assert cfg["view"]["stroke"] is None
    assert s["height"] == charts.DEFAULT_HEIGHT
    assert s["width"] == "container"


def test_line_chart_reference_lines_follow_the_react_vocabulary() -> None:
    s = spec(
        charts.line_chart(
            sample_frame(),
            x="S",
            series=Series("a", "Gamma"),
            x_title="Spot",
            y_title="Gamma",
            vrules=[VRule(101.0), VRule(100.0, "strike"), VRule(95.0, "barrier", "H")],
            hrules=[HRule(5.0, "coupon", "coupon")],
        )
    )
    rules = of_type(s, "rule")
    by_value: dict[float, dict[str, Any]] = {}
    for lay in rules:
        channel = "x" if "x" in lay["encoding"] else "y"
        field = lay["encoding"][channel]["field"]
        if field in ("x", "y") and lay["data"]["name"] in s["datasets"]:
            data = rows(s, lay)
            if len(data) == 1:
                by_value[data[0][field]] = lay
    expected: list[tuple[float, RuleStyle]] = [
        (101.0, "current"),
        (100.0, "strike"),
        (95.0, "barrier"),
        (5.0, "coupon"),
    ]
    for value, style in expected:
        look = RULE_STYLES[style]
        m = mark(by_value[value])
        assert m["color"] == look.color
        assert m["strokeDash"] == list(look.dash)
    texts = [rows(s, lay)[0]["label"] for lay in of_type(s, "text")]
    assert sorted(texts) == ["H", "coupon"]


def test_zero_rule_only_when_zero_is_in_range() -> None:
    df = sample_frame()  # column "a" spans -10..10, "b" spans 45..55

    def zero_rules(s: dict[str, Any]) -> int:
        return sum(
            1
            for lay in of_type(s, "rule")
            if "y" in lay["encoding"] and rows(s, lay) == [{"y": 0.0}]
        )

    spans = spec(charts.line_chart(df, x="S", series=Series("a", "A"), x_title="", y_title=""))
    assert zero_rules(spans) == 1
    level = charts.line_chart(
        df, x="S", series=Series("b", "B"), x_title="", y_title="", y_zero=False
    )
    assert zero_rules(spec(level)) == 0
    assert of_type(spec(level), "line")[0]["encoding"]["y"]["scale"]["zero"] is False


def test_multi_series_styles_legend_and_crosshair_tooltip() -> None:
    df = sample_frame()
    s = spec(
        charts.line_chart(
            df,
            x="S",
            series=[
                Series("a", "Now", color=theme.ACCENT, width=1.5),
                Series("b", "At expiry", dash=(4, 2), opacity=0.5),
            ],
            x_title="Spot",
            y_title="Value",
            y_tooltip=fmt_money,
        )
    )
    lines = of_type(s, "line")
    assert [mark(lay)["strokeWidth"] for lay in lines] == [1.5, 2.0]
    assert mark(lines[1])["strokeDash"] == [4, 2]
    assert mark(lines[1])["opacity"] == 0.5
    color = lines[0]["encoding"]["color"]
    assert color["scale"] == {"domain": ["Now", "At expiry"], "range": [theme.ACCENT, theme.LINE]}
    assert color["legend"] is not None
    # hover crosshair: a nearest-x selection and a tooltip with every series, formatted
    params = s.get("params", []) + [p for lay in layers(s) for p in lay.get("params", [])]
    hover = next(p for p in params if p["name"] == "hover")
    assert hover["select"]["nearest"] is True
    assert hover["select"]["fields"] == ["x"]
    tip_layer = next(lay for lay in of_type(s, "rule") if "tooltip" in lay["encoding"])
    titles = [t["title"] for t in tip_layer["encoding"]["tooltip"]]
    assert titles == ["Spot", "Now", "At expiry"]
    first = rows(s, tip_layer)[0]
    assert first["x_text"] == fmt_num(90.0)
    assert first["t0"] == fmt_money(-10.0)
    assert first["t1"] == fmt_money(45.0)


def test_area_fill_and_options() -> None:
    s = spec(
        charts.line_chart(
            sample_frame(),
            x="S",
            series=Series("b", "Contribution", fill=theme.ACCENT_DIM),
            x_title="Strike",
            y_title="Contribution",
            x_format=",.0f",
            y_format=".0%",
            y_domain=(0.0, 60.0),
            legend=True,
            crosshair=False,
            height=200,
        )
    )
    area = of_type(s, "area")
    assert len(area) == 1
    assert mark(area[0])["color"] == theme.ACCENT_DIM
    line = of_type(s, "line")[0]["encoding"]
    assert line["x"]["axis"]["format"] == ",.0f"
    assert line["y"]["axis"]["format"] == ".0%"
    assert line["y"]["scale"] == {"domain": [0.0, 60.0], "nice": False, "zero": False}
    assert line["color"]["legend"] is not None
    assert not any("tooltip" in lay["encoding"] for lay in layers(s))
    assert s["height"] == 200


def test_line_chart_rejects_bad_series() -> None:
    df = sample_frame()
    with pytest.raises(ValueError, match="unique"):
        charts.line_chart(
            df, x="S", series=[Series("a", "X"), Series("b", "X")], x_title="", y_title=""
        )
    with pytest.raises(ValueError, match="at least one"):
        charts.line_chart(df, x="S", series=[], x_title="", y_title="")
    with pytest.raises(ValueError, match="no finite"):
        charts.line_chart(
            pd.DataFrame({"S": [float("nan")], "a": [1.0]}),
            x="S",
            series=Series("a", "A"),
            x_title="",
            y_title="",
        )


# ------------------------------------------------------------------ payoff / bar / dual


def test_payoff_chart_marks_spot_and_distinct_strikes() -> None:
    spots = [90.0, 100.0, 110.0]
    s = spec(
        charts.payoff_chart(
            spots, [0.0, 0.0, 10.0], [1.0, 4.0, 11.0], spot=101.0, strikes=[100.0, 100.0, 105.0]
        )
    )
    lines = of_type(s, "line")
    assert lines[0]["encoding"]["color"]["scale"]["domain"] == ["Now", "At expiry"]
    assert [r["y"] for r in rows(s, lines[1])] == [0.0, 0.0, 10.0]  # expiry curve
    assert [r["y"] for r in rows(s, lines[0])] == [1.0, 4.0, 11.0]  # value now
    vertical = [
        rows(s, lay)[0]["x"]
        for lay in of_type(s, "rule")
        if "x" in lay["encoding"] and "tooltip" not in lay["encoding"]
    ]
    assert sorted(vertical) == [100.0, 101.0, 105.0]
    assert s["height"] == charts.SHORT_HEIGHT


def test_bar_chart_colours_by_sign_in_given_order() -> None:
    labels = ["Delta", "Gamma", "Theta", "Residual"]
    values = [120.5, -40.2, 0.0, -1.2]
    s = spec(charts.bar_chart(labels, values, y_title="P&L (USD)"))
    bars = of_type(s, "bar")[0]
    assert "clip" not in mark(bars)  # Vega-Lite drops clipped rounded bars
    enc = bars["encoding"]
    assert enc["x"]["sort"] == labels
    assert enc["color"]["scale"] == {"domain": ["pos", "neg"], "range": [theme.POS, theme.NEG]}
    data = rows(s, bars)
    assert [r["tone"] for r in data] == ["pos", "neg", "pos", "neg"]
    assert [r["text"] for r in data] == [fmt_money(v) for v in values]
    with pytest.raises(ValueError, match="differ"):
        charts.bar_chart(["a"], [1.0, 2.0], y_title="")


def test_dual_axis_chart_has_independent_axes() -> None:
    df = pd.DataFrame(
        {"day": [0, 1, 2], "spot": [6300.0, 6250.0, 6320.0], "vol": [0.15, 0.16, 0.14]}
    )
    s = spec(
        charts.dual_axis_chart(
            df,
            x="day",
            left=Series("spot", "Spot"),
            right=Series("vol", "ATM vol", color=theme.PUT),
            x_title="Day",
            left_title="Spot",
            right_title="ATM vol",
            right_format=".0%",
            right_tooltip=fmt_pct,
        )
    )
    assert s["resolve"]["scale"]["y"] == "independent"
    lines = of_type(s, "line")
    assert [lay["encoding"]["y"]["axis"]["orient"] for lay in lines] == ["left", "right"]
    assert lines[1]["encoding"]["y"]["axis"]["format"] == ".0%"
    tip = next(lay for lay in of_type(s, "rule") if "tooltip" in lay["encoding"])
    assert rows(s, tip)[1]["r_text"] == fmt_pct(0.16)


def test_style_chart_applies_to_any_chart() -> None:
    raw = alt.Chart(pd.DataFrame({"a": [1, 2]})).mark_point().encode(x="a:Q")
    s = spec(charts.style_chart(raw))
    assert s["config"]["background"] == "transparent"
    assert s["config"]["axis"]["labelColor"] == theme.TEXT_DIM
