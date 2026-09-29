"""Strategy-builder curves: every plotted number equals the engine evaluated on the React
grid, break-evens are exact zeros of the expiry P&L, and the greek sweep follows
``buildAxisMeta`` (ranges, floors, ticks)."""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from eqd_desk.app.ui.charts import sweep_x
from eqd_desk.app.ui.strategy_builder_legs import make_preset
from eqd_desk.app.ui.strategy_curves import (
    FRONT_EXPIRY_GAP,
    N_POINTS,
    X_AXIS_CHOICES,
    StrategyXAxis,
    break_evens,
    build_axis_meta,
    greek_sweep,
    greeks_at,
    payoff_frame,
    spot_range,
    sweep_heading,
    unique_strikes,
)
from eqd_desk.data import default_surface, load_snapshot
from eqd_desk.engine.presets import PresetName
from eqd_desk.engine.strategy import (
    GREEK_FIELDS,
    Leg,
    MarketParams,
    analyze_position,
    front_expiry,
    payoff_profile,
    position_premium,
    position_value_at,
)

SNAP = load_snapshot()
SPOT = SNAP.spot
MARKET = MarketParams(S=SNAP.spot, r=SNAP.r, q=SNAP.q)


def preset(
    name: PresetName, *, spot: float = SPOT, tenor: int = 30, wing: int = 5
) -> tuple[Leg, ...]:
    return make_preset(
        name,
        spot=spot,
        tenor_days=tenor,
        wing_pct=wing,
        strike_step=25,
        vol_for=default_surface().get_vol,
    )


BUTTERFLY = preset("butterfly")
AXES: tuple[StrategyXAxis, ...] = ("S", "vol", "time")


def expiry_pnl(legs: tuple[Leg, ...], s: float) -> float:
    return position_value_at(legs, s, front_expiry(legs), MARKET) - position_premium(legs, MARKET)


# ------------------------------------------------------------------ P&L vs spot


def test_spot_range_is_70_to_130_percent_of_the_snapshot_spot() -> None:
    assert spot_range(SPOT) == (SPOT * 0.7, SPOT * 1.3)


def test_payoff_frame_is_the_engine_profile_on_the_react_grid() -> None:
    frame = payoff_frame(BUTTERFLY, MARKET, SPOT)
    pts = payoff_profile(BUTTERFLY, MARKET, SPOT * 0.7, SPOT * 1.3, 120)
    assert len(frame) == N_POINTS + 1 == 121
    assert frame["S"].tolist() == [p.S for p in pts]
    assert frame["S"].tolist() == sweep_x(SPOT * 0.7, SPOT * 1.3, 120)
    assert frame["expiry"].tolist() == [p.expiry_pnl for p in pts]
    assert frame["now"].tolist() == [p.now_pnl for p in pts]


def test_payoff_frame_uses_the_slider_market_but_the_snapshot_range() -> None:
    moved = dataclasses.replace(MARKET, S=6000.0)
    frame = payoff_frame(BUTTERFLY, moved, SPOT)
    assert frame["S"].iloc[0] == SPOT * 0.7  # axis still around the snapshot spot
    premium = position_premium(BUTTERFLY, moved)  # but the premium is paid at the slider
    assert frame["expiry"].iloc[0] == pytest.approx(-premium, abs=1e-9)


def test_butterfly_break_evens_are_wing_plus_and_minus_premium() -> None:
    premium = position_premium(BUTTERFLY, MARKET)
    lo_be, hi_be = break_evens(BUTTERFLY, MARKET, SPOT)
    assert lo_be == pytest.approx(5975 + premium, abs=1e-8)
    assert hi_be == pytest.approx(6625 - premium, abs=1e-8)
    assert (round(lo_be, 2), round(hi_be, 2)) == (6121.39, 6478.61)


def test_straddle_and_spread_break_evens() -> None:
    straddle = preset("straddle")
    p = position_premium(straddle, MARKET)
    assert break_evens(straddle, MARKET, SPOT) == pytest.approx((6300 - p, 6300 + p), abs=1e-8)
    spread = preset("call-vertical")
    p = position_premium(spread, MARKET)
    assert break_evens(spread, MARKET, SPOT) == pytest.approx((6300 + p,), abs=1e-8)


@pytest.mark.parametrize("name", ["calendar", "iron-condor", "strangle", "risk-reversal"])
def test_break_evens_are_zeros_of_the_expiry_pnl(name: PresetName) -> None:
    legs = preset(name)
    roots = break_evens(legs, MARKET, SPOT)
    assert roots, name
    assert list(roots) == sorted(roots)
    for r in roots:
        assert abs(expiry_pnl(legs, r)) < 1e-7
        # a real crossing: the sign differs a little either side
        assert (expiry_pnl(legs, r - 1) < 0) != (expiry_pnl(legs, r + 1) < 0)


def test_narrow_butterfly_crossings_between_grid_points_are_found() -> None:
    # 1 % wings: 63.1 points, rounded to the 25-point grid → 75, so the whole tent is 150
    # points wide and spans fewer than five 31.6-point grid cells.
    legs = preset("butterfly", wing=1)
    roots = break_evens(legs, MARKET, SPOT)
    assert len(roots) == 2
    for r in roots:
        assert abs(expiry_pnl(legs, r)) < 1e-7


def test_no_break_even_without_legs_or_crossing() -> None:
    assert break_evens((), MARKET, SPOT) == ()
    far_put = (Leg("p", "put", "long", 1, 0.5 * SPOT, 30 / 365, 0.3),)  # always loses premium
    assert break_evens(far_put, MARKET, SPOT) == ()


def test_unique_strikes_keep_leg_order() -> None:
    assert unique_strikes(BUTTERFLY) == (5975.0, 6300.0, 6625.0)
    assert unique_strikes(preset("calendar")) == (6300.0,)
    assert unique_strikes(()) == ()


