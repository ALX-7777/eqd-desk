"""Session state of the strategy-builder page: its keys, their idempotent initialisation,
the widget callbacks that edit the position, and the cached curve computations.

The position is ONE canonical value, ``st.session_state[LEGS_KEY]``: a tuple of frozen
:class:`~eqd_desk.engine.strategy.Leg`. Every control edits it through a callback (which
runs before the script), and the legs table's widgets are re-synced from it before they
render, so the table, the readout, the charts and the Learn panel always describe the same
legs. Semantics follow ``web/src/components/StrategyBuilder.tsx``:

- picking a preset REBUILDS the legs around the current spot slider with the current tenor
  and wing (clicking the highlighted preset again rebuilds it too);
- the tenor and wing fields only take effect when a preset is picked or a leg is added;
- any hand edit (a field, a toggle, add, remove) turns the structure into ``"custom"``;
- Reset restores the seed market, tenor and wing and rebuilds the default butterfly
  (the selected greek and x axis are kept, as in React).

Keys are page-prefixed (``"strat."``) and non-widget, so the position survives page
switches.
"""

from __future__ import annotations

from typing import Final, cast

import pandas as pd
import streamlit as st

from eqd_desk.app.ui import state
from eqd_desk.app.ui.strategy_builder_legs import (
    CUSTOM,
    DEFAULT_PRESET,
    DEFAULT_TENOR_DAYS,
    DEFAULT_WING_PCT,
    LegField,
    Structure,
    custom_leg_id,
    edit_leg,
    flip_side,
    flip_type,
    leg_display,
    make_preset,
    new_leg,
    remove_leg,
    strike_step_for,
    update_leg,
)
from eqd_desk.app.ui.strategy_curves import (
    StrategyXAxis,
    break_evens,
    greek_sweep,
    payoff_frame,
)
from eqd_desk.app.ui.widgets import set_number
from eqd_desk.engine.presets import PresetName
from eqd_desk.engine.strategy import Leg, MarketParams

PREFIX: Final = "strat."
"""Prefix of every session key of the page."""

LEGS_KEY: Final = "strat.legs"
"""The position: ``tuple[Leg, ...]``."""
STRUCTURE_KEY: Final = "strat.structure"
"""The preset the legs were built from, or ``"custom"`` after a hand edit."""
NEXT_ID_KEY: Final = "strat.next_id"
"""Counter of hand-added legs (their ids are ``custom-<n>``; never reset, like React)."""
TENOR_KEY: Final = "strat.tenor"
"""Preset tenor field, whole calendar days."""
WING_KEY: Final = "strat.wing"
"""Preset wing field, whole % of spot."""
S_KEY: Final = "strat.S"
"""Spot slider (index points)."""
R_KEY: Final = "strat.r"
"""Rate slider (decimal, continuously compounded)."""
Q_KEY: Final = "strat.q"
"""Dividend-yield slider (decimal, continuously compounded)."""
GREEK_KEY: Final = "strat.greek"
"""The greek plotted, highlighted in the readout and explained in Learn."""
X_KEY: Final = "strat.x"
"""X axis of the greek chart: ``"S"``, ``"vol"`` or ``"time"``."""
ADD_LEG_KEY: Final = "strat.add_leg"
"""The "Add leg" button."""
RESET_KEY: Final = "strat.reset"
"""The Reset button."""

TENOR_MAX_DAYS: Final = 3650
"""Longest preset tenor accepted (10 years)."""
WING_MAX_PCT: Final = 45
"""Widest wing accepted, % of spot: keeps the iron condor's outer put strike positive."""


def preset_button_key(name: PresetName) -> str:
    """Key of the preset button ``name``."""
    return f"{PREFIX}preset.{name}"


def leg_widget_key(leg_id: str, field: str) -> str:
    """Key of one control of a leg's row (``field`` = side, type, quantity, K, days, vol,
    remove)."""
    return f"{PREFIX}leg.{leg_id}.{field}"


# ------------------------------------------------------------------ market & data


def strike_step() -> float:
    """Strike grid of the seed index (25 points on SPX)."""
    return strike_step_for(state.snapshot().spot)


def vol_for(K: float, T: float) -> float:
    """Seed vol surface at strike ``K`` and expiry ``T`` (years): every new leg's vol."""
    return state.surface().get_vol(K, T)


def market() -> MarketParams:
    """The shared market of the position (spot, rate, dividend-yield sliders)."""
    ss = st.session_state
    return MarketParams(S=float(ss[S_KEY]), r=float(ss[R_KEY]), q=float(ss[Q_KEY]))


def seed_market() -> MarketParams:
    """The seed snapshot's market (what Reset restores)."""
    snap = state.snapshot()
    return MarketParams(S=snap.spot, r=snap.r, q=snap.q)


def default_legs(m: MarketParams | None = None) -> tuple[Leg, ...]:
    """The default butterfly (30 days, 5 % wings) centred on ``m.S`` (default: seed spot)."""
    spot = (m or seed_market()).S
    return make_preset(
        DEFAULT_PRESET,
        spot=spot,
        tenor_days=DEFAULT_TENOR_DAYS,
        wing_pct=DEFAULT_WING_PCT,
        strike_step=strike_step(),
        vol_for=vol_for,
    )


