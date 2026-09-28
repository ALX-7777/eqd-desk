"""The greeks lab's curves equal direct engine calls on the React sweep grids, and read the
way the Phase-1 acceptance check says they must (gamma spikes as T shrinks; long-dated
trades gamma for vega)."""

from __future__ import annotations

import dataclasses
import itertools

import pytest

from eqd_desk.app.ui import charts
from eqd_desk.app.ui import greeks_lab_curves as curves
from eqd_desk.app.ui.format import fmt_money, fmt_num, to_precision
from eqd_desk.content import GREEK_KEYS
from eqd_desk.content.greeks import GREEK_GROUPS, XAxisKey
from eqd_desk.data import load_snapshot, seed_inputs
from eqd_desk.engine import GREEK_UNITS, BsmInputs, OptionType, analyze_option

SNAP = load_snapshot()
SEED = seed_inputs(SNAP)
"""The default greeks-lab option: S 6312.45, K 6300, 30 days, σ 14.6 %, r 4.3 %, q 1.3 %."""

TYPES: tuple[OptionType, ...] = ("call", "put")


# ------------------------------------------------------------------ sweep grids


@pytest.mark.parametrize(
    ("x_axis", "lo", "hi"),
    [
        ("S", SNAP.spot * 0.6, SNAP.spot * 1.4),
        ("sigma", 0.02, 0.8),
        ("T", 0.003, 2.0),
    ],
)
def test_sweep_ranges_are_the_react_ones(x_axis: XAxisKey, lo: float, hi: float) -> None:
    assert curves.x_range(x_axis, SNAP.spot) == (lo, hi)
    frame = curves.greek_sweep(SEED, "call", x_axis, SNAP.spot)
    assert list(frame["x"]) == charts.sweep_x(lo, hi, 100)  # N = 100 → 101 points
    assert list(frame.columns) == ["x", *GREEK_KEYS]


@pytest.mark.parametrize("option_type", TYPES)
@pytest.mark.parametrize("x_axis", curves.X_AXES)
def test_every_sweep_point_is_the_engine_value(option_type: OptionType, x_axis: XAxisKey) -> None:
    frame = curves.greek_sweep(SEED, option_type, x_axis, SNAP.spot)
    for i, x in enumerate(frame["x"]):
        expected = analyze_option(dataclasses.replace(SEED, **{x_axis: x}), option_type)
        for key in GREEK_KEYS:
            assert frame[key].iloc[i] == getattr(expected.reported, key), (x_axis, x, key)


def test_spot_range_follows_the_snapshot_not_the_spot_input() -> None:
    moved = dataclasses.replace(SEED, S=5000.0)
    assert list(curves.greek_sweep(moved, "call", "S", SNAP.spot)["x"]) == list(
        curves.greek_sweep(SEED, "call", "S", SNAP.spot)["x"]
    )
    # ...while the other inputs are held at their current values
    vol = curves.greek_sweep(moved, "call", "sigma", SNAP.spot)
    x0 = float(vol["x"].iloc[0])
    assert (
        vol["price"].iloc[0]
        == analyze_option(
            BsmInputs(S=5000.0, K=SEED.K, T=SEED.T, r=SEED.r, q=SEED.q, sigma=x0), "call"
        ).reported.price
    )


def test_sweep_resolution_can_be_changed() -> None:
    frame = curves.greek_sweep(SEED, "put", "T", SNAP.spot, n=10)
    assert list(frame["x"]) == charts.sweep_x(0.003, 2.0, 10)


# ------------------------------------------------------------------ payoff


@pytest.mark.parametrize("option_type", TYPES)
def test_payoff_curve_is_intrinsic_at_expiry_and_premium_now(option_type: OptionType) -> None:
    frame = curves.payoff_curve(SEED, option_type, SNAP.spot)
    xs = charts.sweep_x(SNAP.spot * 0.6, SNAP.spot * 1.4, 100)
    assert list(frame["spot"]) == xs
    for x, expiry, now in zip(xs, frame["expiry"], frame["now"], strict=True):
        payoff = max(x - SEED.K, 0.0) if option_type == "call" else max(SEED.K - x, 0.0)
        assert expiry == payoff
        assert now == analyze_option(dataclasses.replace(SEED, S=x), option_type).reported.price


