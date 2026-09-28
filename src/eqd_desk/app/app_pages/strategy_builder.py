"""Strategy builder (Phase 2): compose vanilla legs into a structure, from a preset or by
hand, and read its net premium, aggregate greeks, P&L profile and greek profiles, beside the
desk rationale for the structure.

Port of ``web/src/components/StrategyBuilder.tsx`` (+ ``StrategyControls``, ``LegsEditor``,
``PositionReadout``, ``StrategyPlots``, ``StrategyEducation``). Three columns, as the React
terminal: structure controls + net position | legs + charts | Learn.

State and callbacks live in :mod:`eqd_desk.app.ui.strategy_builder_state`; leg edits in
:mod:`eqd_desk.app.ui.strategy_builder_legs`; curves in :mod:`eqd_desk.app.ui.strategy_curves`.
"""

from __future__ import annotations

from typing import cast

import streamlit as st

from eqd_desk.app.ui import charts, state
from eqd_desk.app.ui import strategy_builder_state as sb
from eqd_desk.app.ui.education import (
    greek_doc_card,
    key_relationships,
    learn_header,
    strategy_doc_card,
    teaching_caption,
)
from eqd_desk.app.ui.format import (
    MINUS,
    fmt_level,
    fmt_money,
    fmt_pct,
    fmt_with_unit,
    js_round,
)
from eqd_desk.app.ui.strategy_builder_charts import (
    greek_profile_chart,
    greek_profile_title,
    pnl_chart,
)
from eqd_desk.app.ui.strategy_builder_legs import CUSTOM, structure_label
from eqd_desk.app.ui.strategy_curves import (
    X_AXIS_OPTIONS,
    build_axis_meta,
    spot_range,
    sweep_heading,
    unique_strikes,
)
from eqd_desk.app.ui.widgets import (
    choice,
    greek_picker,
    greek_readout,
    hero_number,
    md_color,
    number_slider,
    section_header,
    sub_heading,
)
from eqd_desk.content import GREEK_DOCS, GreekKey, markdown_safe
from eqd_desk.content.strategies import (
    EMPTY_LEGS_HINT,
    NET_PREMIUM_NOTE,
    PAYOFF_CAPTION,
    PREMIUM_SIDE_NOTES,
    premium_side,
)
from eqd_desk.engine.presets import PRESETS
from eqd_desk.engine.strategy import analyze_position

sb.init_state()

snap = state.snapshot()
seed_spot = snap.spot
currency = snap.currency
current = sb.structure()
selected = cast("GreekKey", st.session_state[sb.GREEK_KEY])
x_axis = sb.x_axis()

# Pixel widths of the legs table: side, type, qty, strike, exp (d), vol %, remove (React:
# `34px 34px 1fr 1.3fr 1fr 1fr 26px`). Fixed widths make the heading row and every leg row
# wrap at the same places on a narrow screen, so each field stays under its heading.
# (Comments, not a docstring: Streamlit "magic" renders bare string literals of a page.)
LEG_WIDTHS = (40, 40, 80, 136, 80, 110, 32)
W_SIDE, W_TYPE, W_QTY, W_STRIKE, W_DAYS, W_VOL, W_REMOVE = LEG_WIDTHS
LEG_HEADINGS = ("Side", "Type", "Qty", "Strike", "Exp (d)", "Vol %")

left, center, right = st.columns([1, 2.1, 1])

# ------------------------------------------------------------------ left: structure

