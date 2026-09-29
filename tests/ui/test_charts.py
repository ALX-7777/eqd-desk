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


def test_line_chart_axes_read_like_the_react_charts_by_default() -> None:
    """y ticks print fmtNum(v, 3) (React's tickFormatter); the x axis is tidied: a tick-count
    hint, colliding labels thinned, end labels kept inside the plot."""
    s = spec(
        charts.line_chart(
            sample_frame(), x="S", series=Series("a", "Delta"), x_title="Spot", y_title="Delta"
        )
    )
    enc = of_type(s, "line")[0]["encoding"]
    assert enc["y"]["axis"] == {"labelExpr": charts.FMT_NUM_3_LABEL_EXPR}
    x_axis = enc["x"]["axis"]
    assert x_axis["tickCount"] == charts.X_TICK_COUNT
    assert x_axis["labelOverlap"] is True
    assert x_axis["labelSeparation"] == charts.X_LABEL_GAP_PX
    assert x_axis["labelFlush"] is True
    assert x_axis["labelBound"] == charts.X_LABEL_BOUND_PX
    assert "format" not in x_axis  # Vega's adaptive default unless x_format is given


def test_axis_formats_and_opt_outs() -> None:
    assert charts.axis_format(None) == {}
    assert charts.axis_format(charts.FMT_NUM_3) == {"labelExpr": charts.FMT_NUM_3_LABEL_EXPR}
    assert charts.axis_format(".0%") == {"format": ".0%"}
    assert "tickCount" not in charts.tidy_x_axis(None)
    s = spec(
        charts.line_chart(
            sample_frame(),
            x="S",
            series=Series("a", "P&L"),
            x_title="Day",
            y_title="P&L",
            x_format="d",
            y_format=None,
            x_tick_count=None,
        )
    )
    enc = of_type(s, "line")[0]["encoding"]
    assert "labelExpr" not in enc["y"]["axis"]
    assert "format" not in enc["y"]["axis"]
    assert enc["x"]["axis"]["format"] == "d"
    assert "tickCount" not in enc["x"]["axis"]
    assert enc["x"]["axis"]["labelOverlap"] is True  # thinning always on


@pytest.mark.parametrize(
    ("value", "step"),
    [
        (53.14, 0.1),
        (250.0, 1.0),
        (6312.45, 1.0),
        (0.5, 1e-3),
        (0.0007, 1e-6),
        (4.2e-6, 1e-8),
        (-12.0, 0.1),
        (0.0, 0.0),
    ],
)
def test_fmt_num_3_step(value: float, step: float) -> None:
    assert charts.fmt_num_3_step(value) == pytest.approx(step)


def test_fmt_num_3_fits_only_ranges_it_can_label() -> None:
    assert charts.fmt_num_3_fits(-200.0, 200.0)  # a P&L axis
    assert charts.fmt_num_3_fits(0.0, 0.0007)  # a gamma axis
    assert charts.fmt_num_3_fits(53.1, 53.1)  # flat: a single tick
    assert not charts.fmt_num_3_fits(53.13, 53.14)  # would print "53.1" at every tick


def test_a_narrow_y_range_falls_back_to_vega_ticks() -> None:
    df = pd.DataFrame({"w": [50.0, 100.0, 150.0], "v": [53.141, 53.138, 53.132]})
    s = spec(
        charts.line_chart(
            df, x="w", series=Series("v", "Spread"), x_title="Width", y_title="Value", y_zero=False
        )
    )
    y_axis = of_type(s, "line")[0]["encoding"]["y"]["axis"]
    assert "labelExpr" not in y_axis
    # ... but not when zero is on the axis (0 … 53.14 is a wide range)
    s = spec(charts.line_chart(df, x="w", series=Series("v", "S"), x_title="W", y_title="V"))
    assert of_type(s, "line")[0]["encoding"]["y"]["axis"]["labelExpr"]


def test_level_text_prints_whole_points_grouped_like_the_axis() -> None:
    # whole points (React's toFixed(0) rounding), grouped like SPOT_AXIS_FORMAT ticks
    assert charts.level_text(6312.45) == "6,312"
    assert charts.level_text(6312.5) == "6,313"
    assert charts.level_text(-12.4) == "-12"
    assert charts.level_text(950.0) == "950"


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
    # React's payoff axes: spot in whole points, y ticks fmtNum(v, 3); the hover reads like
    # the axes and the readouts: grouped whole points, money with two decimals
    enc = lines[0]["encoding"]
    assert enc["x"]["axis"]["format"] == charts.SPOT_AXIS_FORMAT
    assert enc["y"]["axis"]["labelExpr"] == charts.FMT_NUM_3_LABEL_EXPR
    tip = next(lay for lay in of_type(s, "rule") if "tooltip" in lay["encoding"])
    assert [r["x_text"] for r in rows(s, tip)] == ["90", "100", "110"]
    assert [r["t0"] for r in rows(s, tip)] == ["1.00", "4.00", "11.00"]
    assert [r["t0"] for r in rows(s, tip)] == [fmt_money(v) for v in (1.0, 4.0, 11.0)]


def test_payoff_chart_takes_frame_columns_and_format_overrides() -> None:
    df = pd.DataFrame({"S": [90.0, 110.0], "expiry": [0.0, 10.0], "now": [1.0, 11.0]})
    s = spec(
        charts.payoff_chart(
            df["S"],
            df["expiry"],
            df["now"],
            spot=100.0,
            y_title="P&L (USD)",
            x_format=None,
            y_format=",.2f",
            x_tooltip=fmt_money,
            y_tooltip=fmt_money,
            height=320,
        )
    )
    enc = of_type(s, "line")[0]["encoding"]
    assert "format" not in enc["x"]["axis"]
    assert enc["y"]["axis"]["format"] == ",.2f"
    assert enc["y"]["title"] == "P&L (USD)"
    tip = next(lay for lay in of_type(s, "rule") if "tooltip" in lay["encoding"])
    assert rows(s, tip)[0]["x_text"] == fmt_money(90.0)
    assert rows(s, tip)[1]["t1"] == fmt_money(10.0)
    assert s["height"] == 320


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
    assert lines[0]["encoding"]["x"]["axis"]["tickCount"] == charts.X_TICK_COUNT
    tip = next(lay for lay in of_type(s, "rule") if "tooltip" in lay["encoding"])
    assert rows(s, tip)[1]["r_text"] == fmt_pct(0.16)


def test_style_chart_applies_to_any_chart() -> None:
    raw = alt.Chart(pd.DataFrame({"a": [1, 2]})).mark_point().encode(x="a:Q")
    s = spec(charts.style_chart(raw))
    assert s["config"]["background"] == "transparent"
    assert s["config"]["axis"]["labelColor"] == theme.TEXT_DIM
