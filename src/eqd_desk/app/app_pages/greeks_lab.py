"""Greeks lab (Phase 1): one vanilla option, its price and every greek live, the selected
greek swept against spot / vol / time, the payoff at expiry, and the Learn panel.

Port of ``web/src/components/GreeksLab.tsx`` (with ``InputPanel``, ``GreeksReadout``,
``PlotsPanel`` and ``EducationPanel``). Layout, like the React terminal: inputs + readout |
plots | learn (the columns stack on a phone).

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
from eqd_desk.app.ui.greeks_lab_charts import greek_chart, greek_chart_title, payoff_chart
from eqd_desk.app.ui.greeks_lab_widgets import paired_input
from eqd_desk.app.ui.widgets import (
    choice,
    greek_picker,
    greek_readout,
    hero_number,
    option_type_toggle,
    readout_table,
    section_header,
    set_number,
    sub_heading,
)
from eqd_desk.content import GREEK_DOCS, markdown_safe
from eqd_desk.content.greeks import PAYOFF_CAPTION, SURFACE_VOL_HINT, XAxisKey, greek_sweep_caption
from eqd_desk.data import seed_inputs
from eqd_desk.engine import GREEK_UNITS, BsmInputs, OptionType, analyze_option


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
    for key, value in lab.seed_values(seed_inputs(state.snapshot())).items():
        set_number(key, value)
    st.session_state[lab.TYPE_KEY] = lab.DEFAULT_TYPE


def vol_from_surface() -> None:
    """Snap σ to the seed vol surface at the current strike and tenor (feel the skew)."""
    K = float(st.session_state[lab.input_key("K")])
    T = float(st.session_state[lab.input_key("T")])
    set_number(lab.input_key("sigma"), state.surface().get_vol(K, T))


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
# down / in the header slot; a click has already stored the new choice by now.
greek = lab.valid_greek(st.session_state.get(lab.GREEK_KEY))
x_axis = lab.valid_x_axis(st.session_state.get(lab.X_AXIS_KEY))

left, center, right = st.columns([1, 1.9, 1])

# ------------------------------------------------------------------ inputs + readout

with left:
    with st.container(border=True, key="lab_inputs"):
        with section_header("Inputs", icon=":material/tune:"):
            option_type = option_type_toggle(key=lab.TYPE_KEY)
        values = {
            spec.key: paired_input(spec, default=float(getattr(seed, spec.field))) for spec in specs
        }
        with st.container(horizontal=True, gap="small"):
            st.button(
                "Reset to snapshot",
                icon=":material/restart_alt:",
                on_click=reset_to_snapshot,
                help="Restore the seed snapshot inputs",
                width="stretch",
                key="lab.reset",
            )
            st.button(
                "σ ← surface",
                icon=":material/ssid_chart:",
                on_click=vol_from_surface,
                help=markdown_safe(SURFACE_VOL_HINT),
                width="stretch",
                key="lab.surface_vol",
            )

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
            help=markdown_safe(GREEK_DOCS["price"].measures),
        )
        greek_readout(analysis.reported, selected=greek)
        with st.expander("Raw partials", icon=":material/function:"):
            readout_table(curves.raw_partial_rows(analysis, selected=greek))

# ------------------------------------------------------------------ plots

with center, st.container(border=True, key="lab_plots"):
    label, x_label = greek_chart_title(greek, x_axis)
    with section_header(label, subtitle="vs", highlight=x_label):
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
    charts.show_chart(
        payoff_chart(
            cached_payoff(inputs, option_type, snap.spot), inputs=inputs, currency=currency
        ),
        key="lab.payoff_chart",
    )
    teaching_caption(PAYOFF_CAPTION)

# ------------------------------------------------------------------ learn

with right, st.container(border=True, key="lab_learn"):
    learn_header(badge=GREEK_UNITS[greek].unit)
    greek_picker(key=lab.GREEK_KEY)
    greek_doc_card(greek)
    key_relationships()
