"""The simulator's Auto clock (:mod:`eqd_desk.app.ui.simulator_clock`): the fragment timer,
how many steps a rerun takes, and when Auto counts as abandoned."""

from __future__ import annotations

import pytest

from eqd_desk.app.ui.simulator_clock import (
    AUTO_DEFAULT_MS,
    AUTO_MAX_MS,
    AUTO_MIN_MS,
    AUTO_STEP_MS,
    MAX_CATCH_UP,
    STALE_MIN_S,
    auto_interval,
    auto_stale,
    auto_steps,
)


def test_speed_slider_matches_react() -> None:
    assert (AUTO_MIN_MS, AUTO_MAX_MS, AUTO_STEP_MS, AUTO_DEFAULT_MS) == (120, 3000, 60, 650)
    assert (AUTO_DEFAULT_MS - AUTO_MIN_MS) % AUTO_STEP_MS == 50  # React's default is off-grid too


def test_auto_interval_is_the_speed_in_seconds_while_playing() -> None:
    assert auto_interval(True, 650) == 0.65
    assert auto_interval(False, 650) is None


@pytest.mark.parametrize(
    ("elapsed", "steps", "new_last"),
    [
        (0.0, 0, 10.0),  # a click right after a step
        (0.3, 0, 10.0),  # still less than half an interval
        (0.5, 1, 11.0),  # the timer fired early: one step, schedule kept
        (1.0, 1, 11.0),  # on time
        (1.7, 1, 11.0),  # a slow render: the remainder carries over
        (2.2, 2, 12.0),  # two intervals behind: catch up
        (4.0, 4, 14.0),
    ],
)
def test_auto_steps_follow_the_schedule(elapsed: float, steps: int, new_last: float) -> None:
    got_steps, got_last = auto_steps(10.0 + elapsed, 10.0, 1000)
    assert got_steps == steps
    assert got_last == pytest.approx(new_last)


def test_auto_steps_drop_a_long_backlog() -> None:
    steps, last = auto_steps(100.0, 10.0, 1000)
    assert steps == MAX_CATCH_UP
    assert last == 100.0


def test_auto_steps_keep_the_day_rate_despite_slow_renders() -> None:
    """Timer runs every interval + a 240 ms render: the schedule still makes one step per
    interval on average."""
    now, last, days = 0.0, 0.0, 0
    for _ in range(100):
        now += 0.65 + 0.24
        n, last = auto_steps(now, last, 650)
        days += n
    assert days == int(now / 0.65)


def test_auto_stale() -> None:
    assert not auto_stale(12.0, 10.0, 650)  # 2 s < max(5 × 0.65 s, 3 s)
    assert auto_stale(13.3, 10.0, 650)
    assert not auto_stale(10.0 + STALE_MIN_S - 0.01, 10.0, 120)  # the 3 s floor
    assert auto_stale(10.0 + STALE_MIN_S + 0.01, 10.0, 120)
    assert not auto_stale(20.0, 10.0, 3000)  # 5 intervals of 3 s = 15 s
    assert auto_stale(26.0, 10.0, 3000)