def test_intrinsic_value() -> None:
    assert curves.intrinsic_value(110.0, 100.0, "call") == 10.0
    assert curves.intrinsic_value(90.0, 100.0, "call") == 0.0
    assert curves.intrinsic_value(90.0, 100.0, "put") == 10.0
    assert curves.intrinsic_value(110.0, 100.0, "put") == 0.0


# ------------------------------------------------------------------ readout numbers


def test_seed_premium_split_matches_the_react_readout() -> None:
    """The React screenshot: 119.61, intrinsic 12.45 · time value 107.16, delta 0.54994."""
    analysis = analyze_option(SEED, "call")
    split = curves.premium_split(analysis)
    assert split.premium == analysis.reported.price
    assert fmt_money(split.premium) == "119.61"
    assert fmt_money(split.intrinsic) == "12.45"
    assert fmt_money(split.time_value) == "107.16"
    assert fmt_num(analysis.reported.delta) == "0.54994"


def test_premium_split_of_an_otm_put_is_all_time_value() -> None:
    analysis = analyze_option(SEED, "put")
    split = curves.premium_split(analysis)
    assert split.intrinsic == 0.0
    assert split.time_value == split.premium == analysis.reported.price


def test_raw_partial_rows_show_the_raw_derivatives_to_six_figures() -> None:
    analysis = analyze_option(SEED, "call")
    rows = curves.raw_partial_rows(analysis, selected="vega")
    groups = [r.label for r in rows if r.kind == "group"]
    assert groups == [g.title for g in GREEK_GROUPS]
    values = [r for r in rows if r.kind == "row"]
    keys = [k for g in GREEK_GROUPS for k in g.keys]
    assert [r.label for r in values] == [GREEK_UNITS[k].label for k in keys]
    for row, key in zip(values, keys, strict=True):
        raw = getattr(analysis.raw, key)
        assert row.value == raw
        assert row.text == to_precision(raw, 6)
        assert row.unit == curves.raw_scale_text(key)
        assert row.selected == (key == "vega")
    # raw vega is per 1.00 of vol: 100 × the desk number
    vega = next(r for r in values if r.label == "Vega")
    assert vega.value == pytest.approx(100 * analysis.reported.vega)


def test_raw_scale_text() -> None:
    assert curves.raw_scale_text("delta") == "desk = raw"
    assert curves.raw_scale_text("vega") == "desk = raw ÷100"
    assert curves.raw_scale_text("theta") == "desk = raw ÷365"
    assert curves.raw_scale_text("volga") == "desk = raw ÷10000"


# ------------------------------------------------------------------ x formatting


@pytest.mark.parametrize(
    ("x_axis", "value", "text"),
    [
        ("S", 6312.45, "6312"),
        ("S", 3787.47, "3787"),
        ("sigma", 0.146, "15%"),
        ("sigma", 0.8, "80%"),
        ("T", 30 / 365, "0.08"),
        ("T", 2.0, "2.00"),
    ],
)
def test_x_tick_is_the_react_tooltip_label(x_axis: XAxisKey, value: float, text: str) -> None:
    assert curves.x_tick(x_axis, value) == text


def test_current_x_reads_the_swept_input() -> None:
    assert curves.current_x(SEED, "S") == SEED.S
    assert curves.current_x(SEED, "sigma") == SEED.sigma
    assert curves.current_x(SEED, "T") == SEED.T


# ------------------------------------------------------------------ acceptance check


def atm_gamma(T: float) -> float:
    """Peak of the gamma-vs-spot curve of the seed call with time to expiry ``T``."""
    frame = curves.greek_sweep(dataclasses.replace(SEED, T=T), "call", "S", SNAP.spot)
    return float(frame["gamma"].max())


def test_shrinking_T_spikes_atm_gamma() -> None:
    month, three_days, one_day = atm_gamma(30 / 365), atm_gamma(3 / 365), atm_gamma(1 / 365)
    assert three_days > 3 * month
    assert one_day > 5 * month
    assert one_day > three_days > month


def test_longer_T_trades_gamma_for_vega() -> None:
    frame = curves.greek_sweep(SEED, "call", "T", SNAP.spot)
    gamma, vega = list(frame["gamma"]), list(frame["vega"])
    assert all(b < a for a, b in itertools.pairwise(gamma))
    assert all(b > a for a, b in itertools.pairwise(vega))
    assert gamma[0] > 20 * gamma[-1]
    assert vega[-1] > 20 * vega[0]
