"""Remount-safe input widgets: every input of the app keeps its value in a plain Session
State key and survives the frontend remounting it.

The problem
-----------
When a run finishes, the Streamlit frontend drops every element the run did not refresh,
together with its browser-side widget state. It does so in a React state update that may
execute AFTER the next run has started (the browser is busy drawing charts). Elements the
next run has not re-sent by then are dropped and REMOUNTED, and a remounted widget restarts
from its proto ``default``. For a keyed widget created without ``value=`` / ``default=``,
that default is its ``min_value`` (or no selection for a segmented control), and the browser
reports it back as a genuine user change. It bites whenever runs come back to back: the
simulator's ``st.fragment(run_every=…)`` loop (observed: toggling Auto reset the trade
ticket's strike, tenor and size to 25 / 1 / 1), or a quick series of slider moves.

The contract
------------
- The value lives in a plain (non-widget) Session State key, the CANONICAL key
  (``"lab.S"``, ``"sim.tk_K"``). Pages read it there, and it survives page switches.
- The widget's own key is ``<canonical>__w<generation>`` (:func:`widget_key`) and is NEVER
  written through the Session State API.
- The widget is always created with ``value=`` / ``default=`` equal to the canonical value,
  so a remount restores the current value. (For keyed widgets these parameters are not part
  of the widget identity, so passing them every run never recreates the widget.)
- A user edit flows widget → canonical in ``on_change``.
- A programmatic change writes the canonical key and bumps the generation
  (:func:`set_value`), so the next run mounts a fresh widget whose default is the new value.
  A plain write of the canonical key (a Reset callback's ``st.session_state[key] = v``)
  works too: before rendering, :func:`steady_key` notices that the live widget disagrees
  with the canonical value and bumps the generation itself.

The key and value helpers are pure (they take any mapping-like state, so a test can pass
``AppTest.session_state``); the widget functions render with Streamlit.

Pages use the widgets of :mod:`eqd_desk.app.ui.widgets`, which are built on this module
(:func:`~eqd_desk.app.ui.widgets.number_slider` for sliders,
:func:`~eqd_desk.app.ui.widgets.choice` / :func:`~eqd_desk.app.ui.widgets.toggle` over
:func:`steady_choice` / :func:`steady_toggle`), and :func:`steady_number` directly for a
plain number field. Every ``help`` here is plain text, escaped for Markdown on the way in.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Final, Literal, Protocol, cast

import streamlit as st

from eqd_desk.content import markdown_safe

GEN_SUFFIX: Final = "__gen"
"""Session State suffix of a canonical key's widget generation counter."""

WIDGET_SUFFIX: Final = "__w"
"""Widget keys are ``<canonical key>__w<generation>``."""

LabelVisibility = Literal["visible", "hidden", "collapsed"]
"""``label_visibility`` of a Streamlit widget."""


class ReadableState(Protocol):
    """What the pure helpers need from a Session State: item lookup that raises
    ``KeyError`` for a missing key (``st.session_state``, ``AppTest.session_state``, a
    ``dict``)."""

    def __getitem__(self, key: str, /) -> object: ...


# ------------------------------------------------------------------ pure helpers


def gen_key(key: str) -> str:
    """Session State key of the widget generation of canonical ``key``."""
    return f"{key}{GEN_SUFFIX}"


def widget_key(key: str, generation: int) -> str:
    """The widget key of canonical ``key`` at ``generation``: ``"sim.tk_K__w0"``."""
    return f"{key}{WIDGET_SUFFIX}{generation}"


def generation_in(state: ReadableState, key: str) -> int:
    """The current widget generation of canonical ``key`` in ``state`` (0 before any
    programmatic change)."""
    try:
        return int(cast("int", state[gen_key(key)]))
    except KeyError:
        return 0


def widget_key_in(state: ReadableState, key: str) -> str:
    """The widget key canonical ``key`` currently renders with, read from ``state``.

    Tests use it to find a widget: ``at.slider(key=widget_key_in(at.session_state, k))``.
    """
    return widget_key(key, generation_in(state, key))


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
    return widget_key_in(st.session_state, key)


def remount(key: str) -> None:
    """Bump the widget generation of ``key``: its next render mounts a fresh widget (whose
    default is the canonical value)."""
    st.session_state[gen_key(key)] = generation_in(st.session_state, key) + 1


def set_value(key: str, value: object) -> None:
    """Set canonical ``key`` programmatically (from a callback, or before the widget renders)
    and remount its widget with the new value as its default."""
    st.session_state[key] = value
    remount(key)