with left:
    with st.container(border=True):
        section_header(
            "Structure",
            icon=":material/category:",
            badge="custom" if current == CUSTOM else "preset",
            badge_color="gray",
        )
        grid = [col.container(gap="xsmall") for col in st.columns(2, gap="xsmall", wrap=False)]
        for i, preset in enumerate(PRESETS):
            active = preset.name == current
            grid[i % 2].button(
                f":primary[**{preset.label}**]" if active else preset.label,
                key=sb.preset_button_key(preset.name),
                on_click=sb.apply_preset,
                args=(preset.name,),
                width="stretch",
                help="Rebuild the legs as this structure around the current spot.",
            )
        with st.container(horizontal=True, gap="small"):
            st.number_input(
                "Tenor (days)",
                key=sb.TENOR_KEY,
                min_value=1,
                max_value=sb.TENOR_MAX_DAYS,
                step=1,
                format="%d",
                help="Expiry of the preset legs, in calendar days (ACT/365). "
                "Takes effect when you pick a preset or add a leg.",
                persist_state="session",
            )
            st.number_input(
                "Wing (% of spot)",
                key=sb.WING_KEY,
                min_value=1,
                max_value=sb.WING_MAX_PCT,
                step=1,
                format="%d",
                help="Distance of the wings from the at-the-money strike, as % of spot, "
                "rounded to the strike grid. Takes effect when you pick a preset.",
                persist_state="session",
            )
        number_slider(
            "Spot",
            key=sb.S_KEY,
            symbol="S",
            min_value=js_round(seed_spot * 0.6),
            max_value=js_round(seed_spot * 1.4),
            step=1.0 if seed_spot >= 2000 else 0.5,
            default=seed_spot,
            display=lambda v: fmt_with_unit(fmt_level(v), currency),
            slider_format="%.2f",
            compact=True,
        )
        number_slider(
            "Rate",
            key=sb.R_KEY,
            symbol="r",
            min_value=-0.02,
            max_value=0.1,
            step=0.0005,
            default=snap.r,
            display=fmt_pct,
            slider_format="percent",
            compact=True,
        )
        number_slider(
            "Dividend yield",
            key=sb.Q_KEY,
            symbol="q",
            min_value=0.0,
            max_value=0.06,
            step=0.0005,
            default=snap.q,
            display=fmt_pct,
            slider_format="percent",
            compact=True,
        )
        st.button(
            "Reset",
            key=sb.RESET_KEY,
            icon=":material/restart_alt:",
            on_click=sb.reset,
            width="stretch",
            help="Restore the seed market, a 30-day tenor and 5 % wings, and rebuild the "
            "butterfly.",
        )

    market = sb.market()
    position = sb.legs()
    analysis = analyze_position(position, market)
    side = premium_side(analysis.price)
    debit = side == "debit"

    with st.container(border=True):
        section_header(
            "Net position",
            icon=":material/account_balance:",
            badge=side.upper(),
            badge_color="primary" if debit else "gray",
        )
        hero_number(
            f"Net premium ({currency})",
            f"{MINUS if debit else '+'}{fmt_money(abs(analysis.price))}",
            detail=PREMIUM_SIDE_NOTES[side],
            tone=None if debit else "pos",
            help=NET_PREMIUM_NOTE,
        )
        greek_readout(analysis.reported, selected=selected)

# ------------------------------------------------------------------ centre: legs + charts

