"""The greeks lab's paired slider + numeric field (React ``InputPanel`` ``Field``).

Same state contract as :func:`eqd_desk.app.ui.widgets.number_slider` (the value lives at the
canonical, non-widget key; the widgets use :func:`~eqd_desk.app.ui.widgets.slider_keys`; so
:func:`~eqd_desk.app.ui.widgets.set_number` drives it), with one layout difference: the
numeric field has a FIXED width, like React's 92 px column.

Why: Streamlit adds +/- step buttons to a number input wider than 7.5rem (105 px with this
theme's 14 px base). ``number_slider`` sizes the field as a share of its column, which lands
at 112–120 px on every desktop width, so the buttons appear and squeeze the value to four
or five characters ("6312.4", "0.082"). A 96 px field never grows buttons and shows
"6312.45" whole, at any page width.
"""

from __future__ import annotations

from typing import Final

import streamlit as st

from eqd_desk.app.ui.greeks_lab_inputs import InputSpec
from eqd_desk.app.ui.widgets import clamp, slider_keys
from eqd_desk.content import markdown_safe

FIELD_WIDTH: Final = 96
"""Numeric-field width in px: under the 105 px at which Streamlit adds step buttons, and
wide enough for "6312.45" in the mono font."""


def _from_slider(key: str) -> None:
    slider_key, input_key = slider_keys(key)
    value = float(st.session_state[slider_key])
    st.session_state[key] = value
    st.session_state[input_key] = value


def _from_field(key: str, lo: float, hi: float) -> None:
    slider_key, input_key = slider_keys(key)
    raw = st.session_state[input_key]
    value = clamp(float(raw), lo, hi) if raw is not None else float(st.session_state[key])
    st.session_state[key] = value
    st.session_state[slider_key] = value
    st.session_state[input_key] = value


def paired_input(spec: InputSpec, *, default: float) -> float:
    """One input of the panel: a header (label, dim italic symbol, and the value with its
    unit on the right), then a slider and a fixed-width numeric field editing the same value.

    Args:
        spec: bounds, step, formats and display of the input.
        default: first-run value (clamped to the bounds).

    Returns:
        The current value.
    """
    key = spec.key
    lo, hi = spec.min_value, spec.max_value
    if key not in st.session_state:
        st.session_state[key] = clamp(default, lo, hi)
    value = clamp(float(st.session_state[key]), lo, hi)
    st.session_state[key] = value
    slider_key, input_key = slider_keys(key)
    for wkey in (slider_key, input_key):
        if st.session_state.get(wkey) != value:
            st.session_state[wkey] = value

    with st.container(gap="xsmall"):
        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="bottom",
            gap="small",
        ):
            st.markdown(
                f"{markdown_safe(spec.label)} :gray[*{markdown_safe(spec.symbol)}*]",
                width="content",
            )
            st.markdown(f"`{spec.display(value)}`", width="content")
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.slider(
                spec.label,
                min_value=lo,
                max_value=hi,
                step=spec.step,
                format=spec.input_format,
                key=slider_key,
                on_change=_from_slider,
                args=(key,),
                label_visibility="collapsed",
                width="stretch",
            )
            st.number_input(
                f"{spec.label} value",
                min_value=lo,
                max_value=hi,
                step=spec.step,
                format=spec.input_format,
                key=input_key,
                on_change=_from_field,
                args=(key, lo, hi),
                label_visibility="collapsed",
                width=FIELD_WIDTH,
            )
    return value
