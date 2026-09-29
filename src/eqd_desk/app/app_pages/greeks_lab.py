"""Greeks lab (Phase 1): one vanilla option, its price and every greek live, the selected
greek swept against spot / vol / time, the payoff at expiry, and the Learn panel.

Port of ``web/src/components/GreeksLab.tsx`` (with ``InputPanel``, ``GreeksReadout``,
``PlotsPanel`` and ``EducationPanel``). Layout, like the React terminal: inputs + readout |
plots | learn (the columns stack on a phone).

The plotted greek is picked in the chart header (a compact select next to the x-axis
control, as the exotics' chart metric) or with the Learn chips; both write the one
selection (``lab.greek``) and each shows what the other picked. On a phone the chips sit
far below the chart, so the header select is the one at hand.

Acceptance check of the spec, readable off the charts: with Gamma vs spot, shrinking T
spikes the at-the-money gamma; with Time on the x axis, gamma falls and vega rises as T
grows.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from eqd_desk.app.ui import charts, state
from eqd_desk.app.ui import greeks_lab_curves as curves
from eqd_desk.app.ui import greeks_lab_inputs as lab
from eqd_desk.app.ui.education import (
    greek_doc_card,
    key_relationships,
    learn_header,
    teaching_caption,
)
from eqd_desk.app.ui.format import fmt_money
from eqd_desk.app.ui.greeks_lab_charts import PAYOFF_CHART_HEIGHT, greek_chart, greek_chart_title
from eqd_desk.app.ui.inputs import steady_key
from eqd_desk.app.ui.units import greek_unit
from eqd_desk.app.ui.widgets import (
    choice,
    greek_label,
    greek_picker,
    greek_readout,
    hero_number,
    number_slider,
    option_type_toggle,
    readout_table,
    reset_inputs,
    section_header,
    sub_heading,
    surface_vol_button,
)
from eqd_desk.content import GREEK_DOCS, GREEK_KEYS, GreekKey, markdown_safe
from eqd_desk.content.greeks import (
    PAYOFF_CAPTION,
    RESET_HINT,
    XAxisKey,
    greek_sweep_caption,
)
from eqd_desk.data import seed_inputs
from eqd_desk.engine import BsmInputs, OptionType, analyze_option


@st.cache_data(max_entries=256, show_spinner=False)
def cached_sweep(
    inputs: BsmInputs, option_type: OptionType, x_axis: XAxisKey, spot: float
) -> pd.DataFrame:
    """Every greek swept against ``x_axis`` (cached: picking another greek is free)."""
    return curves.greek_sweep(inputs, option_type, x_axis, spot)


@st.cache_data(max_entries=128, show_spinner=False)
def cached_payoff(inputs: BsmInputs, option_type: OptionType, spot: float) -> pd.DataFrame:
    """The payoff chart's grid (intrinsic at expiry and premium now)."""
    return curves.payoff_curve(inputs, option_type, spot)


def reset_to_snapshot() -> None:
    """Restore the seed option (spot, 30-day ATM-ish strike, snapshot vol/r/q) and a call."""
    seed = lab.seed_values(seed_inputs(state.snapshot()))
    reset_inputs({**seed, lab.TYPE_KEY: lab.DEFAULT_TYPE})


# Width in px of the chart header's greek select: the longest label ("Charm", "Gamma") plus
# the dropdown arrow, so it sits next to the x-axis control without crowding the title. (A
# comment, not a docstring: Streamlit's magic would print a bare string on the page.)
CHART_GREEK_WIDTH = 120


def chart_greek_select(current: GreekKey) -> None:
    """The chart header's greek selector: a compact select over the price and every greek,
    showing ``current`` (the shared ``lab.greek``, which the Learn chips also write).

    A pick is copied to ``lab.greek`` in the callback, so the chart, the readout highlight
    and the chips follow on the rerun. Remount-safe (:mod:`eqd_desk.app.ui.inputs`): the
    widget key is ``lab.chart_greek__w<generation>``, never written; when the chips pick
    another greek the live select disagrees with ``current`` and
    :func:`~eqd_desk.app.ui.inputs.steady_key` mounts a fresh one showing it.
    """
    wkey = steady_key(lab.CHART_GREEK_KEY, current)

    def adopt() -> None:
        picked = st.session_state.get(wkey)
        if picked in GREEK_KEYS:
            st.session_state[lab.GREEK_KEY] = picked

    st.selectbox(
        "Greek to plot",
        GREEK_KEYS,
        index=GREEK_KEYS.index(current),
        format_func=greek_label,
        key=wkey,
        on_change=adopt,
        label_visibility="collapsed",
        width=CHART_GREEK_WIDTH,
    )


