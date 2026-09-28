"""Historical replay. Port of the ``historical replay`` block of
``web/src/engine/sim/__tests__/sim.test.ts``, plus window edge cases."""

from __future__ import annotations

import pytest

from eqd_desk.engine.sim import (
    HistoryPoint,
    ReplayBase,
    ReplayWindow,
    pick_window,
    replay_state,
    window_steps,
)
from tests.engine.sim.common import close

SERIES = [HistoryPoint(date=f"d{k}", spot=3000 + k * 5, vix=15 + (k % 10)) for k in range(200)]
BASE = ReplayBase(r=0.03, q=0.01, skew_slope=-0.4, skew_curv=0.5, dt=1 / 252)


def test_picks_a_window_and_maps_points_to_market_states() -> None:
    win = pick_window(SERIES, 60, 0.5)
    assert window_steps(win) == 60
    s0 = replay_state(win, 0, BASE)
    assert s0.spot == win.points[0].spot
    assert s0.atm_vol == close(win.points[0].vix / 100, 9)
    assert s0.skew_slope == -0.4
    assert replay_state(win, 5, BASE).t == close(5 / 252, 9)
    # clamps past the end
    assert replay_state(win, 999, BASE).spot == win.points[-1].spot


# --- beyond the TS tests -------------------------------------------------------------------


def test_window_start_is_driven_by_the_uniform_draw() -> None:
    # 200 points, 60 steps ⇒ max start 139; u = 0.5 ⇒ floor(0.5·140) = 70
    win = pick_window(SERIES, 60, 0.5)
    assert win.start_index == 70
    assert win.points == tuple(SERIES[70:131])
    assert pick_window(SERIES, 60, 0.0).start_index == 0
    assert pick_window(SERIES, 60, 0.999999).start_index == 139


def test_a_series_shorter_than_the_window_is_replayed_whole() -> None:
    win = pick_window(SERIES[:10], 60, 0.7)
    assert win.start_index == 0
    assert len(win.points) == 10
    assert window_steps(win) == 9
    assert window_steps(ReplayWindow(points=(), start_index=0)) == 0


def test_replay_state_clamps_index_and_floors_vol() -> None:
    low_vix = [HistoryPoint(date="x", spot=4000, vix=3.0), HistoryPoint("y", 4010, 20)]
    win = pick_window(low_vix, 1, 0.3)
    s = replay_state(win, -5, BASE)
    assert s.t == 0
    assert s.atm_vol == 0.05  # VIX 3 → floored at 5%
    assert (s.r, s.q, s.skew_curv) == (0.03, 0.01, 0.5)
    with pytest.raises(ValueError, match="no points"):
        replay_state(ReplayWindow(points=(), start_index=0), 0, BASE)