# ------------------------------------------------------------------ state


def init_state() -> None:
    """Idempotently seed every key of the page (existing values are kept)."""
    m = seed_market()
    state.ensure_state(
        {
            STRUCTURE_KEY: DEFAULT_PRESET,
            NEXT_ID_KEY: 0,
            TENOR_KEY: DEFAULT_TENOR_DAYS,
            WING_KEY: DEFAULT_WING_PCT,
            S_KEY: m.S,
            R_KEY: m.r,
            Q_KEY: m.q,
            GREEK_KEY: "delta",
            X_KEY: "S",
        }
    )
    state.ensure_lazy(LEGS_KEY, default_legs)


def legs() -> tuple[Leg, ...]:
    """The current position."""
    return cast("tuple[Leg, ...]", st.session_state[LEGS_KEY])


def structure() -> Structure:
    """The preset the legs came from, or ``"custom"``."""
    return cast("Structure", st.session_state[STRUCTURE_KEY])


def x_axis() -> StrategyXAxis:
    """The greek chart's x axis."""
    return cast("StrategyXAxis", st.session_state[X_KEY])


def _set_legs(new: tuple[Leg, ...], new_structure: Structure) -> None:
    st.session_state[LEGS_KEY] = new
    st.session_state[STRUCTURE_KEY] = new_structure


def _edit(new: tuple[Leg, ...]) -> None:
    """A hand edit: store the legs and mark the structure custom."""
    _set_legs(new, CUSTOM)


def sync_leg_widgets(position: tuple[Leg, ...]) -> None:
    """Point each leg row's numeric fields at the leg's current (displayed) values.

    Call before the rows render: a preset rebuild, Reset or another row's edit changes the
    legs outside these widgets, and a field must never show a stale number.
    """
    for leg in position:
        shown = leg_display(leg)
        values: dict[str, float] = {
            "quantity": shown.quantity,
            "K": shown.strike,
            "days": shown.days,
            "vol": shown.vol_pct,
        }
        for field, value in values.items():
            key = leg_widget_key(leg.id, field)
            if st.session_state.get(key) != value:
                st.session_state[key] = value


# ------------------------------------------------------------------ callbacks


def apply_preset(name: PresetName) -> None:
    """Rebuild the legs as preset ``name`` around the spot slider, with the current tenor
    and wing (React ``applyPreset``)."""
    built = make_preset(
        name,
        spot=market().S,
        tenor_days=int(st.session_state[TENOR_KEY]),
        wing_pct=int(st.session_state[WING_KEY]),
        strike_step=strike_step(),
        vol_for=vol_for,
    )
    _set_legs(built, name)


def add_leg() -> None:
    """Append a long ATM call at the preset tenor (React ``addLeg``)."""
    n = int(st.session_state[NEXT_ID_KEY])
    st.session_state[NEXT_ID_KEY] = n + 1
    leg = new_leg(
        custom_leg_id(n),
        spot=market().S,
        tenor_days=int(st.session_state[TENOR_KEY]),
        strike_step=strike_step(),
        vol_for=vol_for,
    )
    _edit((*legs(), leg))


def delete_leg(leg_id: str) -> None:
    """Remove one leg (the row's × button)."""
    _edit(remove_leg(legs(), leg_id))


def toggle_side(leg_id: str) -> None:
    """Flip a leg between long and short (the row's L / S button)."""
    _edit(update_leg(legs(), leg_id, flip_side))


def toggle_type(leg_id: str) -> None:
    """Flip a leg between call and put (the row's C / P button)."""
    _edit(update_leg(legs(), leg_id, flip_type))


def on_leg_field(leg_id: str, field: LegField) -> None:
    """A leg's numeric field changed: convert and store it (``LegsEditor.tsx`` rules)."""
    raw = st.session_state.get(leg_widget_key(leg_id, field))
    value = None if raw is None else float(raw)
    _edit(update_leg(legs(), leg_id, lambda leg: edit_leg(leg, field, value)))


def reset() -> None:
    """Seed market, 30-day tenor, 5 % wing and the default butterfly (React ``onReset``)."""
    m = seed_market()
    set_number(S_KEY, m.S)
    set_number(R_KEY, m.r)
    set_number(Q_KEY, m.q)
    st.session_state[TENOR_KEY] = DEFAULT_TENOR_DAYS
    st.session_state[WING_KEY] = DEFAULT_WING_PCT
    _set_legs(default_legs(m), DEFAULT_PRESET)


# ------------------------------------------------------------------ cached curves


@st.cache_data(max_entries=64, show_spinner=False)
def cached_payoff(
    position: tuple[Leg, ...], m: MarketParams, spot: float
) -> tuple[pd.DataFrame, tuple[float, ...]]:
    """P&L-vs-spot frame and break-evens of a position (see
    :mod:`eqd_desk.app.ui.strategy_curves`)."""
    return payoff_frame(position, m, spot), break_evens(position, m, spot)


@st.cache_data(max_entries=64, show_spinner=False)
def cached_sweep(
    axis: StrategyXAxis, position: tuple[Leg, ...], m: MarketParams, spot: float
) -> pd.DataFrame:
    """Every aggregate greek along ``axis`` (so switching the plotted greek is free)."""
    return greek_sweep(axis, position, m, spot)
