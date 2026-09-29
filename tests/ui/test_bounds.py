"""The shared input bounds and grids reproduce the React constants, and every page uses
the same ones."""

from __future__ import annotations

import pytest

from eqd_desk.app.ui import bounds
from eqd_desk.app.ui import exotics_curves as ec
from eqd_desk.app.ui import greeks_lab_curves as lab_curves
from eqd_desk.app.ui.greeks_lab_inputs import input_specs
from eqd_desk.app.ui.sim_session import desk_config
from eqd_desk.data import load_snapshot


@pytest.mark.parametrize(
    ("spot", "level", "listed"),
    [
        (6312.45, 1.0, 25.0),
        (4000.0, 1.0, 25.0),
        (2000.0, 1.0, 25.0),
        (631.0, 0.5, 5.0),
        (200.0, 0.5, 5.0),
        (63.0, 0.1, 5.0),
    ],
)
def test_steps_match_react(spot: float, level: float, listed: float) -> None:
    assert bounds.level_step(spot) == level  # InputPanel stepFor
    assert bounds.listed_strike_step(spot) == listed  # exotics / simulator STRIKE_STEP


def test_react_input_ranges() -> None:
    assert bounds.RATE_BOUNDS == bounds.Bounds(-0.02, 0.10, 0.0005)
    assert bounds.DIV_BOUNDS == bounds.Bounds(0.0, 0.06, 0.0005)
    assert bounds.T_BOUNDS == bounds.Bounds(0.003, 2.0, 0.003)
    assert bounds.SPOT_RANGE_FACTORS == (0.6, 1.4)


def test_pages_share_the_bounds() -> None:
    snap = load_snapshot()
    specs = {s.field: s for s in input_specs(snap.spot, snap.currency)}
    assert (specs["r"].min_value, specs["r"].max_value, specs["r"].step) == (
        bounds.RATE_BOUNDS.lo,
        bounds.RATE_BOUNDS.hi,
        bounds.RATE_BOUNDS.step,
    )
    assert (specs["q"].min_value, specs["q"].max_value) == (
        bounds.DIV_BOUNDS.lo,
        bounds.DIV_BOUNDS.hi,
    )
    assert (specs["T"].min_value, specs["T"].max_value) == lab_curves.T_RANGE
    assert specs["S"].step == bounds.level_step(snap.spot)
    for view in (ec.barrier_bounds(snap.spot), ec.digital_bounds(snap.spot)):
        assert view["r"] == bounds.RATE_BOUNDS
        assert view["q"] == bounds.DIV_BOUNDS
    assert desk_config(snap).strike_step == bounds.listed_strike_step(snap.spot)
