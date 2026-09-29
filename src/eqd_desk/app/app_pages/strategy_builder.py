"""Strategy builder (Phase 2): compose vanilla legs into a structure, from a preset or by
hand, and read its net premium, aggregate greeks, P&L profile and greek profiles, beside the
desk rationale for the structure.

Port of ``web/src/components/StrategyBuilder.tsx`` (+ ``StrategyControls``, ``LegsEditor``,
``PositionReadout``, ``StrategyPlots``, ``StrategyEducation``). Three columns, as the React
terminal: structure controls + net position | legs + charts | Learn.

State and callbacks live in :mod:`eqd_desk.app.ui.strategy_builder_state`; leg edits and
the table's field bounds in :mod:`eqd_desk.app.ui.strategy_builder_legs`; the net-premium
readout in :mod:`eqd_desk.app.ui.strategy_builder_readout`; curves in
:mod:`eqd_desk.app.ui.strategy_curves`.
Every input is remount-safe (:mod:`eqd_desk.app.ui.inputs`): it keeps its value in a plain
Session State key and survives the frontend remounting it.
"""

from __future__ import annotations

from functools import partial
from typing import Final, Literal, cast

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from eqd_desk.app.ui import charts, state
from eqd_desk.app.ui import strategy_builder_state as sb
from eqd_desk.app.ui.bounds import DIV_BOUNDS, RATE_BOUNDS, SPOT_RANGE_FACTORS, level_step
from eqd_desk.app.ui.education import (
    greek_doc_card,
    key_relationships,
    learn_header,
    strategy_doc_card,
    teaching_caption,
)
from eqd_desk.app.ui.format import (
    THUMB_LEVEL,
    THUMB_PERCENT,
    fmt_level,
    fmt_money,
    fmt_pct,
    fmt_with_unit,
    js_round,
)
from eqd_desk.app.ui.inputs import steady_number
from eqd_desk.app.ui.strategy_builder_charts import (
    EMPTY_CHARTS_NOTE,
    greek_profile_chart,
    greek_profile_title,
    pnl_chart,
)
from eqd_desk.app.ui.strategy_builder_legs import (
    CUSTOM,
    DAYS_LIMITS,
    QUANTITY_LIMITS,
    STRIKE_LIMITS,
    VOL_LIMITS,
    FieldLimits,
    LegField,
    leg_button_help,
    leg_display,
    leg_field_label,
    structure_label,
)
from eqd_desk.app.ui.strategy_builder_readout import premium_view
from eqd_desk.app.ui.strategy_curves import (
    X_AXIS_CHOICES,
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
from eqd_desk.content.strategies import EMPTY_LEGS_HINT, NET_PREMIUM_NOTE, PAYOFF_CAPTION
from eqd_desk.engine.presets import PRESETS
from eqd_desk.engine.strategy import analyze_position

sb.init_state()

snap = state.snapshot()
seed_spot = snap.spot
currency = snap.currency
current = sb.structure()
selected = cast("GreekKey", st.session_state[sb.GREEK_KEY])
x_axis = sb.x_axis()

# The legs table (React `LegsEditor.tsx`). Pixel widths of its columns: side, type, qty,
# strike, exp (d), vol %, remove. A row (437 px with its gaps) fits the centre column of a
# window down to ~1,100 px. Number fields under 105 px draw no +/- steppers (Streamlit), like
# the React fields; the arrow keys still step them.
# (Comments, not a docstring: Streamlit "magic" renders bare string literals of a page.)
W_SIDE, W_TYPE, W_QTY, W_STRIKE, W_DAYS, W_VOL, W_REMOVE = 36, 36, 64, 96, 72, 80, 32
# Each row is two groups, the option (side, type, qty, strike) and its terms (expiry, vol,
# remove), so a row too wide for its column wraps between them, never inside one; the
# heading row has the same groups and widths, so it wraps at the same place. The fields of
# a leg sit a quarter-rem apart and legs a full rem apart, so a leg wrapped on two lines
# (a phone, a small laptop) still reads as one.
LEG_GAP: Final = "xxsmall"
LEGS_GAP: Final = "small"
OPTION_HEADINGS = (("Side", W_SIDE), ("Type", W_TYPE), ("Qty", W_QTY), ("Strike", W_STRIKE))
TERMS_HEADINGS = (("Exp (d)", W_DAYS), ("Vol %", W_VOL))


def leg_row(align: Literal["center", "bottom"] = "center") -> DeltaGenerator:
    # One line of the legs table (headings or a leg): wraps between its two groups.
    return st.container(horizontal=True, gap=LEG_GAP, vertical_alignment=align)


def leg_group(align: Literal["center", "bottom"] = "center") -> DeltaGenerator:
    # One group of a line, kept together when the line wraps.
    return st.container(horizontal=True, gap=LEG_GAP, vertical_alignment=align, width="content")


def leg_field[N: (int, float)](
    n: int,
    leg_id: str,
    field: LegField,
    limits: FieldLimits[N],
    shown: N,
    *,
    fmt: str,
    width: int,
) -> None:
    # A numeric field of the n-th leg's row: its value lives at sb.leg_key and an edit goes
    # to sb.on_leg_field. Its bounds always contain the value shown (FieldLimits.around), so
    # it never clamps a value the user did not type (a calendar's back leg, a steep wing's
    # vol).
    bounds = limits.around(shown)
    steady_number(
        leg_field_label(n, field),
        key=sb.leg_key(leg_id, field),
        min_value=bounds.lo,
        max_value=bounds.hi,
        step=bounds.step,
        format=fmt,
        on_change=partial(sb.on_leg_field, leg_id, field),
        label_visibility="collapsed",
        width=width,
    )


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
            steady_number(
                "Tenor (days)",
                key=sb.TENOR_KEY,
                min_value=1,
                max_value=sb.TENOR_MAX_DAYS,
                step=1,
                format="%d",
                help="Expiry of the preset legs, in calendar days (ACT/365). "
                "Takes effect when you pick a preset or add a leg.",
            )
            steady_number(
                "Wing (% of spot)",
                key=sb.WING_KEY,
                min_value=1,
                max_value=sb.WING_MAX_PCT,
                step=1,
                format="%d",
                help="Distance of the wings from the at-the-money strike, as % of spot, "
                "rounded to the strike grid. Takes effect when you pick a preset.",
            )
        lo_mult, hi_mult = SPOT_RANGE_FACTORS
        number_slider(
            "Spot",
            key=sb.S_KEY,
            symbol="S",
            min_value=js_round(seed_spot * lo_mult),
            max_value=js_round(seed_spot * hi_mult),
            step=level_step(seed_spot),
            default=seed_spot,
            display=lambda v: fmt_with_unit(fmt_level(v), currency),
            slider_format=THUMB_LEVEL,
            compact=True,
        )
        number_slider(
            "Rate",
            key=sb.R_KEY,
            symbol="r",
            min_value=RATE_BOUNDS.lo,
            max_value=RATE_BOUNDS.hi,
            step=RATE_BOUNDS.step,
            default=snap.r,
            display=fmt_pct,
            slider_format=THUMB_PERCENT,
            compact=True,
        )
        number_slider(
            "Dividend yield",
            key=sb.Q_KEY,
            symbol="q",
            min_value=DIV_BOUNDS.lo,
            max_value=DIV_BOUNDS.hi,
            step=DIV_BOUNDS.step,
            default=snap.q,
            display=fmt_pct,
            slider_format=THUMB_PERCENT,
            compact=True,
        )
        st.button(
            "Reset",
            key=sb.RESET_KEY,
            icon=":material/restart_alt:",
            on_click=sb.reset,
            width="stretch",
            help=markdown_safe(sb.reset_help()),
        )

    market = sb.market()
    position = sb.legs()
    analysis = analyze_position(position, market)
    premium = premium_view(analysis.price, n_legs=len(position))

    with st.container(border=True):
        section_header(
            "Net position",
            icon=":material/account_balance:",
            badge=premium.badge,
            badge_color=premium.badge_color,
        )
        hero_number(
            f"Net premium ({currency})",
            premium.value,
            detail=premium.detail,
            tone=premium.tone,
            help=NET_PREMIUM_NOTE,
        )
        greek_readout(analysis.reported, selected=selected, currency=currency)

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
        sb.seed_leg_fields(position)
        with st.container(gap=LEGS_GAP):
            with leg_row(align="bottom"):
                with leg_group(align="bottom"):
                    for title, width in OPTION_HEADINGS:
                        st.caption(title, width=width)
                with leg_group(align="bottom"):
                    for title, width in TERMS_HEADINGS:
                        st.caption(title, width=width)
                    st.space(W_REMOVE)  # the remove column has no heading
            if not position:
                st.caption(markdown_safe(EMPTY_LEGS_HINT))
            for n, leg in enumerate(position, start=1):
                shown = leg_display(leg)
                with leg_row():
                    with leg_group():
                        st.button(
                            md_color("**L**", "pos")
                            if leg.side == "long"
                            else md_color("**S**", "neg"),
                            key=sb.leg_key(leg.id, "side"),
                            on_click=sb.toggle_side,
                            args=(leg.id,),
                            help=leg_button_help(n, "side"),
                            width=W_SIDE,
                        )
                        st.button(
                            md_color("**C**", "call")
                            if leg.type == "call"
                            else md_color("**P**", "put"),
                            key=sb.leg_key(leg.id, "type"),
                            on_click=sb.toggle_type,
                            args=(leg.id,),
                            help=leg_button_help(n, "type"),
                            width=W_TYPE,
                        )
                        leg_field(
                            n,
                            leg.id,
                            "quantity",
                            QUANTITY_LIMITS,
                            shown.quantity,
                            fmt="%d",
                            width=W_QTY,
                        )
                        leg_field(
                            n,
                            leg.id,
                            "K",
                            STRIKE_LIMITS,
                            shown.strike,
                            fmt="%g",
                            width=W_STRIKE,
                        )
                    with leg_group():
                        leg_field(
                            n,
                            leg.id,
                            "days",
                            DAYS_LIMITS,
                            shown.days,
                            fmt="%d",
                            width=W_DAYS,
                        )
                        leg_field(
                            n,
                            leg.id,
                            "vol",
                            VOL_LIMITS,
                            shown.vol_pct,
                            fmt="%g",
                            width=W_VOL,
                        )
                        st.button(
                            ":material/close:",
                            key=sb.leg_key(leg.id, "remove"),
                            on_click=sb.delete_leg,
                            args=(leg.id,),
                            type="tertiary",
                            help=leg_button_help(n, "remove"),
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
        if not position:
            # Nothing to plot: flat zero lines and a caption about break-evens would read
            # as a broken chart.
            st.info(markdown_safe(EMPTY_CHARTS_NOTE), icon=":material/info:")
        else:
            payoff, bes = sb.cached_payoff(position, market, seed_spot)
            charts.show_chart(
                pnl_chart(
                    payoff, spot=market.S, strikes=unique_strikes(position), currency=currency
                ),
                key="strat.payoff_chart",
            )
            lo, hi = spot_range(seed_spot)
            if bes:
                levels = " · ".join(f"`{fmt_money(b)}`" for b in bes)
                st.markdown(f":small[:gray[Break-even at expiry]] {levels}")
            else:
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
                choice("X axis", X_AXIS_CHOICES, key=sb.X_AXIS_KEY, default=sb.DEFAULT_X_AXIS)
            sweep = sb.cached_sweep(x_axis, position, market, seed_spot)
            charts.show_chart(
                greek_profile_chart(sweep, meta, selected, currency=currency),
                key="strat.greek_chart",
            )
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
