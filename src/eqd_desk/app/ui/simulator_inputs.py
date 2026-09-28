"""The simulator's input widgets, built to survive the Auto run-boundary race.

Why the simulator needs its own inputs
--------------------------------------
While Auto runs, the desk fragment reruns back to back (``st.fragment(run_every=…)``). When
a run finishes, the Streamlit frontend drops every element the run did not refresh together
with its browser-side widget state, but it does so in a React state update that may execute
AFTER the next run has started (the browser is busy drawing the charts). Elements the next
run has not re-sent by then are dropped and remounted, and a remounted widget restarts from
its proto ``default``. For a keyed widget created without ``value=`` / ``default=`` that is
its ``min_value`` (or nothing for a segmented control), and the browser reports it back as a
genuine change. Observed in the browser: toggling Auto reset the trade ticket's strike, tenor
and size to 25 / 1 / 1.

The inputs here make a remount harmless:

- the value lives in a plain (non-widget) Session State key, the CANONICAL key, like
  ``widgets.number_slider``;
- the widget is always created with ``value=`` / ``default=`` equal to the canonical value,
  so a remount restores the current value (for keyed widgets these parameters are not part
  of the widget identity, so passing them every run never recreates the widget);
- the widget's own key is ``<canonical>__w<generation>`` and is NEVER written through the
  Session State API. A user edit flows widget → canonical in ``on_change``; a programmatic
  change (:func:`set_value`, e.g. "Load into ticket") writes the canonical value and bumps the
  generation, so the next run mounts a fresh widget whose default is the new value.

The key and value helpers are pure; the widget functions render with Streamlit.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Final, Literal, cast

import streamlit as st

from eqd_desk.content import markdown_safe

GEN_SUFFIX: Final = "__gen"
"""Session State suffix of a canonical key's widget generation counter."""

WIDGET_SUFFIX: Final = "__w"
"""Widget keys are ``<canonical key>__w<generation>``."""


# ------------------------------------------------------------------ pure helpers


def gen_key(key: str) -> str:
    """Session State key of the widget generation of canonical ``key``."""
    return f"{key}{GEN_SUFFIX}"


def widget_key(key: str, generation: int) -> str:
    """The widget key of canonical ``key`` at ``generation``: ``"sim.tk_K__w0"``."""
    return f"{key}{WIDGET_SUFFIX}{generation}"


def clamp_number(value: float, lo: float, hi: float | None, *, integer: bool) -> float:
    """``value`` limited to ``[lo, hi]`` (``hi=None``: no upper bound), rounded to a whole
    number for an integer input; NaN falls back to ``lo``."""
    if math.isnan(value):
        value = lo
    value = max(value, lo) if hi is None else min(max(value, lo), hi)
    return float(round(value)) if integer else float(value)


# ------------------------------------------------------------------ Session State plumbing


def current_widget_key(key: str) -> str:
    """The widget key canonical ``key`` renders with in this run."""
    return widget_key(key, int(st.session_state.get(gen_key(key), 0)))


def set_value(key: str, value: object) -> None:
    """Set canonical ``key`` programmatically (from a callback, or before the widget renders)
    and remount its widget with the new value as its default."""
    st.session_state[key] = value
    st.session_state[gen_key(key)] = int(st.session_state.get(gen_key(key), 0)) + 1


def _sync(key: str, wkey: str, after: Callable[[], None] | None) -> None:
    """``on_change`` of a steady widget: copy the edited value to the canonical key."""
    value = st.session_state.get(wkey)
    if value is not None:
        st.session_state[key] = value
    if after is not None:
        after()


# ------------------------------------------------------------------ widgets


def steady_number(
    label: str,
    *,
    key: str,
    min_value: int,
    step: int,
    max_value: int | None = None,
    help: str | None = None,
) -> int:
    """An integer number input whose value lives at canonical ``key`` (see the module
    docstring). Returns the current value."""
    value = int(clamp_number(float(st.session_state[key]), min_value, max_value, integer=True))
    st.session_state[key] = value
    wkey = current_widget_key(key)
    st.number_input(
        label,
        min_value=min_value,
        max_value=max_value,
        step=step,
        value=value,
        key=wkey,
        help=help,
        on_change=_sync,
        args=(key, wkey, None),
    )
    return int(st.session_state[key])


def steady_slider(
    label: str,
    *,
    key: str,
    min_value: float,
    max_value: float,
    step: float,
    display: Callable[[float], str],
    slider_format: str | None = None,
    integer: bool = False,
    help: str | None = None,
) -> float:
    """A compact labelled slider (the look of ``widgets.number_slider(compact=True)``: the
    label on the left, the mono ``display`` of the value on the right, the slider below)
    whose value lives at canonical ``key``. Returns the current value."""
    value = clamp_number(float(st.session_state[key]), min_value, max_value, integer=integer)
    typed: float = int(value) if integer else value
    st.session_state[key] = typed
    wkey = current_widget_key(key)
    with st.container(gap="xsmall"):
        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="bottom",
            gap="small",
        ):
            st.markdown(markdown_safe(label), help=help, width="content")
            st.markdown(f"`{display(typed)}`", width="content")
        lo: float = int(min_value) if integer else float(min_value)
        hi: float = int(max_value) if integer else float(max_value)
        stp: float = int(step) if integer else float(step)
        st.slider(
            label,
            min_value=lo,
            max_value=hi,
            step=stp,
            value=typed,
            format=slider_format,
            key=wkey,
            on_change=_sync,
            args=(key, wkey, None),
            label_visibility="collapsed",
        )
    return cast("float", st.session_state[key])


def steady_choice[T: str](
    label: str,
    options: Mapping[T, str],
    *,
    key: str,
    default: T,
    kind: Literal["segmented", "pills"] = "segmented",
    on_change: Callable[[], None] | None = None,
    help: str | None = None,
) -> T:
    """A single-choice segmented control (or pills) over ``options`` (value → label) that
    always has a selection, its value at canonical ``key``; ``on_change`` runs after the
    canonical value is updated by a user pick. Returns the selected value."""
    current = st.session_state.get(key)
    value: T = cast("T", current) if current in options else default
    st.session_state[key] = value
    wkey = current_widget_key(key)
    widget = st.segmented_control if kind == "segmented" else st.pills
    widget(
        label,
        list(options),
        format_func=lambda v: options[v],
        default=value,
        key=wkey,
        required=True,
        help=help,
        on_change=_sync,
        args=(key, wkey, on_change),
        label_visibility="collapsed",
    )
    return cast("T", st.session_state[key])


__all__ = [
    "GEN_SUFFIX",
    "WIDGET_SUFFIX",
    "clamp_number",
    "current_widget_key",
    "gen_key",
    "set_value",
    "steady_choice",
    "steady_number",
    "steady_slider",
    "widget_key",
]
