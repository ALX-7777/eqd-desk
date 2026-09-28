"""Standard index-desk structures, built relative to spot.

Pure: the caller passes a ``vol_for(K, T)`` provider (the vol surface) so each leg is
seeded with a skew-aware implied vol while the engine keeps zero data dependency.

Example::

    from eqd_desk.engine.presets import PresetParams, build_preset

    legs = build_preset(
        "butterfly",
        PresetParams(
            S=6312.45, base_t=30 / 365, width_pct=0.05, strike_step=25, vol_for=lambda K, T: 0.15
        ),
    )
    [(leg.side, leg.quantity, leg.K) for leg in legs]
    # [('long', 1, 5975.0), ('short', 2, 6300.0), ('long', 1, 6625.0)]
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from eqd_desk.engine.strategy import Leg, LegSide
from eqd_desk.engine.types import OptionType

PresetName = Literal[
    "call-vertical",
    "put-vertical",
    "straddle",
    "strangle",
    "risk-reversal",
    "butterfly",
    "iron-condor",
    "calendar",
]
"""Identifier of a standard structure understood by :func:`build_preset`."""

VolProvider = Callable[[float, float], float]
"""``vol_for(K, T) -> sigma``: implied vol (decimal) for strike ``K`` and expiry ``T``
(years), typically the vol surface's ``get_vol``."""


@dataclass(frozen=True, slots=True)
class PresetInfo:
    """A preset's identifier and its human-readable label (for pickers)."""

    name: PresetName
    label: str


PRESETS: tuple[PresetInfo, ...] = (
    PresetInfo("call-vertical", "Bull call spread"),
    PresetInfo("put-vertical", "Bear put spread"),
    PresetInfo("straddle", "Straddle"),
    PresetInfo("strangle", "Strangle"),
    PresetInfo("risk-reversal", "Risk reversal"),
    PresetInfo("butterfly", "Butterfly"),
    PresetInfo("iron-condor", "Iron condor"),
    PresetInfo("calendar", "Calendar"),
)
"""Every preset, in display order."""

CALENDAR_BACK_OFFSET = 60 / 365
"""How much further out (years, ~2 months) the back leg of a calendar expires."""


@dataclass(frozen=True, slots=True)
class PresetParams:
    """Geometry of a preset structure."""

    S: float
    """Spot to centre the structure on."""
    base_t: float
    """Base tenor (years) for the front/only expiry."""
    width_pct: float
    """Wing width as a fraction of spot (e.g. 0.05 = 5%)."""
    strike_step: float
    """Strike rounding step (price units, e.g. 25 index points on SPX)."""
    vol_for: VolProvider
    """Implied vol provider, typically ``surface.get_vol``."""


def round_to(x: float, step: float) -> float:
    """Round ``x`` to the nearest multiple of ``step``, ties toward +∞.

    Mirrors the TS ``Math.round(x / step) * step`` exactly. JavaScript's ``Math.round``
    rounds halves UP (``Math.round(2.5) = 3``, ``Math.round(-2.5) = -2``), whereas
    Python's built-in ``round`` rounds halves to even (``round(2.5) = 2``), so it cannot
    be used here: a spot of 6312.5 on a 25-point grid must give the same ATM strike
    (6325) in both engines. The fractional part ``y − floor(y)`` is computed exactly in
    floating point, so the tie test is exact too.
    """
    y = x / step
    n = math.floor(y)
    if y - n >= 0.5:
        n += 1
    return float(n) * step


def build_preset(name: PresetName, p: PresetParams) -> list[Leg]:
    """Build the legs of a standard structure centred on ``p.S``.

    Geometry: ``atm`` is spot rounded to the strike grid; the wing width ``w`` is
    ``width_pct`` of spot rounded to the grid, never less than one step. Every leg is
    quantity 1 except the butterfly body (2x). Leg ids are ``"<name>-<i>"`` in build order,
    so they are unique within the structure. Each leg's vol is ``p.vol_for(K, T)``,
    called in leg order.

    Legs by preset (+ long, − short; C = call, P = put; all at ``base_t`` unless noted)::

        call-vertical  +C(atm)  −C(atm+w)                          bull call spread
        put-vertical   +P(atm)  −P(atm−w)                          bear put spread
        straddle       +C(atm)  +P(atm)                            long vol at atm
        strangle       +P(atm−w)  +C(atm+w)                        cheaper long vol
        risk-reversal  −P(atm−w)  +C(atm+w)                        skew bet
        butterfly      +C(atm−w)  −2·C(atm)  +C(atm+w)             vol-of-vol / pin bet
        iron-condor    +P(atm−2w)  −P(atm−w)  −C(atm+w)  +C(atm+2w)  short vol, capped risk
        calendar       −C(atm, base_t)  +C(atm, base_t + 60d)       term-structure bet

    Raises:
        ValueError: if ``name`` is not a :data:`PresetName` (only possible from untyped
            callers, e.g. a raw widget string). The TS engine returns ``[]`` there; an
            empty position silently analysing to zero would hide the bug, so we raise.
    """
    base_t = p.base_t
    atm = round_to(p.S, p.strike_step)
    w = max(p.strike_step, round_to(p.S * p.width_pct, p.strike_step))
    back_t = base_t + CALENDAR_BACK_OFFSET  # ~2 months further out, for calendars

    counter = 0

    def leg(option_type: OptionType, side: LegSide, K: float, T: float, quantity: float = 1) -> Leg:
        nonlocal counter
        leg_id = f"{name}-{counter}"
        counter += 1
        return Leg(
            id=leg_id,
            type=option_type,
            side=side,
            quantity=quantity,
            K=K,
            T=T,
            sigma=p.vol_for(K, T),
        )

    match name:
        case "call-vertical":
            return [leg("call", "long", atm, base_t), leg("call", "short", atm + w, base_t)]
        case "put-vertical":
            return [leg("put", "long", atm, base_t), leg("put", "short", atm - w, base_t)]
        case "straddle":
            return [leg("call", "long", atm, base_t), leg("put", "long", atm, base_t)]
        case "strangle":
            return [leg("put", "long", atm - w, base_t), leg("call", "long", atm + w, base_t)]
        case "risk-reversal":
            return [leg("put", "short", atm - w, base_t), leg("call", "long", atm + w, base_t)]
        case "butterfly":
            return [
                leg("call", "long", atm - w, base_t),
                leg("call", "short", atm, base_t, 2),
                leg("call", "long", atm + w, base_t),
            ]
        case "iron-condor":
            return [
                leg("put", "long", atm - 2 * w, base_t),
                leg("put", "short", atm - w, base_t),
                leg("call", "short", atm + w, base_t),
                leg("call", "long", atm + 2 * w, base_t),
            ]
        case "calendar":
            return [leg("call", "short", atm, base_t), leg("call", "long", atm, back_t)]
        case _:
            raise ValueError(f"unknown preset {name!r}")


__all__ = [
    "CALENDAR_BACK_OFFSET",
    "PRESETS",
    "PresetInfo",
    "PresetName",
    "PresetParams",
    "VolProvider",
    "build_preset",
    "round_to",
]