# ------------------------------------------------------------------ axis meta


def test_spot_axis_meta() -> None:
    moved = dataclasses.replace(MARKET, S=6100.0)
    meta = build_axis_meta("S", BUTTERFLY, moved, SPOT)
    assert (meta.label, meta.lo, meta.hi, meta.current) == ("Spot", SPOT * 0.7, SPOT * 1.3, 6100.0)
    assert meta.plot_scale == 1.0
    assert sweep_heading(meta) == "spot"
    assert meta.tick(6312.45) == "6,312"  # grouped like the spot axis
    assert meta.tick(6312.5) == "6,313"  # halves round away from 0, as toFixed


def test_vol_axis_meta() -> None:
    meta = build_axis_meta("vol", BUTTERFLY, MARKET, SPOT)
    assert (meta.label, meta.lo, meta.hi, meta.current) == ("Vol shift", -0.1, 0.1, 0.0)
    assert sweep_heading(meta) == "vol shift"
    assert meta.plot_scale == 100.0
    assert [meta.tick(p) for p in (5.0, -10.0, 0.0, 1e-15)] == ["+5pt", "-10pt", "+0pt", "+0pt"]


def test_time_axis_meta() -> None:
    meta = build_axis_meta("time", BUTTERFLY, MARKET, SPOT)
    assert (meta.label, meta.lo, meta.current) == ("Time elapsed", 0.0, 0.0)
    assert meta.hi == 30 / 365 - FRONT_EXPIRY_GAP
    assert meta.plot_scale == 365.0
    assert meta.tick(12.4) == "12d"
    assert meta.tick(12.5) == "13d"
    # calendars stop at the FRONT expiry; very short or no legs keep at least one day
    assert build_axis_meta("time", preset("calendar"), MARKET, SPOT).hi == meta.hi
    short = (dataclasses.replace(BUTTERFLY[0], T=0.5 / 365),)
    assert build_axis_meta("time", short, MARKET, SPOT).hi == 1 / 365
    assert build_axis_meta("time", (), MARKET, SPOT).hi == 1 / 365


def test_axis_options_are_react_labels() -> None:
    assert dict(X_AXIS_CHOICES) == {"S": "Spot", "vol": "Vol", "time": "Time"}


# ------------------------------------------------------------------ greek at x


def test_greeks_at_spot_revalues_the_position() -> None:
    got = greeks_at("S", BUTTERFLY, MARKET, 6400.0)
    assert got == analyze_position(BUTTERFLY, dataclasses.replace(MARKET, S=6400.0)).reported


def test_greeks_at_vol_shift_moves_every_leg_with_a_floor() -> None:
    got = greeks_at("vol", BUTTERFLY, MARKET, 0.05)
    shifted = [dataclasses.replace(leg, sigma=leg.sigma + 0.05) for leg in BUTTERFLY]
    assert got == analyze_position(shifted, MARKET).reported
    floored = greeks_at("vol", BUTTERFLY, MARKET, -0.5)
    at_floor = [dataclasses.replace(leg, sigma=0.01) for leg in BUTTERFLY]
    assert floored == analyze_position(at_floor, MARKET).reported


def test_greeks_at_time_ages_every_leg_with_a_floor() -> None:
    cal = preset("calendar")
    t = 10 / 365
    got = greeks_at("time", cal, MARKET, t)
    aged = [dataclasses.replace(leg, T=leg.T - t) for leg in cal]
    assert got == analyze_position(aged, MARKET).reported
    past = greeks_at("time", cal, MARKET, 1.0)
    floored = [dataclasses.replace(leg, T=max(1e-6, leg.T - 1.0)) for leg in cal]
    assert past == analyze_position(floored, MARKET).reported


# ------------------------------------------------------------------ sweeps


@pytest.mark.parametrize("axis", AXES)
def test_greek_sweep_is_the_engine_on_the_react_grid(axis: StrategyXAxis) -> None:
    frame = greek_sweep(axis, BUTTERFLY, MARKET, SPOT)
    meta = build_axis_meta(axis, BUTTERFLY, MARKET, SPOT)
    xs = sweep_x(meta.lo, meta.hi, N_POINTS)
    assert frame["x"].tolist() == xs
    assert frame["x_plot"].tolist() == [x * meta.plot_scale for x in xs]
    assert list(frame.columns) == ["x", "x_plot", *GREEK_FIELDS]
    for i in (0, 37, 60, 120):
        want = greeks_at(axis, BUTTERFLY, MARKET, xs[i]).as_dict()
        assert [float(frame[f].iloc[i]) for f in GREEK_FIELDS] == [want[f] for f in GREEK_FIELDS]


def test_spot_sweep_delta_passes_through_the_readout_at_spot() -> None:
    # sweeping spot and reading the grid point nearest the market spot gives the readout's
    # delta up to the grid spacing: a sanity check that the axes are not swapped.
    frame = greek_sweep("S", BUTTERFLY, MARKET, SPOT)
    i = int(np.argmin(np.abs(frame["x"].to_numpy() - SPOT)))
    readout = analyze_position(BUTTERFLY, MARKET).reported.delta
    assert float(frame["delta"].iloc[i]) == pytest.approx(readout, abs=0.02)
    assert isinstance(frame, pd.DataFrame)


def test_empty_position_sweeps_are_flat_zero() -> None:
    for axis in AXES:
        frame = greek_sweep(axis, (), MARKET, SPOT)
        assert len(frame) == 121
        assert (frame[list(GREEK_FIELDS)] == 0).all().all()
    assert (payoff_frame((), MARKET, SPOT)[["expiry", "now"]] == 0).all().all()
