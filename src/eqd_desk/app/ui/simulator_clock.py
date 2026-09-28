"""The simulator's Auto clock in Streamlit terms (pure; no Streamlit import).

React drives Auto with ``setInterval(advance, autoDelay)``. The Streamlit page instead wraps
the live desk in ``@st.fragment(run_every=…)``, which reruns the fragment on a timer. Two
things differ from an interval and are handled here:

- The timer is fixed when the fragment is registered (a full-app run), so turning Auto on or
  off, or changing the speed, needs one full-app rerun to (un)register it:
  :func:`auto_interval` is what the fragment should be registered with, and the page reruns
  the app when it differs from what is registered.
- A fragment also reruns when the user clicks inside it, and the timer only fires again once
  a rerun has finished (so a slow render stretches the period). A run therefore advances the
  market by the number of steps that are DUE (:func:`auto_steps`): none if less than half an
  interval has passed since the last step (a click), otherwise one per elapsed interval,
  keeping the schedule's phase. Auto thus runs at the chosen ms per day however long a render
  takes or however much the user clicks meanwhile.

React also pauses Auto when the user leaves the page. Streamlit has no "left the page" event;
a page run that finds Auto on but no step for several intervals (:func:`auto_stale`) means the
user was away, and pauses it.
"""

from __future__ import annotations

from typing import Final

AUTO_MIN_MS: Final = 120
AUTO_MAX_MS: Final = 3000
AUTO_STEP_MS: Final = 60
AUTO_DEFAULT_MS: Final = 650
"""Auto speed slider: milliseconds per simulated day (React ``autoDelay``)."""

AUTO_DUE_FRACTION: Final = 0.5
"""A step is due once this fraction of the interval has passed since the last one (the timer
can fire a little early; a click right after a step must not step again)."""

MAX_CATCH_UP: Final = 4
"""Most steps one run may take to catch up with the schedule; further behind (a long render,
a sleeping laptop), the backlog is dropped rather than replayed in a burst."""

STALE_INTERVALS: Final = 5.0
STALE_MIN_S: Final = 3.0
"""Auto is stale (the user left the page) after ``max(5 intervals, 3 s)`` without a step."""


def auto_interval(playing: bool, speed_ms: float) -> float | None:
    """The fragment's ``run_every`` in seconds: the speed while Auto is on, else ``None``."""
    return speed_ms / 1000 if playing else None


def auto_steps(now: float, last_step: float, speed_ms: float) -> tuple[int, float]:
    """How many Auto steps are due at ``now`` and the new "last step" time.

    With ``interval = speed_ms / 1000`` and ``k`` whole intervals elapsed since
    ``last_step``: no step before half an interval; otherwise ``max(k, 1)`` steps (at most
    :data:`MAX_CATCH_UP`), the schedule advancing by that many intervals so the remainder
    carries over. Beyond the cap the backlog is dropped and the schedule restarts at ``now``.
    """
    interval = speed_ms / 1000
    elapsed = now - last_step
    if interval <= 0 or elapsed < AUTO_DUE_FRACTION * interval:
        return 0, last_step
    whole = int(elapsed // interval)
    if whole > MAX_CATCH_UP:
        return MAX_CATCH_UP, now
    steps = max(whole, 1)
    return steps, last_step + steps * interval


def auto_stale(now: float, last_step: float, speed_ms: float) -> bool:
    """Whether Auto has been silent long enough that the user must have left the page."""
    return now - last_step > max(STALE_INTERVALS * speed_ms / 1000, STALE_MIN_S)


__all__ = [
    "AUTO_DEFAULT_MS",
    "AUTO_DUE_FRACTION",
    "AUTO_MAX_MS",
    "AUTO_MIN_MS",
    "AUTO_STEP_MS",
    "MAX_CATCH_UP",
    "STALE_INTERVALS",
    "STALE_MIN_S",
    "auto_interval",
    "auto_stale",
    "auto_steps",
]
