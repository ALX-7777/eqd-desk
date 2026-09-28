"""The exotics page's chart specs (:mod:`eqd_desk.app.ui.exotics_views` builders): the
right series, the reference lines at the right levels in the shared rule styles, and the
chart cache returning the very same chart for the same inputs."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from eqd_desk.app.ui import exotics_curves as ec
from eqd_desk.app.ui import exotics_views as ev
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


def test_barrier_chart_overlays_the_vanilla_and_marks_the_levels(snap: MarketSnapshot) -> None:
    i = ec.barrier_seed(snap)
    curve = ec.barrier_curve(i, "gamma", snap.spot)
    spec = ev.barrier_chart(curve, i, "gamma", currency="USD", vanilla=True).to_dict()
    assert series_labels(spec) == ["Vanilla call", "Down-out call"]
    assert rule_values(spec, "x", "barrier") == [i.H]
    assert rule_values(spec, "x", "current") == [i.S]
    assert rule_values(spec, "x", "strike") == [i.K]
    assert spec["config"]["axisX"] == {
        "labelFlush": True,
        "labelBound": ev.X_LABEL_BOUND_PX,
        "labelSeparation": ev.X_LABEL_GAP_PX,
    }
    alone = ev.barrier_chart(curve, i, "gamma", currency="USD", vanilla=False).to_dict()
    assert len(series_labels(alone)) <= 1  # a single series has no legend domain


def test_digital_chart_shows_the_replication_only_for_the_price(snap: MarketSnapshot) -> None:
    i = ec.digital_seed(snap)
    curve = ec.digital_curve(i, 125.0, "price", snap.spot)
    spec = ev.digital_chart(curve, i, "price", currency="USD").to_dict()
    assert series_labels(spec) == ["Call spread", "Digital"]
    greek = ev.digital_chart(curve, i, "gamma", currency="USD").to_dict()
    assert "Call spread" not in series_labels(greek)
    conv = ec.spread_convergence(i, ec.width_grid(ec.digital_bounds(snap.spot)["width"]))
    cspec = ev.convergence_chart(conv, 125.0, currency="USD").to_dict()
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
    spec = ev.digital_chart(curve, i, "price", currency="USD", payout=payout).to_dict()
    assert series_labels(spec) == labels
    conv = ec.spread_convergence(i, [25.0, 125.0, 625.0], payout)
    pair = ec.digital_series_labels(option, payout)
    cspec = ev.convergence_chart(conv, 125.0, currency="USD", labels=pair).to_dict()
    assert series_labels(cspec) == labels


def test_autocall_chart_draws_every_path_and_barrier(snap: MarketSnapshot) -> None:
    i = ec.autocall_seed(snap)
    paths = ec.sample_paths(i)
    spec = ev.autocall_chart(paths, i).to_dict()
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


def test_varswap_charts_mark_the_forward_fair_vol_and_slope(snap: MarketSnapshot) -> None:
    c = ec.varswap_seed(snap)
    data = ec.varswap_data(c, S=snap.spot, r=snap.r, q=snap.q)
    strip = ev.strip_chart(data.strip, data.forward).to_dict()
    assert rule_values(strip, "x", "forward") == [data.forward]
    smile = ev.smile_chart(data.strip, data.forward, data.fair_vol).to_dict()
    assert rule_values(smile, "y", "marker") == [data.fair_vol]
    skew_off = replace(c, skew=False)
    flat = ec.varswap_data(skew_off, S=snap.spot, r=snap.r, q=snap.q)
    flat_spec = ev.smile_chart(flat.strip, flat.forward, flat.fair_vol).to_dict()
    domains = [
        layer["encoding"]["y"]["scale"].get("domain")
        for layer in layers(flat_spec)
        if mark(layer)["type"] == "line"
    ]
    assert domains == [list(ec.vol_axis_domain([*flat.strip["vol"], flat.fair_vol]) or ())]
    skew = ev.skew_chart(data.skew, c.smile_slope).to_dict()
    assert series_labels(skew) == ["ATM vol", "Fair vol"]
    assert rule_values(skew, "x", "current") == [c.slope]
    flat_skew = ev.skew_chart(flat.skew, skew_off.smile_slope).to_dict()
    assert rule_values(flat_skew, "x", "current") == [0.0]


def test_chart_cache_reuses_a_chart_for_the_same_inputs(snap: MarketSnapshot) -> None:
    i = ec.autocall_seed(snap)
    paths = ec.sample_paths(i)
    first = ev.autocall_chart(paths, i)
    assert ev.autocall_chart(paths.copy(), i) is first  # same content, same chart
    other = replace(i, protection_barrier=0.5)
    assert ev.autocall_chart(paths, other) is not first
