"""The exotics page's chart specs (the pure :mod:`eqd_desk.app.ui.exotics_charts`
builders): the right series, the reference lines at the right levels in the shared rule
styles, the shared axis formats and the named chart heights. (The views' chart cache is
tested with the app, ``tests/app/test_exotics.py``.)"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from eqd_desk.app.ui import charts
from eqd_desk.app.ui import exotics_charts as xc
from eqd_desk.app.ui import exotics_curves as ec
from eqd_desk.app.ui.charts import RULE_STYLES, RuleStyle
from eqd_desk.data import MarketSnapshot, load_snapshot
from eqd_desk.engine import OptionType

Spec = dict[str, Any]


@pytest.fixture(scope="module")
def snap() -> MarketSnapshot:
    return load_snapshot()


def layers(spec: Spec) -> Iterator[Spec]:
    """Every leaf layer of a (possibly nested) layered spec."""
    for layer in spec.get("layer", []):
        if "layer" in layer:
            yield from layers(layer)
        else:
            yield layer


def mark(layer: Spec) -> Spec:
    m = layer["mark"]
    return {"type": m} if isinstance(m, str) else m


def rows(spec: Spec, layer: Spec) -> list[Spec]:
    """The data rows of a layer (datasets are stored by name at the top level)."""
    rows_: list[Spec] = spec["datasets"][layer["data"]["name"]]
    return rows_


def rule_values(spec: Spec, field: str, style: RuleStyle) -> list[float]:
    """The ``field`` positions of the rule layers drawn in the ``style`` look (colour and
    dash; several styles share a colour)."""
    look = RULE_STYLES[style]
    dash = list(look.dash) or [1, 0]
    out: list[float] = []
    for layer in layers(spec):
        m = mark(layer)
        if m["type"] == "rule" and m.get("color") == look.color and m.get("strokeDash") == dash:
            out.extend(float(r[field]) for r in rows(spec, layer) if field in r)
    return out


def series_labels(spec: Spec) -> list[str]:
    """The legend domain of the line layers (the series labels, in drawing order)."""
    for layer in layers(spec):
        if mark(layer)["type"] == "line":
            labels: list[str] = layer["encoding"]["color"]["scale"]["domain"]
            return labels
    return []


def line_axes(spec: Spec) -> tuple[Spec, Spec]:
    """The (x, y) axis properties of the first line layer."""
    enc = next(layer for layer in layers(spec) if mark(layer)["type"] == "line")["encoding"]
    return enc["x"].get("axis", {}), enc["y"].get("axis", {})


def test_barrier_chart_overlays_the_vanilla_and_marks_the_levels(snap: MarketSnapshot) -> None:
    i = ec.barrier_seed(snap)
    curve = ec.barrier_curve(i, "gamma", snap.spot)
    spec = xc.barrier_chart(curve, i, "gamma", currency="USD", vanilla=True).to_dict()
    assert series_labels(spec) == ["Vanilla call", "Down-out call"]
    assert rule_values(spec, "x", "barrier") == [i.H]
    assert rule_values(spec, "x", "current") == [i.S]
    assert rule_values(spec, "x", "strike") == [i.K]
    alone = xc.barrier_chart(curve, i, "gamma", currency="USD", vanilla=False).to_dict()
    assert len(series_labels(alone)) <= 1  # a single series has no legend domain


def test_spot_charts_read_like_the_react_charts(snap: MarketSnapshot) -> None:
    """The shared axes: x labels tidied (whole, never colliding), y ticks fmtNum(v, 3) as
    React's ``tickFormatter`` (vol axes keep their percent format)."""
    b = ec.barrier_seed(snap)
    d = ec.digital_seed(snap)
    c = ec.varswap_seed(snap)
    vs = ec.varswap_data(c, S=snap.spot, r=snap.r, q=snap.q)
    specs = {
        "barrier": xc.barrier_chart(
            ec.barrier_curve(b, "gamma", snap.spot), b, "gamma", currency="USD", vanilla=True
        ),
        "digital": xc.digital_chart(
            ec.digital_curve(d, 125.0, "price", snap.spot), d, "price", currency="USD"
        ),
        "strip": xc.strip_chart(vs.strip, vs.forward),
        "smile": xc.smile_chart(vs.strip, vs.forward, vs.fair_vol),
        "skew": xc.skew_chart(vs.skew, c.smile_slope),
    }
    for name, chart in specs.items():
        x_axis, y_axis = line_axes(chart.to_dict())
        assert x_axis == charts.tidy_x_axis(), name
        expected_y = {"smile": {"format": ".0%"}, "skew": {"format": ".1%"}}.get(
            name, charts.axis_format(charts.FMT_NUM_3)
        )
        assert y_axis == expected_y, name


