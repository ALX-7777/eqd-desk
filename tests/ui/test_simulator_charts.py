"""The simulator's chart specs (:mod:`eqd_desk.app.ui.simulator_charts`): the right data,
axes and formats, from the shared builders."""

from __future__ import annotations

from typing import Any

from eqd_desk.app.ui import charts, theme
from eqd_desk.app.ui.sim_session import CumAttribution, HistPoint
from eqd_desk.app.ui.simulator_charts import (
    DAY_FORMAT,
    MONEY_AXIS,
    POINT_SIZES,
    day_text,
    explain_chart,
    path_chart,
    pnl_chart,
    with_points,
)

HISTORY = (
    HistPoint(0, 6312.45, 0.146, 0.0),
    HistPoint(1, 6290.0, 0.151, 350.5),
    HistPoint(2, 6330.1, 0.143, -120.25),
)


def _datasets(spec: dict[str, Any]) -> list[list[dict[str, Any]]]:
    return list(spec.get("datasets", {}).values())


def test_day_text() -> None:
    assert day_text(12.0) == "Day 12"


def test_pnl_chart_plots_the_history_in_money_and_whole_days() -> None:
    spec = pnl_chart(HISTORY, "USD").to_dict()
    assert spec["config"]["axisX"] == {"format": DAY_FORMAT, "tickMinStep": 1}
    rows = [r for d in _datasets(spec) for r in d if r.get("series") == "P&L"]
    assert [(r["x"], r["y"]) for r in rows] == [(0.0, 0.0), (1.0, 350.5), (2.0, -120.25)]
    layers = spec["layer"]
    line = next(layer for layer in layers if layer["mark"].get("type") == "line")
    assert line["encoding"]["y"]["title"] == "P&L (USD)"
    # the same money ticks as the explain chart below it (see MONEY_AXIS)
    assert line["encoding"]["y"]["axis"] == {"format": MONEY_AXIS}
    # whole days (config) on top of the shared tidy x axis (encoding)
    assert line["encoding"]["x"]["axis"] == charts.tidy_x_axis()
    assert line["encoding"]["color"]["scale"]["range"] == [theme.ACCENT]
    # the tooltip prints "Day n" and money
    texts = [r for d in _datasets(spec) for r in d if "x_text" in r]
    assert texts[1]["x_text"] == "Day 1"
    assert texts[2]["t0"] == "-120.25"


def test_explain_chart_has_one_signed_bar_per_term() -> None:
    spec = explain_chart(CumAttribution(1.5, -2.0, -3.25, 4.0, 0.0, -0.5, 0.01), "USD").to_dict()
    assert spec["config"]["axisY"] == {"format": MONEY_AXIS}
    rows = next(d for d in _datasets(spec) if d and "tone" in d[0])
    assert [r["label"] for r in rows] == [
        "Delta",
        "Gamma",
        "Theta",
        "Vega",
        "Vanna",
        "Volga",
        "Residual",
    ]
    assert [r["value"] for r in rows] == [1.5, -2.0, -3.25, 4.0, 0.0, -0.5, 0.01]
    assert [r["tone"] for r in rows] == ["pos", "neg", "neg", "pos", "pos", "neg", "pos"]


def test_path_chart_has_spot_and_vol_on_their_own_axes() -> None:
    spec = path_chart(HISTORY).to_dict()
    assert spec["resolve"]["scale"]["y"] == "independent"
    assert spec["config"]["axisX"]["format"] == DAY_FORMAT
    lines = [layer for layer in spec["layer"] if layer["mark"].get("type") == "line"]
    assert [ln["encoding"]["y"]["axis"]["orient"] for ln in lines] == ["left", "right"]
    assert lines[0]["encoding"]["y"]["axis"]["format"] == charts.SPOT_AXIS_FORMAT
    assert lines[1]["encoding"]["y"]["axis"]["format"] == ".1%"
    assert lines[0]["encoding"]["x"]["axis"] == charts.tidy_x_axis()
    rows = _datasets(spec)[0]
    assert [(r["x"], r["l"], r["r"]) for r in rows] == [
        (0.0, 6312.45, 0.146),
        (1.0, 6290.0, 0.151),
        (2.0, 6330.1, 0.143),
    ]
    assert (rows[0]["l_text"], rows[0]["r_text"]) == ("6,312.45", "14.60%")


# ------------------------------------------------------------------ day 0: a one-point path


def _line_marks(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [layer["mark"] for layer in spec["layer"] if layer["mark"].get("type") == "line"]


def test_a_one_point_path_is_drawn_as_dots() -> None:
    """At day 0 the history is one point, which a line cannot draw: the P&L and spot & vol
    charts would be empty frames. Each line then also marks its points (React draws dots)."""
    day0 = HISTORY[:1]
    (pnl,) = _line_marks(pnl_chart(day0, "USD").to_dict())
    assert pnl["point"] == {"filled": True, "size": POINT_SIZES[0]}
    spot, vol = _line_marks(path_chart(day0).to_dict())
    # spot and vol coincide (each is centred on its own axis): the second dot sits inside
    # the first, so both colours show
    assert (spot["point"]["size"], vol["point"]["size"]) == POINT_SIZES
    assert POINT_SIZES[0] > POINT_SIZES[1]


def test_a_path_of_two_or_more_points_is_a_plain_line() -> None:
    for spec in (pnl_chart(HISTORY[:2], "USD").to_dict(), path_chart(HISTORY).to_dict()):
        assert all("point" not in mark for mark in _line_marks(spec))


def test_with_points_leaves_the_original_chart_untouched() -> None:
    chart = pnl_chart(HISTORY, "USD")
    dotted = with_points(chart)
    assert all("point" in mark for mark in _line_marks(dotted.to_dict()))
    assert all("point" not in mark for mark in _line_marks(chart.to_dict()))
