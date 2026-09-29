"""Leg editing for the strategy builder: build presets and new legs exactly as the React
``StrategyBuilder.tsx`` does, and apply the legs-table edits with ``LegsEditor.tsx``'s unit
conversions (trader units in the table, engine units in the :class:`Leg`).

Pure: no Streamlit. The page keeps the position as a tuple of frozen legs and replaces it
with the functions here, so every edit is a plain value transformation::

    legs = make_preset(
        "butterfly", spot=6312.45, tenor_days=30, wing_pct=5, strike_step=25, vol_for=get_vol
    )
    legs = update_leg(legs, "butterfly-1", lambda leg: edit_leg(leg, "K", 6325))

Units, as in the React table:

========== ======================== ====================================================
column     shown                    stored on the leg
========== ======================== ====================================================
qty        contracts (integer ≥ 1)  ``quantity`` (sign comes from ``side``)
strike     index points, 2 dp       ``K`` (index points)
exp (d)    whole calendar days      ``T`` = days / 365 (years, ACT/365)
vol %      vol points, 2 dp         ``sigma`` = points / 100 (decimal)
========== ======================== ====================================================

The table shows ROUNDED values (``round2``, whole days) but an edit only replaces the one
field that was edited, so an untouched leg keeps its full-precision strike, expiry and
surface vol, and the position prices exactly as in the React app.

Each field has bounds and a step (:class:`FieldLimits`), and the bounds always contain the
value the field shows for its leg (:meth:`FieldLimits.around`): a field only ever limits
what the user types, never a value a preset put there. (A calendar's back leg expires 60
days after the longest tenor; the smile can put a far wing's vol above the usual cap.)
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from eqd_desk.app.ui.format import js_round
from eqd_desk.engine import OptionType
from eqd_desk.engine.presets import (
    CALENDAR_BACK_OFFSET,
    PRESETS,
    PresetName,
    PresetParams,
    VolProvider,
    build_preset,
    round_to,
)
from eqd_desk.engine.strategy import Leg, LegSide

DAYS_PER_YEAR: Final = 365
"""Day count of the tenor / expiry fields: calendar days, ACT/365 (React ``/ 365``)."""

DEFAULT_PRESET: Final[PresetName] = "butterfly"
"""The structure the builder opens on (React ``DEFAULT_PRESET``)."""
DEFAULT_TENOR_DAYS: Final = 30
"""Default preset tenor, calendar days."""
DEFAULT_WING_PCT: Final = 5
"""Default wing width, % of spot."""

TENOR_MAX_DAYS: Final = 3650
"""Longest preset tenor accepted (10 years)."""
CALENDAR_BACK_DAYS: Final = js_round(CALENDAR_BACK_OFFSET * DAYS_PER_YEAR)
"""How many days after the preset tenor a calendar's back leg expires (60)."""
LEG_DAYS_MAX: Final = TENOR_MAX_DAYS + CALENDAR_BACK_DAYS
"""Longest expiry a leg's field accepts: the back leg of the longest calendar."""

MIN_VOL: Final = 0.01
"""Lowest vol a leg can be edited to (decimal: 1 vol point), as ``LegsEditor.tsx``."""

CUSTOM: Final = "custom"
"""The structure label once the legs have been edited by hand."""

Structure = PresetName | Literal["custom"]
"""What the legs currently are: a named preset, or ``"custom"`` after a hand edit."""

PRESET_LABELS: Final[Mapping[PresetName, str]] = MappingProxyType(
    {p.name: p.label for p in PRESETS}
)
"""Display label of each preset ("Bull call spread", …), in picker order."""

CUSTOM_LABEL: Final = "Custom structure"
"""Display label of a hand-edited structure (React ``StrategyEducation.tsx``)."""

LegField = Literal["quantity", "K", "days", "vol"]
"""An editable numeric column of the legs table."""

LEG_FIELDS: Final[tuple[LegField, ...]] = ("quantity", "K", "days", "vol")
"""The editable numeric columns, in table order (qty, strike, exp (d), vol %)."""

FIELD_NAMES: Final[Mapping[LegField, str]] = MappingProxyType(
    {"quantity": "quantity", "K": "strike", "days": "expiry (days)", "vol": "vol (%)"}
)
"""Spoken name of each numeric column (the visible headings are abbreviated)."""

LegButton = Literal["side", "type", "remove"]
"""A button of a leg's row: the L / S toggle, the C / P toggle, the remove ×."""

_BUTTON_HELP: Final[Mapping[LegButton, str]] = MappingProxyType(
    {
        "side": "Leg {n}: toggle long / short",
        "type": "Leg {n}: toggle call / put",
        "remove": "Remove leg {n}",
    }
)