def test_digital_chart_shows_the_replication_only_for_the_price(snap: MarketSnapshot) -> None:
    i = ec.digital_seed(snap)
    curve = ec.digital_curve(i, 125.0, "price", snap.spot)
    spec = xc.digital_chart(curve, i, "price", currency="USD").to_dict()
    assert series_labels(spec) == ["Call spread", "Digital"]
    greek = xc.digital_chart(curve, i, "gamma", currency="USD").to_dict()
    assert "Call spread" not in series_labels(greek)
    conv = ec.spread_convergence(i, ec.width_grid(ec.digital_bounds(snap.spot)["width"]))
    cspec = xc.convergence_chart(conv, 125.0, currency="USD").to_dict()
    assert rule_values(cspec, "x", "current") == [125.0]
    assert series_labels(cspec) == ["Call spread", "Digital"]


@pytest.mark.parametrize(
    ("option", "payout", "labels"),
    [
        ("put", "cash", ["Put spread", "Digital"]),
        ("call", "asset", ["Vanilla + call spreads", "Asset-or-nothing"]),
        ("put", "asset", ["Put spreads − vanilla", "Asset-or-nothing"]),
    ],
)
def test_digital_chart_names_the_replication_it_draws(
    snap: MarketSnapshot, option: OptionType, payout: ec.DigitalPayout, labels: list[str]
) -> None:
    i = replace(ec.digital_seed(snap), type=option)
    curve = ec.digital_curve(i, 125.0, "price", snap.spot, payout)
    spec = xc.digital_chart(curve, i, "price", currency="USD", payout=payout).to_dict()
    assert series_labels(spec) == labels
    conv = ec.spread_convergence(i, [25.0, 125.0, 625.0], payout)
    pair = ec.digital_series_labels(option, payout)
    cspec = xc.convergence_chart(conv, 125.0, currency="USD", labels=pair).to_dict()
    assert series_labels(cspec) == labels


def test_autocall_chart_draws_every_path_and_barrier(snap: MarketSnapshot) -> None:
    i = ec.autocall_seed(snap)
    paths = ec.sample_paths(i)
    spec = xc.autocall_chart(paths, i).to_dict()
    lines = [layer for layer in layers(spec) if mark(layer)["type"] == "line"]
    assert len(lines) == 1  # one layer, grouped by path
    assert lines[0]["encoding"]["detail"]["field"] == "path"
    assert {r["path"] for r in rows(spec, lines[0])} == {f"p{p}" for p in range(8)}
    assert len(rows(spec, lines[0])) == 8 * 61
    lv = ec.autocall_levels(i)
    assert rule_values(spec, "y", "autocall") == [lv.autocall]
    assert rule_values(spec, "y", "coupon") == [lv.coupon]
    assert rule_values(spec, "y", "protection") == [lv.protection]
    assert rule_values(spec, "t", "marker") == [0.5, 1.0, 1.5, 2.0, 2.5]
    labels = [
        r["label"]
        for layer in layers(spec)
        if mark(layer)["type"] == "text"
        for r in rows(spec, layer)
    ]
    assert labels == ["autocall", "coupon", "protection"]
    assert lines[0]["encoding"]["x"]["scale"]["domain"] == [0.0, 3.0]
    # the time axis: one-decimal years, tidied like every x axis (0 and the maturity kept
    # inside the plot), with its own tick-count hint
    assert lines[0]["encoding"]["x"]["axis"] == {
        "format": ".1f",
        **charts.tidy_x_axis(xc.AUTOCALL_X_TICK_COUNT),
    }


