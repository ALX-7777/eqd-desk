"""Specs of the strategy-builder charts: the right curves, reference lines, units and
tick treatment (the rendering itself is the shared ``ui.charts`` look)."""

from __future__ import annotations

from typing import Any

from eqd_desk.app.ui import theme
from eqd_desk.app.ui.strategy_builder_charts import (
    EXPIRY_LABEL,
    NOW_LABEL,
    X_TICK_COUNT,
    greek_profile_chart,
    greek_profile_title,
    pnl_chart,
)
from eqd_desk.app.ui.strategy_builder_legs import make_preset
from eqd_desk.app.ui.strategy_curves import build_axis_meta, greek_sweep, payoff_frame
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


def test_pnl_chart_has_both_curves_spot_and_strikes() -> None:
    spec = pnl_chart(
        payoff_frame(LEGS, MARKET, SNAP.spot),
        spot=MARKET.S,
        strikes=[5975, 6300, 6625, 6300],
        currency="USD",
    ).to_dict()
    text = str(spec)
    assert NOW_LABEL in text
    assert EXPIRY_LABEL in text
    assert "P&L (USD)" in text
    assert rule_xs(spec, theme.ACCENT) == [6250.0]  # the spot slider, not the snapshot
    assert rule_xs(spec, theme.TEXT_DIM)[:3] == [5975, 6300, 6625]  # strikes, deduplicated
    assert len([x for x in rule_xs(spec, theme.TEXT_DIM) if x == 6300]) == 1
    assert spec["config"]["axisX"] == {"tickCount": X_TICK_COUNT, "labelOverlap": True}
    assert spec["height"] == 320


def test_greek_profile_chart_units_and_marker() -> None:
    meta = build_axis_meta("vol", LEGS, MARKET, SNAP.spot)
    sweep = greek_sweep("vol", LEGS, MARKET, SNAP.spot)
    spec = greek_profile_chart(sweep, meta, "vega").to_dict()
    text = str(spec)
    assert greek_profile_title("vega") == "Net Vega"
    assert "Net Vega (per 1 vol pt)" in text
    assert "Vol shift (vol pts)" in text
    assert rule_xs(spec, theme.ACCENT) == [0.0]
    assert spec["height"] == 210
    assert spec["config"]["axisX"]["tickCount"] == X_TICK_COUNT


def test_greek_profile_title_uses_desk_labels() -> None:
    assert greek_profile_title("delta") == "Net Delta"
    assert greek_profile_title("price") == "Net Price"