def structure_label(structure: Structure) -> str:
    """Display label of the current structure: the preset's label, or "Custom structure"."""
    if structure == CUSTOM:
        return CUSTOM_LABEL
    return PRESET_LABELS[structure]


def strike_step_for(spot: float) -> float:
    """Strike grid the presets and new legs are rounded to, in index points (React
    ``strikeStepFor``): 25 for an index level at or above 2,000 (SPX, SX5E), 5 at or above
    200 (an ETF like SPY), else 1."""
    if spot >= 2000:
        return 25.0
    if spot >= 200:
        return 5.0
    return 1.0


def round2(x: float) -> float:
    """``Math.round(x * 100) / 100``: the 2-decimal value the legs table displays."""
    return js_round(x * 100) / 100


# ------------------------------------------------------------------ building legs


def make_preset(
    name: PresetName,
    *,
    spot: float,
    tenor_days: int,
    wing_pct: float,
    strike_step: float,
    vol_for: VolProvider,
) -> tuple[Leg, ...]:
    """The legs of a preset centred on ``spot`` (React ``makePreset``): expiry
    ``tenor_days / 365`` years, wing ``wing_pct`` % of spot, strikes on the ``strike_step``
    grid and each leg's vol read from the surface at its own strike and expiry."""
    return tuple(
        build_preset(
            name,
            PresetParams(
                S=spot,
                base_t=tenor_days / DAYS_PER_YEAR,
                width_pct=wing_pct / 100,
                strike_step=strike_step,
                vol_for=vol_for,
            ),
        )
    )


def new_leg(
    leg_id: str,
    *,
    spot: float,
    tenor_days: int,
    strike_step: float,
    vol_for: VolProvider,
) -> Leg:
    """The leg "Add leg" appends (React ``addLeg``): long 1 call struck at spot rounded to
    the strike grid, expiring at the preset tenor, with the surface vol there."""
    K = round_to(spot, strike_step)
    T = tenor_days / DAYS_PER_YEAR
    return Leg(id=leg_id, type="call", side="long", quantity=1, K=K, T=T, sigma=vol_for(K, T))


# ------------------------------------------------------------------ what the table shows


def leg_field_label(n: int, field: LegField) -> str:
    """Label of the ``field`` input of the ``n``-th leg (1-based): ``"Leg 2 strike"``.

    The table hides it (the column headings name the fields), but screen readers announce
    it, so each field says which leg it belongs to.
    """
    return f"Leg {n} {FIELD_NAMES[field]}"


def leg_button_help(n: int, button: LegButton) -> str:
    """Tooltip of a button of the ``n``-th leg's row (1-based): ``"Remove leg 2"``."""
    return _BUTTON_HELP[button].format(n=n)


@dataclass(frozen=True, slots=True)
class LegDisplay:
    """A leg in the table's trader units (the values its fields show)."""

    quantity: int
    """Contracts."""
    strike: float
    """Strike, rounded to 2 decimals."""
    days: int
    """Calendar days to expiry, rounded (``Math.round(T * 365)``)."""
    vol_pct: float
    """Implied vol in points, rounded to 2 decimals."""


def leg_display(leg: Leg) -> LegDisplay:
    """What the legs table shows for ``leg`` (``LegsEditor.tsx`` field values)."""
    return LegDisplay(
        quantity=js_round(leg.quantity),
        strike=round2(leg.K),
        days=js_round(leg.T * DAYS_PER_YEAR),
        vol_pct=round2(leg.sigma * 100),
    )


def field_values(leg: Leg) -> dict[LegField, float]:
    """The value each numeric field of ``leg``'s row shows (:func:`leg_display`), keyed by
    :data:`LegField` in table order: what the page seeds the row's inputs with."""
    shown = leg_display(leg)
    return {
        "quantity": shown.quantity,
        "K": shown.strike,
        "days": shown.days,
        "vol": shown.vol_pct,
    }


# ------------------------------------------------------------------ field bounds


@dataclass(frozen=True, slots=True)
class FieldLimits[N: (int, float)]:
    """Bounds and step of one numeric column of the legs table, in its trader units
    (``int`` for contracts and days, ``float`` for strike and vol points)."""

    lo: N
    """Lowest value the field accepts."""
    hi: N | None
    """Highest value the field accepts (``None``: no upper bound)."""
    step: N
    """Increment of the field's arrow keys (and step buttons, when it is wide enough)."""

    def around(self, shown: N) -> FieldLimits[N]:
        """These limits widened just enough to contain ``shown``, the value the field
        displays for its leg.

        A number field clamps whatever it is given, so a bound below a preset's value would
        make the table disagree with the leg that is priced: the field would show 3650 days
        for a calendar back leg priced at 3710. Widening instead means a field only ever
        limits what the user types.
        """
        lo = min(self.lo, shown)
        hi = None if self.hi is None else max(self.hi, shown)
        return FieldLimits(lo=lo, hi=hi, step=self.step)