def steady_key(key: str, value: object) -> str:
    """The widget key to render canonical ``key``'s widget with in this run, given the
    canonical ``value``.

    If the live widget holds a different value (the canonical key was written elsewhere,
    e.g. by a Reset callback, or clamped), the generation is bumped first, so a fresh
    widget mounts showing ``value``. Call once per render, just before creating the widget.
    """
    wkey = current_widget_key(key)
    live = st.session_state.get(wkey)
    if live is not None and live != value:
        remount(key)
        wkey = current_widget_key(key)
    return wkey


def _sync(key: str, wkey: str, after: Callable[[], None] | None) -> None:
    """``on_change`` of a steady widget: copy the edited value to the canonical key."""
    value = st.session_state.get(wkey)
    if value is not None:
        st.session_state[key] = value
    if after is not None:
        after()


# ------------------------------------------------------------------ widgets


def steady_number[N: (int, float)](
    label: str,
    *,
    key: str,
    min_value: N,
    step: N,
    max_value: N | None = None,
    format: str | None = None,
    width: int | Literal["stretch"] = "stretch",
    label_visibility: LabelVisibility = "visible",
    on_change: Callable[[], None] | None = None,
    help: str | None = None,
) -> N:
    """A number input whose value lives at canonical ``key`` (see the module docstring):
    integer-valued when ``min_value`` and ``step`` are ints (the simulator's strike, tenor,
    size), else a float (a leg's strike or vol). Values outside the bounds are clamped;
    ``on_change`` runs after a user edit is stored. Returns the current value."""
    integer = isinstance(min_value, int) and isinstance(step, int)
    value = clamp_number(float(st.session_state[key]), min_value, max_value, integer=integer)
    typed: float = int(value) if integer else value
    st.session_state[key] = typed
    wkey = steady_key(key, typed)
    # st.number_input needs value, bounds and step of one type.
    kind = int if integer else float
    st.number_input(
        label,
        min_value=kind(min_value),
        max_value=None if max_value is None else kind(max_value),
        step=kind(step),
        value=typed,
        format=format,
        key=wkey,
        help=markdown_safe(help) if help else None,
        on_change=_sync,
        args=(key, wkey, on_change),
        label_visibility=label_visibility,
        width=width,
    )
    return cast("N", st.session_state[key])


def steady_choice[T: str](
    label: str,
    options: Mapping[T, str],
    *,
    key: str,
    default: T,
    kind: Literal["segmented", "pills"] = "segmented",
    on_change: Callable[[], None] | None = None,
    help: str | None = None,
    label_visibility: LabelVisibility = "collapsed",
) -> T:
    """A single-choice segmented control (or pills) over ``options`` (value → label) that
    always has a selection, its value at canonical ``key``; ``on_change`` runs after the
    canonical value is updated by a user pick. Returns the selected value."""
    current = st.session_state.get(key)
    value: T = cast("T", current) if current in options else default
    st.session_state[key] = value
    wkey = steady_key(key, value)
    widget = st.segmented_control if kind == "segmented" else st.pills
    widget(
        label,
        list(options),
        format_func=lambda v: options[v],
        default=value,
        key=wkey,
        required=True,
        help=markdown_safe(help) if help else None,
        on_change=_sync,
        args=(key, wkey, on_change),
        label_visibility=label_visibility,
    )
    return cast("T", st.session_state[key])


def steady_toggle(
    label: str,
    *,
    key: str,
    default: bool = False,
    on_change: Callable[[], None] | None = None,
    help: str | None = None,
    disabled: bool = False,
) -> bool:
    """An on/off switch (``st.toggle``) whose value lives at canonical ``key`` (seeded with
    ``default`` on first use); ``on_change`` runs after a user flip is stored. Returns the
    current value."""
    value = bool(st.session_state.get(key, default))
    st.session_state[key] = value
    wkey = steady_key(key, value)
    st.toggle(
        label,
        value=value,
        key=wkey,
        help=markdown_safe(help) if help else None,
        on_change=_sync,
        args=(key, wkey, on_change),
        disabled=disabled,
    )
    return bool(st.session_state[key])


__all__ = [
    "GEN_SUFFIX",
    "WIDGET_SUFFIX",
    "LabelVisibility",
    "ReadableState",
    "clamp_number",
    "current_widget_key",
    "gen_key",
    "generation_in",
    "remount",
    "set_value",
    "steady_choice",
    "steady_key",
    "steady_number",
    "steady_toggle",
    "widget_key",
    "widget_key_in",
]