# ------------------------------------------------------------------ state

snap = state.snapshot()
currency = snap.currency
seed = seed_inputs(snap)
specs = lab.input_specs(snap.spot, currency)

state.ensure_state(
    {
        lab.TYPE_KEY: lab.DEFAULT_TYPE,
        lab.GREEK_KEY: lab.DEFAULT_GREEK,
        lab.X_AXIS_KEY: lab.DEFAULT_X_AXIS,
        **lab.seed_values(seed),
    }
)
# The chart (centre) and the Learn badge are drawn before their pickers render further
# down / in the header slot; a click (chips or chart select) has already stored the new
# choice by now.
greek = lab.valid_greek(st.session_state.get(lab.GREEK_KEY))
x_axis = lab.valid_x_axis(st.session_state.get(lab.X_AXIS_KEY))

left, center, right = st.columns([1, 1.9, 1])

# ------------------------------------------------------------------ inputs + readout

with left:
    with st.container(border=True, key="lab_inputs"):
        with section_header("Inputs", icon=":material/tune:"):
            option_type = option_type_toggle(key=lab.TYPE_KEY)
        values = {
            spec.key: number_slider(
                spec.label,
                key=spec.key,
                symbol=spec.symbol,
                min_value=spec.min_value,
                max_value=spec.max_value,
                step=spec.step,
                default=float(getattr(seed, spec.field)),
                display=spec.display,
                input_format=spec.input_format,
                slider_format=spec.slider_format,
            )
            for spec in specs
        }
        with st.container(horizontal=True, gap="small"):
            st.button(
                "Reset to snapshot",
                icon=":material/restart_alt:",
                on_click=reset_to_snapshot,
                help=markdown_safe(RESET_HINT),
                width="stretch",
                key="lab.reset",
            )
            surface_vol_button(lab.PREFIX, key="lab.surface_vol")

    inputs = lab.inputs_from_values(values)
    analysis = analyze_option(inputs, option_type)
    split = curves.premium_split(analysis)

    with st.container(border=True, key="lab_readout"):
        section_header(
            "Price & greeks",
            badge=option_type.upper(),
            badge_color="primary" if option_type == "call" else "orange",
        )
        hero_number(
            f"Premium ({currency})",
            fmt_money(split.premium),
            detail=(
                f"intrinsic {fmt_money(split.intrinsic)} · time value {fmt_money(split.time_value)}"
            ),
            help=GREEK_DOCS["price"].measures,
        )
        greek_readout(analysis.reported, selected=greek, currency=currency)
        with st.expander("Raw partials", icon=":material/function:"):
            readout_table(curves.raw_partial_rows(analysis, selected=greek))

# ------------------------------------------------------------------ plots

with center, st.container(border=True, key="lab_plots"):
    label, x_label = greek_chart_title(greek, x_axis)
    with section_header(label, subtitle="vs", highlight=x_label):
        chart_greek_select(greek)
        choice("X axis", curves.X_AXIS_CHOICES, key=lab.X_AXIS_KEY, default=lab.DEFAULT_X_AXIS)
    # Room for the chart's hover toolbar, which would otherwise sit over the x-axis control.
    st.space("small")
    charts.show_chart(
        greek_chart(
            cached_sweep(inputs, option_type, x_axis, snap.spot),
            greek,
            x_axis,
            inputs=inputs,
            currency=currency,
        ),
        key="lab.greek_chart",
    )
    teaching_caption(greek_sweep_caption(greek, x_axis))

    sub_heading("Payoff at expiry")
    payoff = cached_payoff(inputs, option_type, snap.spot)
    charts.show_chart(
        charts.payoff_chart(
            payoff["spot"],
            payoff["expiry"],
            payoff["now"],
            spot=inputs.S,
            strikes=[inputs.K],
            y_title=f"Value ({currency})",
            height=PAYOFF_CHART_HEIGHT,
        ),
        key="lab.payoff_chart",
    )
    teaching_caption(PAYOFF_CAPTION)

# ------------------------------------------------------------------ learn

with right, st.container(border=True, key="lab_learn"):
    learn_header(badge=greek_unit(greek, currency))
    greek_picker(key=lab.GREEK_KEY)
    greek_doc_card(greek)
    key_relationships()