QUANTITY_LIMITS: Final = FieldLimits(lo=1, hi=1000, step=1)
"""Contracts per leg."""
STRIKE_LIMITS: Final = FieldLimits(lo=0.01, hi=None, step=5.0)
"""Strike, index points (a strike must stay positive: ln(S/K))."""
DAYS_LIMITS: Final = FieldLimits(lo=1, hi=LEG_DAYS_MAX, step=1)
"""Expiry, whole calendar days (ACT/365)."""
VOL_LIMITS: Final = FieldLimits(lo=MIN_VOL * 100, hi=300.0, step=0.5)
"""Implied vol, vol points."""


# ------------------------------------------------------------------ edits


def _num(raw: float | None, fallback: float) -> float:
    """The typed number, or ``fallback`` when the field holds nothing usable (React
    ``num``)."""
    if raw is None or not math.isfinite(raw):
        return fallback
    return float(raw)


def edit_leg(leg: Leg, field: LegField, raw: float | None) -> Leg:
    """``leg`` with one table field replaced by the typed value ``raw`` (trader units),
    converted and clamped as ``LegsEditor.tsx`` does:

    - ``quantity``: rounded to a whole number of contracts, at least 1;
    - ``K``: the strike as typed. The React field accepts any number; here a strike that is
      not positive is ignored (the leg is kept) because ln(S/K) is undefined there;
    - ``days``: at least 1 day, stored as ``T = days / 365`` years;
    - ``vol``: vol points, stored as ``sigma = points / 100``, at least 1 point.
    """
    match field:
        case "quantity":
            return dataclasses.replace(leg, quantity=max(1, js_round(_num(raw, leg.quantity))))
        case "K":
            K = _num(raw, leg.K)
            return dataclasses.replace(leg, K=K) if K > 0 else leg
        case "days":
            days = max(1.0, _num(raw, leg.T * DAYS_PER_YEAR))
            return dataclasses.replace(leg, T=days / DAYS_PER_YEAR)
        case "vol":
            return dataclasses.replace(leg, sigma=max(MIN_VOL, _num(raw, leg.sigma * 100) / 100))


def flip_side(leg: Leg) -> Leg:
    """``leg`` bought instead of sold, or the reverse (the table's L / S toggle)."""
    side: LegSide = "short" if leg.side == "long" else "long"
    return dataclasses.replace(leg, side=side)


def flip_type(leg: Leg) -> Leg:
    """``leg`` as a put instead of a call, or the reverse (the table's C / P toggle)."""
    option_type: OptionType = "put" if leg.type == "call" else "call"
    return dataclasses.replace(leg, type=option_type)


def update_leg(legs: Sequence[Leg], leg_id: str, change: Callable[[Leg], Leg]) -> tuple[Leg, ...]:
    """The position with the leg ``leg_id`` replaced by ``change(leg)`` (others untouched;
    an unknown id changes nothing)."""
    return tuple(change(leg) if leg.id == leg_id else leg for leg in legs)


def remove_leg(legs: Sequence[Leg], leg_id: str) -> tuple[Leg, ...]:
    """The position without the leg ``leg_id``."""
    return tuple(leg for leg in legs if leg.id != leg_id)


def custom_leg_id(n: int) -> str:
    """Id of the ``n``-th hand-added leg (React ``custom-${n}``)."""
    return f"custom-{n}"


__all__ = [
    "CALENDAR_BACK_DAYS",
    "CUSTOM",
    "CUSTOM_LABEL",
    "DAYS_LIMITS",
    "DAYS_PER_YEAR",
    "DEFAULT_PRESET",
    "DEFAULT_TENOR_DAYS",
    "DEFAULT_WING_PCT",
    "FIELD_NAMES",
    "LEG_DAYS_MAX",
    "LEG_FIELDS",
    "MIN_VOL",
    "PRESET_LABELS",
    "QUANTITY_LIMITS",
    "STRIKE_LIMITS",
    "TENOR_MAX_DAYS",
    "VOL_LIMITS",
    "FieldLimits",
    "LegButton",
    "LegDisplay",
    "LegField",
    "Structure",
    "custom_leg_id",
    "edit_leg",
    "field_values",
    "flip_side",
    "flip_type",
    "leg_button_help",
    "leg_display",
    "leg_field_label",
    "make_preset",
    "new_leg",
    "remove_leg",
    "round2",
    "strike_step_for",
    "structure_label",
    "update_leg",
]