def test_varswap_charts_mark_the_forward_fair_vol_and_slope(snap: MarketSnapshot) -> None:
    c = ec.varswap_seed(snap)
    data = ec.varswap_data(c, S=snap.spot, r=snap.r, q=snap.q)
    strip = xc.strip_chart(data.strip, data.forward).to_dict()
    assert rule_values(strip, "x", "forward") == [data.forward]
    smile = xc.smile_chart(data.strip, data.forward, data.fair_vol).to_dict()
    assert rule_values(smile, "y", "marker") == [data.fair_vol]
    skew_off = replace(c, skew=False)
    flat = ec.varswap_data(skew_off, S=snap.spot, r=snap.r, q=snap.q)
    flat_spec = xc.smile_chart(flat.strip, flat.forward, flat.fair_vol).to_dict()
    domains = [
        layer["encoding"]["y"]["scale"].get("domain")
        for layer in layers(flat_spec)
        if mark(layer)["type"] == "line"
    ]
    assert domains == [list(ec.vol_axis_domain([*flat.strip["vol"], flat.fair_vol]) or ())]
    skew = xc.skew_chart(data.skew, c.smile_slope).to_dict()
    assert series_labels(skew) == ["ATM vol", "Fair vol"]
    assert rule_values(skew, "x", "current") == [c.slope]
    flat_skew = xc.skew_chart(flat.skew, skew_off.smile_slope).to_dict()
    assert rule_values(flat_skew, "x", "current") == [0.0]


def test_chart_heights_are_the_named_ones(snap: MarketSnapshot) -> None:
    """Every exotics chart is drawn at one of the shared, named heights: the characteristic
    charts tall, the strip medium (React's 250 px), the companions short."""
    b = ec.barrier_seed(snap)
    d = ec.digital_seed(snap)
    a = ec.autocall_seed(snap)
    c = ec.varswap_seed(snap)
    vs = ec.varswap_data(c, S=snap.spot, r=snap.r, q=snap.q)
    conv = ec.spread_convergence(d, [25.0, 125.0, 625.0])
    heights = {
        "barrier": xc.barrier_chart(
            ec.barrier_curve(b, "gamma", snap.spot), b, "gamma", currency="USD", vanilla=True
        ),
        "digital": xc.digital_chart(
            ec.digital_curve(d, 125.0, "price", snap.spot), d, "price", currency="USD"
        ),
        "convergence": xc.convergence_chart(conv, 125.0, currency="USD"),
        "autocall": xc.autocall_chart(ec.sample_paths(a), a),
        "strip": xc.strip_chart(vs.strip, vs.forward),
        "smile": xc.smile_chart(vs.strip, vs.forward, vs.fair_vol),
        "skew": xc.skew_chart(vs.skew, c.smile_slope),
    }
    assert {name: chart.to_dict()["height"] for name, chart in heights.items()} == {
        "barrier": charts.TALL_HEIGHT,
        "digital": charts.TALL_HEIGHT,
        "convergence": charts.SHORT_HEIGHT,
        "autocall": charts.TALL_HEIGHT,
        "strip": charts.MEDIUM_HEIGHT,
        "smile": charts.SHORT_HEIGHT,
        "skew": charts.SHORT_HEIGHT,
    }
    assert charts.SHORT_HEIGHT < charts.MEDIUM_HEIGHT == 250 < charts.DEFAULT_HEIGHT
