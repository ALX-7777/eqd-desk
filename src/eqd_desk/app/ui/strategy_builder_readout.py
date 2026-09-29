"""What the strategy builder's "Net position" panel shows for the net premium: the hero
number, its badge and the line under it. Pure: no Streamlit.

The React readout (``PositionReadout.tsx``) has two states, debit (you pay, shown ``−x.xx``)
and credit (you receive, ``+x.xx`` in green), and counts a zero premium as a debit, so an
empty position read "−0.00 DEBIT, you pay (debit)". Two neutral states are added here:

- **flat**: no legs at all (a trader's "flat" is having no position);
- **zero cost**: legs whose premiums cancel to the cent, like a risk reversal struck for
  zero cost. Nothing changes hands, so it is neither a debit nor a credit.

The debit / credit states keep the React wording (:data:`PREMIUM_SIDE_NOTES`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from eqd_desk.app.ui.format import MINUS, fmt_money
from eqd_desk.app.ui.theme import Tone
from eqd_desk.content.strategies import PREMIUM_SIDE_NOTES, premium_side

FLAT_BADGE: Final = "FLAT"
"""Badge of a position with no legs."""
FLAT_NOTE: Final = "no legs: nothing to pay or receive"
"""Line under the premium of a position with no legs."""
ZERO_COST_BADGE: Final = "ZERO COST"
"""Badge of legs whose premiums cancel to the cent."""
ZERO_COST_NOTE: Final = "the premiums cancel: nothing changes hands"
"""Line under a zero premium."""

PremiumBadgeColor = Literal["primary", "gray"]
"""Colour of the net-position badge (``st.badge`` colours)."""


@dataclass(frozen=True, slots=True)
class PremiumView:
    """The net premium as the panel shows it."""

    value: str
    """The hero number, signed from the trader's side: ``"−146.39"`` (you pay),
    ``"+74.40"`` (you receive), ``"0.00"`` (nothing changes hands)."""
    badge: str
    """``DEBIT``, ``CREDIT``, ``ZERO COST`` or ``FLAT``."""
    badge_color: PremiumBadgeColor
    """The accent for a debit (the React badge), gray otherwise."""
    detail: str
    """The line under the number."""
    tone: Tone | None
    """Colour of the number: green for a credit, plain otherwise."""


def premium_view(price: float, *, n_legs: int) -> PremiumView:
    """How the panel shows a structure's net premium ``price`` (currency units; > 0: the
    structure costs money) given its number of legs.

    A premium that rounds to ``0.00`` is shown as zero, never ``−0.00``: with no legs the
    position is flat, with legs it is zero cost. Otherwise the React debit / credit rule.
    """
    shown = fmt_money(abs(price))
    if n_legs == 0:
        return PremiumView(shown, FLAT_BADGE, "gray", FLAT_NOTE, None)
    if shown == fmt_money(0.0):
        return PremiumView(shown, ZERO_COST_BADGE, "gray", ZERO_COST_NOTE, None)
    side = premium_side(price)
    note = PREMIUM_SIDE_NOTES[side]
    if side == "debit":
        return PremiumView(f"{MINUS}{shown}", side.upper(), "primary", note, None)
    return PremiumView(f"+{shown}", side.upper(), "gray", note, "pos")


__all__ = [
    "FLAT_BADGE",
    "FLAT_NOTE",
    "ZERO_COST_BADGE",
    "ZERO_COST_NOTE",
    "PremiumBadgeColor",
    "PremiumView",
    "premium_view",
]
