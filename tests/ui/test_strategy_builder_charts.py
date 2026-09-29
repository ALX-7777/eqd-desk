"""Specs of the strategy-builder charts: the right curves, reference lines, units and
tick treatment (the rendering itself is the shared ``ui.charts`` look)."""

from __future__ import annotations

from typing import Any

from eqd_desk.app.ui import charts, theme
from eqd_desk.app.ui.strategy_builder_charts import (
    greek_profile_chart,
    greek_profile_title,
    pnl_chart,
)
from eqd_desk.app.ui.strategy_builder_legs import make_preset
from eqd_desk.app.ui.strategy_curves import build_axis_meta, greek_sweep, payoff_frame
from eqd_desk.content import GreekKey
from eqd_desk.data import default_surface, load_snapshot
from eqd_desk.engine.strategy import MarketParams

SNAP = load_snapshot()
MARKET = MarketParams(S=6250.0, r=SNAP.r, q=SNAP.q)
LEGS = make_preset(
    "butterfly",
    spot=SNAP.spot,
    tenor_days=30,
    wing_pct=5,
    strike_step=25,
    vol_for=default_surface().get_vol,
)


def rule_xs(spec: dict[str, Any], color: str) -> list[float]:
    """x of every vertical rule layer drawn in ``color``."""
    out: list[float] = []
    datasets = spec["datasets"]
    for layer in spec["layer"]:
        mark = layer.get("mark", {})
        if isinstance(mark, dict) and mark.get("type") == "rule" and mark.get("color") == color:
            enc = layer.get("encoding", {})
            if "x" in enc and "y" not in enc:
                out.extend(row["x"] for row in datasets[layer["data"]["name"]])
    return out


def line_layers(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """The curve layers (one per series)."""
    return [
        layer
        for layer in spec["layer"]
        if isinstance(layer.get("mark"), dict) and layer["mark"].get("type") == "line"
    ]


def x_axis(spec: dict[str, Any]) -> dict[str, Any]:
    """The x-axis properties of the curves."""
    axis: dict[str, Any] = line_layers(spec)[0]["encoding"]["x"]["axis"]
    return axis


def tooltip_texts(spec: dict[str, Any]) -> list[str]:
    """The x texts of the hover tooltip (the one dataset with an ``x_text`` column)."""
    for rows in spec["datasets"].values():
        if rows and "x_text" in rows[0]:
            return [row["x_text"] for row in rows]
    raise AssertionError("no hover tooltip data")


def test_pnl_chart_has_both_curves_spot_and_strikes() -> None:
    spec = pnl_chart(
        payoff_frame(LEGS, MARKET, SNAP.spot),
        spot=MARKET.S,
        strikes=[5975, 6300, 6625, 6300],
        currency="USD",
    ).to_dict()
    text = str(spec)
    assert "'Now'" in text  # React tooltip names
    assert "'At expiry'" in text
    assert "P&L (USD)" in text
    assert [layer["mark"]["strokeWidth"] for layer in line_layers(spec)] == [1.5, 2.0]
    assert rule_xs(spec, theme.ACCENT) == [6250.0]  # the spot slider, not the snapshot
    assert rule_xs(spec, theme.TEXT_DIM)[:3] == [5975, 6300, 6625]  # strikes, deduplicated
    assert len([x for x in rule_xs(spec, theme.TEXT_DIM) if x == 6300]) == 1
    assert spec["height"] == 320


def test_pnl_chart_axes_read_like_react() -> None:
    spec = pnl_chart(
        payoff_frame(LEGS, MARKET, SNAP.spot), spot=MARKET.S, strikes=[6300], currency="USD"
    ).to_dict()
    axis = x_axis(spec)
    assert axis["format"] == charts.SPOT_AXIS_FORMAT  # whole index points
    assert axis["tickCount"] == charts.X_TICK_COUNT  # tidy: ~8 ticks, labels kept apart
    assert axis["labelOverlap"] is True
    assert "axisX" not in spec["config"]  # no page-local override any more
    y_axis = line_layers(spec)[0]["encoding"]["y"]["axis"]
    assert y_axis["labelExpr"] == charts.FMT_NUM_3_LABEL_EXPR  # fmtNum(v, 3)
    # hover: whole points grouped like the axis (React: `Number(v).toFixed(0)`), P&L in money
    texts = tooltip_texts(spec)
    assert texts[0] == charts.level_text(0.7 * SNAP.spot)
    assert all("," in t and "." not in t for t in texts)  # every spot here is > 1,000
    pnl = [
        row["t0"] for rows in spec["datasets"].values() if rows and "t0" in rows[0] for row in rows
    ]
    assert pnl
    assert all(len(t.rpartition(".")[2]) == 2 for t in pnl)  # money: two decimals


def test_greek_profile_chart_units_and_marker() -> None:
    meta = build_axis_meta("vol", LEGS, MARKET, SNAP.spot)
    sweep = greek_sweep("vol", LEGS, MARKET, SNAP.spot)
    spec = greek_profile_chart(sweep, meta, "vega", currency="USD").to_dict()
    text = str(spec)
    assert greek_profile_title("vega") == "Net Vega"
    assert "Net Vega (per 1 vol pt)" in text
    assert "Vol shift (vol pts)" in text
    assert rule_xs(spec, theme.ACCENT) == [0.0]
    assert spec["height"] == 210
    assert x_axis(spec)["tickCount"] == charts.X_TICK_COUNT
    assert "axisX" not in spec["config"]


def test_greek_profile_title_uses_desk_labels() -> None:
    assert greek_profile_title("delta") == "Net Delta"
    assert greek_profile_title("price") == "Net Price"


def test_greek_profile_axis_titles_carry_the_currency() -> None:
    meta = build_axis_meta("S", LEGS, MARKET, SNAP.spot)
    sweep = greek_sweep("S", LEGS, MARKET, SNAP.spot)

    def y_title(greek: GreekKey, currency: str) -> str:
        spec = greek_profile_chart(sweep, meta, greek, currency=currency).to_dict()
        return str(line_layers(spec)[0]["encoding"]["y"]["title"])

    # the price profile is money, not "(premium)"; the money in a greek unit follows the
    # currency, like the greeks lab's axes (the shared units.axis_title)
    assert y_title("price", "USD") == "Net Price (USD)"
    assert y_title("delta", "EUR") == "Net Delta (per €1 spot)"
    assert y_title("vega", "USD") == "Net Vega (per 1 vol pt)"
