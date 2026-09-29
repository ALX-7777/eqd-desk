"""Strategy-builder teaching content: the VIEW each standard index-desk structure expresses,
its leg structure, greek signature, and the main risk. Desk-flavoured and concise.

Source: ``web/src/components/strategyDocs.ts``, ported VERBATIM (every string equals the
TypeScript, enforced by ``tests/parity/test_content_parity.py``).

The constants after :data:`STRATEGY_DOCS` are teaching prose lifted out of the React
markup (each carries its ``file:line``): the card's field headings, the note shown for a
hand-edited (custom) structure, the payoff-chart caption and the debit/credit notes.

Two panels reuse the greeks-lab content rather than new text: the caption under the
aggregate-greek profile chart is the greek's one-line definition,
``eqd_desk.content.greeks.GREEK_DOCS[key].measures`` (StrategyPlots.tsx:186), and the
"Greek detail" section is the greeks-lab education panel (StrategyEducation.tsx:58-59).
The card title is the preset's display label (``PRESETS`` in web/src/engine/presets.ts).

All text is plain (no markup); see :mod:`eqd_desk.content` for how to render it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from eqd_desk.engine.presets import PresetName

PRESET_NAMES: Final[tuple[PresetName, ...]] = (
    "call-vertical",
    "put-vertical",
    "straddle",
    "strangle",
    "risk-reversal",
    "butterfly",
    "iron-condor",
    "calendar",
)
"""Every preset structure, in the display order of the preset picker. The names are the
engine's :data:`~eqd_desk.engine.presets.PresetName` (the one definition; re-exported here
for the content keys)."""


@dataclass(frozen=True, slots=True)
class StrategyDoc:
    """The desk rationale for one preset structure."""

    name: PresetName
    view: str
    """The market view it expresses."""
    structure: str
    """What the legs are."""
    greeks: str
    """Greek signature — what risks you actually own."""
    risk: str
    """The principal risk / max loss shape."""


STRATEGY_DOCS: Final[Mapping[PresetName, StrategyDoc]] = MappingProxyType(
    {
        "call-vertical": StrategyDoc(
            name="call-vertical",
            view=(
                "Moderately bullish, with a budget. You want upside but refuse to pay full premium "
                "for an outright call."
            ),
            structure=(
                "Long a lower-strike call, short a higher-strike call (same expiry). A debit "
                "spread."
            ),
            greeks=(
                "Positive delta that fades to zero above the short strike (your upside is capped). "
                "Net vega and gamma are small — you sold most of the convexity back. Theta is mild."
            ),
            risk=(
                "Defined: max loss = the net debit; max gain = the strike width − debit. You trade "
                "unlimited upside for a cheaper entry."
            ),
        ),
        "put-vertical": StrategyDoc(
            name="put-vertical",
            view="Moderately bearish with defined risk — the mirror of the bull call spread.",
            structure=(
                "Long a higher-strike put, short a lower-strike put (same expiry). A debit spread."
            ),
            greeks=(
                "Negative delta that flattens below the short strike. Small net vega/gamma; the "
                "short leg finances the long. Mild theta."
            ),
            risk="Defined: max loss = the net debit; max gain = the strike width − debit.",
        ),
        "straddle": StrategyDoc(
            name="straddle",
            view=(
                "You expect a big move but not its direction — a bet that REALISED vol will beat "
                "the implied vol you pay."
            ),
            structure="Long a call and a long put at the same (ATM) strike and expiry.",
            greeks=(
                "Delta ≈ 0 at the strike, long gamma and long vega (you own convexity and the vol "
                "level), and you pay for it with negative theta every day."
            ),
            risk=(
                "Max loss = the premium paid, if spot pins the strike. The classic gamma-scalping "
                "/ long-vol position."
            ),
        ),
        "strangle": StrategyDoc(
            name="strangle",
            view=(
                "A cheaper straddle: still a long-vol, big-move bet, but you need a LARGER move to "
                "pay off."
            ),
            structure=(
                "Long an out-of-the-money put and a long out-of-the-money call (same expiry)."
            ),
            greeks=(
                "Delta ≈ 0 between the strikes, long gamma and long vega, negative theta. Less "
                "premium than a straddle, but a wider dead zone."
            ),
            risk="Max loss = the premium paid, across the whole zone between the strikes.",
        ),
        "risk-reversal": StrategyDoc(
            name="risk-reversal",
            view=(
                "Bullish AND a pure SKEW bet. You sell the (expensive) downside put to fund the "
                "(cheaper) upside call — you are short skew."
            ),
            structure=(
                "Long an out-of-the-money call, short an out-of-the-money put. Often near-zero "
                "cost."
            ),
            greeks=(
                "Positive delta, and most importantly a big VANNA: with equity skew (spot down → "
                "vol up) your delta-hedge moves exactly when the market gaps. Low net premium but "
                "real tail risk."
            ),
            risk=(
                "The short put gives unlimited downside if the market sells off — you are paid the "
                "skew to take that risk."
            ),
        ),
        "butterfly": StrategyDoc(
            name="butterfly",
            view=(
                "A pin / low-vol bet: you expect spot to sit near the body strike at expiry. A bet "
                "on the smile (vol-of-vol)."
            ),
            structure=(
                "Long one wing, short two body, long the other wing (all calls or all puts), wings "
                "symmetric."
            ),
            greeks=(
                "Near the body you are short gamma and long theta (time works for you); cheap and "
                "defined. Sensitive to the curvature of the vol smile."
            ),
            risk=(
                "Defined: max loss = the small net debit; max gain peaks if spot lands exactly on "
                "the body strike at expiry."
            ),
        ),
        "iron-condor": StrategyDoc(
            name="iron-condor",
            view=(
                "Range-bound: you collect premium betting spot stays between the short strikes. A "
                "short-vol / income structure."
            ),
            structure=(
                "Short a put spread below and short a call spread above (long wings further out). "
                "A net credit."
            ),
            greeks=(
                "Short vega and short gamma with positive theta — you are paid to wait, and hurt "
                "by a big move in either direction."
            ),
            risk=(
                "Defined: max gain = the credit; max loss = a wing width − credit if spot breaks "
                "through a short strike."
            ),
        ),
        "calendar": StrategyDoc(
            name="calendar",
            view=(
                "A TERM-STRUCTURE bet: sell rich front-month decay, own back-month vega. Profits "
                "if spot sits near the strike at the front expiry."
            ),
            structure=(
                "Short the front-month option, long the back-month option at the same strike. A "
                "debit."
            ),
            greeks=(
                "Long vega (the back month dominates) and positive theta (the front decays "
                "faster). Value peaks at the strike at the front expiry — hence the tent-shaped "
                "payoff."
            ),
            risk=(
                "Max loss ≈ the debit. Hurt by a large spot move away from the strike, or by "
                "back-month implied vol falling."
            ),
        ),
    }
)
"""The desk rationale of every preset, in display order. Read-only."""

# ------------------------------------------------------------------ prose from the markup

StrategyDocField = Literal["view", "structure", "greeks", "risk"]
"""The prose fields of a :class:`StrategyDoc`, in the order the card shows them."""

STRATEGY_DOC_FIELD_LABELS: Final[Mapping[StrategyDocField, str]] = MappingProxyType(
    {
        # web/src/components/StrategyEducation.tsx:40-47 (the <dt> headings of the card)
        "view": "The view",
        "structure": "Structure",
        "greeks": "Greek signature",
        "risk": "Principal risk",
    }
)
"""Heading shown above each prose field of the strategy card, in display order."""

# web/src/components/StrategyEducation.tsx:52-54
CUSTOM_STRUCTURE_NOTE: Final = (
    "Custom structure — edit the legs freely. Pick a preset to see its desk rationale."
)
"""Shown instead of the strategy card once the legs have been edited by hand."""

# web/src/components/StrategyPlots.tsx:128-131
PAYOFF_CAPTION: Final = (
    "Solid: P&L at the front expiry. Thin: P&L now (mark-to-market). Dashed: spot; "
    "dotted: strikes. Crosses zero at the break-evens."
)
"""Caption under the structure's P&L-vs-spot chart. Both curves are net of premium, and
the expiry curve is taken at the FRONT expiry (correct for calendars too)."""

# web/src/components/PositionReadout.tsx:46
NET_PREMIUM_NOTE: Final = "Net premium of the structure (debit = you pay, credit = you receive)."
"""What the net-premium hero number means."""

PremiumSide = Literal["debit", "credit"]
"""Whether a structure costs money to put on (debit) or pays you (credit)."""

PREMIUM_SIDE_NOTES: Final[Mapping[PremiumSide, str]] = MappingProxyType(
    {
        # web/src/components/PositionReadout.tsx:54
        "debit": "you pay (debit)",
        "credit": "you receive (credit)",
    }
)
"""Sub-caption under the net premium, per side."""


def premium_side(net_premium: float) -> PremiumSide:
    """Classify a structure's net premium (web/src/components/PositionReadout.tsx:32-33).

    net premium ≥ 0 ⇒ you pay (debit); < 0 ⇒ you receive (credit). Zero counts as a debit.
    """
    return "debit" if net_premium >= 0 else "credit"


# web/src/components/LegsEditor.tsx:30
EMPTY_LEGS_HINT: Final = "No legs — pick a preset or add one."
"""Shown in the legs table when the structure has no legs."""

# Streamlit-UI addition (the React Reset button has no tooltip). Filled with the builder's
# defaults, so the text cannot drift from what Reset restores.
RESET_HELP_TEMPLATE: Final = (
    "Restore the seed market, a {tenor_days}-day tenor and {wing_pct} % wings, and rebuild "
    "the {structure}."
)
"""Tooltip of the strategy builder's Reset. ``{tenor_days}``: the default preset tenor in
calendar days; ``{wing_pct}``: the default wing in % of spot; ``{structure}``: the default
preset's label, lower-cased."""


__all__ = [
    "CUSTOM_STRUCTURE_NOTE",
    "EMPTY_LEGS_HINT",
    "NET_PREMIUM_NOTE",
    "PAYOFF_CAPTION",
    "PREMIUM_SIDE_NOTES",
    "PRESET_NAMES",
    "RESET_HELP_TEMPLATE",
    "STRATEGY_DOCS",
    "STRATEGY_DOC_FIELD_LABELS",
    "PremiumSide",
    "PresetName",
    "StrategyDoc",
    "StrategyDocField",
    "premium_side",
]