with center:
    with st.container(border=True):
        n_legs = len(position)
        section_header(
            "Legs",
            icon=":material/list_alt:",
            badge=f"{n_legs} leg{'' if n_legs == 1 else 's'}",
            badge_color="gray",
        )
        sb.sync_leg_widgets(position)
        with st.container(gap="xsmall"):
            with st.container(horizontal=True, gap="xsmall", vertical_alignment="bottom"):
                for title, width in zip(LEG_HEADINGS, LEG_WIDTHS, strict=False):
                    st.caption(title, width=width)
            if not position:
                st.caption(markdown_safe(EMPTY_LEGS_HINT))
            for leg in position:
                with st.container(horizontal=True, gap="xsmall", vertical_alignment="center"):
                    st.button(
                        md_color("**L**", "pos")
                        if leg.side == "long"
                        else md_color("**S**", "neg"),
                        key=sb.leg_widget_key(leg.id, "side"),
                        on_click=sb.toggle_side,
                        args=(leg.id,),
                        help="Toggle long / short",
                        width=W_SIDE,
                    )
                    st.button(
                        md_color("**C**", "call")
                        if leg.type == "call"
                        else md_color("**P**", "put"),
                        key=sb.leg_widget_key(leg.id, "type"),
                        on_click=sb.toggle_type,
                        args=(leg.id,),
                        help="Toggle call / put",
                        width=W_TYPE,
                    )
                    st.number_input(
                        "Quantity",
                        key=sb.leg_widget_key(leg.id, "quantity"),
                        min_value=1,
                        max_value=1000,
                        step=1,
                        format="%d",
                        on_change=sb.on_leg_field,
                        args=(leg.id, "quantity"),
                        label_visibility="collapsed",
                        width=W_QTY,
                    )
                    st.number_input(
                        "Strike",
                        key=sb.leg_widget_key(leg.id, "K"),
                        min_value=0.01,
                        step=5.0,
                        format="%g",
                        on_change=sb.on_leg_field,
                        args=(leg.id, "K"),
                        label_visibility="collapsed",
                        width=W_STRIKE,
                    )
                    st.number_input(
                        "Expiry (days)",
                        key=sb.leg_widget_key(leg.id, "days"),
                        min_value=1,
                        max_value=sb.TENOR_MAX_DAYS,
                        step=1,
                        format="%d",
                        on_change=sb.on_leg_field,
                        args=(leg.id, "days"),
                        label_visibility="collapsed",
                        width=W_DAYS,
                    )
                    st.number_input(
                        "Vol (%)",
                        key=sb.leg_widget_key(leg.id, "vol"),
                        min_value=1.0,
                        max_value=300.0,
                        step=0.5,
                        format="%g",
                        on_change=sb.on_leg_field,
                        args=(leg.id, "vol"),
                        label_visibility="collapsed",
                        width=W_VOL,
                    )
                    st.button(
                        ":material/close:",
                        key=sb.leg_widget_key(leg.id, "remove"),
                        on_click=sb.delete_leg,
                        args=(leg.id,),
                        type="tertiary",
                        help="Remove leg",
                        width=W_REMOVE,
                    )
        st.button(
            "Add leg",
            key=sb.ADD_LEG_KEY,
            icon=":material/add:",
            on_click=sb.add_leg,
            help="Append a long at-the-money call at the preset tenor, vol from the surface.",
        )

    with st.container(border=True):
        section_header(
            "P&L at expiry", subtitle="vs", highlight="spot", icon=":material/show_chart:"
        )
        payoff, bes = sb.cached_payoff(position, market, seed_spot)
        charts.show_chart(
            pnl_chart(payoff, spot=market.S, strikes=unique_strikes(position), currency=currency),
            key="strat.payoff_chart",
        )
        lo, hi = spot_range(seed_spot)
        if bes:
            levels = " · ".join(f"`{fmt_money(b)}`" for b in bes)
            st.markdown(f":small[:gray[Break-even at expiry]] {levels}")
        elif position:
            st.markdown(
                f":small[:gray[No break-even between {markdown_safe(fmt_level(lo, 0))} and "
                f"{markdown_safe(fmt_level(hi, 0))}]]"
            )
        teaching_caption(PAYOFF_CAPTION)

        meta = build_axis_meta(x_axis, position, market, seed_spot)
        slot = section_header(
            greek_profile_title(selected),
            subtitle="vs",
            highlight=sweep_heading(meta),
            icon=":material/timeline:",
        )
        with slot:
            choice("X axis", X_AXIS_OPTIONS, key=sb.X_KEY, default="S")
        sweep = sb.cached_sweep(x_axis, position, market, seed_spot)
        charts.show_chart(greek_profile_chart(sweep, meta, selected), key="strat.greek_chart")
        teaching_caption(GREEK_DOCS[selected].measures)

# ------------------------------------------------------------------ right: learn

with right, st.container(border=True):
    label = structure_label(current)
    learn_header(badge=label)
    strategy_doc_card(None if current == CUSTOM else current, title=label)
    sub_heading("Greek detail")
    greek_picker(key=sb.GREEK_KEY)
    greek_doc_card(selected)
    key_relationships()
