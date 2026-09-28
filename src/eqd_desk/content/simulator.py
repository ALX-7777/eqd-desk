"""Trading-simulator teaching content: the market-making loop, the spread/fill tradeoff,
gamma scalping (realised vs implied), and how to read a P&L explain. Plus per-term notes
for the attribution panel.

Source: ``web/src/components/simDocs.ts``, ported VERBATIM (every string equals the
TypeScript, enforced by ``tests/parity/test_content_parity.py``).

The constants after :data:`ATTRIBUTION_TERMS` are the desk instructions, captions and
messages lifted out of ``web/src/components/SimulatorView.tsx`` (each carries its line).
Message templates use :meth:`str.format` named placeholders; the UI fills them with
already-formatted values (money through its money formatter, sides upper-cased).

All text is plain (no markup); see :mod:`eqd_desk.content` for how to render it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal


@dataclass(frozen=True, slots=True)
class SimConcept:
    """One market-making concept of the simulator's "Learn" panel."""

    title: str
    body: str


SIM_CONCEPTS: Final[tuple[SimConcept, ...]] = (
    SimConcept(
        title="The market-making loop",
        body=(
            "A client asks for a price; you quote a two-way (bid/ask around fair); you win or lose "
            "the trade; you are left with risk; you hedge it; and at end-of-day you attribute your "
            "P&L. Every tick of this simulator is one turn of that loop — your job is to be paid "
            "for the risk you warehouse."
        ),
    ),
    SimConcept(
        title="Spread vs fill — the edge tradeoff",
        body=(
            "A wider spread earns more edge per trade but wins less flow; a tighter spread wins "
            "more trades but is paid less for the risk. The skill is pricing tight enough to "
            "capture flow yet wide enough to be compensated — and skewing your quote when you "
            "already have a position you want to reduce."
        ),
    ),
    SimConcept(
        title="Gamma scalping — realised vs implied",
        body=(
            "Once you hold an option and delta-hedge, your P&L per unit time is ≈ "
            "½·Γ·S²·(σ_realised² − σ_implied²). Long gamma makes money when the market moves MORE "
            "than the vol you paid (realised > implied) and bleeds theta when it is calmer; short "
            "gamma is the reverse. The vol index (VIX/VSTOXX) is the implied gauge you are betting "
            "against."
        ),
    ),
    SimConcept(
        title="The leverage effect bites twice",
        body=(
            "Spot down → vol up. So a sell-off hits a short-gamma / short-vega book twice: a gamma "
            "loss on the move AND a vega loss as implied vol spikes. The vanna term in your P&L "
            "explain is exactly this spot-vol interaction — it is why equity skew is not cosmetic."
        ),
    ),
    SimConcept(
        title="Reading a P&L explain",
        body=(
            "Decompose each step into delta (spot × your net delta), gamma (convexity, ½Γ·ΔS²), "
            "theta (decay), vega (implied-vol move), vanna (spot-vol cross), volga (vol convexity) "
            "and a residual. A small residual means the second-order Taylor explains your day — "
            "you understand your risk. A large residual flags a gap, a big move, or risk you are "
            "not measuring."
        ),
    ),
)
"""The concepts behind the simulator, in reading order."""

AttributionKey = Literal["delta", "gamma", "theta", "vega", "vanna", "volga", "residual"]
"""A term of the second-order Taylor P&L explain (plus what it leaves unexplained)."""


@dataclass(frozen=True, slots=True)
class AttributionTerm:
    """How to read one bar of the P&L explain."""

    key: AttributionKey
    label: str
    note: str


ATTRIBUTION_TERMS: Final[tuple[AttributionTerm, ...]] = (
    AttributionTerm(
        key="delta",
        label="Delta",
        note="Spot moved × your net delta (options + hedge). Hedge it to isolate vol/gamma.",
    ),
    AttributionTerm(
        key="gamma",
        label="Gamma",
        note="Convexity: ½·Γ·ΔS². Long gamma loves big moves; short gamma fears them.",
    ),
    AttributionTerm(
        key="theta",
        label="Theta",
        note="Time decay — the rent you pay (long) or collect (short) for gamma.",
    ),
    AttributionTerm(
        key="vega",
        label="Vega",
        note="Implied vol moved × your vega — the level of the surface.",
    ),
    AttributionTerm(
        key="vanna",
        label="Vanna",
        note="Spot–vol cross (ΔS×Δσ). Bites with skew / the leverage effect.",
    ),
    AttributionTerm(
        key="volga",
        label="Volga",
        note="Vol convexity (½·volga·Δσ²) — the value of the wings.",
    ),
    AttributionTerm(
        key="residual",
        label="Residual",
        note="What 2nd-order Taylor missed: 3rd-order, big gaps, vol-path. Large ⇒ look closer.",
    ),
)
"""The P&L-explain terms, in the order the attribution chart shows them."""

# ------------------------------------------------------------------ prose from the markup

# web/src/components/SimulatorView.tsx:370
REPLAY_CAPTION_TEMPLATE: Final = (
    "Undisclosed slice of real S&P 500 / VIX history ({count} days on file)."
)
"""Caption in historical-replay mode. ``{count}``: number of days in the history file."""

# web/src/components/SimulatorView.tsx:373
REPLAY_LENGTH_HINT: Final = "Applies on the next reset."
"""Shown under the replay-length slider: a new length only takes effect on reset."""

# web/src/components/SimulatorView.tsx:377
EPISODE_ENDED_MESSAGE: Final = "Episode ended — reset for a new one."
"""Shown when a historical-replay episode has reached its last day."""

# web/src/components/SimulatorView.tsx:406
EMPTY_QUEUE_HINT: Final = "No live requests — Auto brings them in, or request one."
"""Shown when no client RFQ is live."""

RfqVerdict = Literal["hedges", "adds"]
"""Whether winning an RFQ would reduce or add to the book's risk (no flag when neutral)."""

RFQ_VERDICT_HINTS: Final[Mapping[RfqVerdict, str]] = MappingProxyType(
    {
        # web/src/components/SimulatorView.tsx:414 (tooltip of the ↓ / ↑ flag on an RFQ)
        "hedges": "winning this cuts your risk",
        "adds": "winning this adds risk",
    }
)
"""Explanation of the risk flag shown on an RFQ."""

# web/src/components/SimulatorView.tsx:235
FILL_MESSAGE_TEMPLATE: Final = "Filled — you {side} {size}× {label} @ {price} · edge {edge}"
"""Result of a winning quote. ``{side}``: your side, upper-cased (BUY / SELL); ``{size}``:
the RFQ size; ``{label}``: the RFQ label; ``{price}`` / ``{edge}``: formatted money."""

# web/src/components/SimulatorView.tsx:237
MISS_MESSAGE_TEMPLATE: Final = "Missed {label} — client traded elsewhere"
"""Result of a losing quote. ``{label}``: the RFQ label."""

# web/src/components/SimulatorView.tsx:537
OPTION_HEDGE_CAPTION: Final = (
    "Option hedges cross the market spread (a cost); they flatten one greek but pick up others."
)
"""Caption under the flatten-delta / vega / gamma hedge buttons."""

# web/src/components/SimulatorView.tsx:544
EMPTY_BOOK_HINT: Final = "No trades yet."
"""Shown in the positions blotter before the first trade."""

# web/src/components/SimulatorView.tsx:639
ADVISOR_SUBTITLE: Final = "Reads your live book & the market — ranked by what to deal with first."
"""Subtitle of the desk advisor (its advice itself comes from the engine)."""

# web/src/components/SimulatorView.tsx:672 (the React UI prefixes a "⚖︎" icon)
JOINT_HEDGE_TITLE: Final = "Hedge the book together"
"""Title of the combined (options + future) hedge suggestion."""

# web/src/components/SimulatorView.tsx:673
JOINT_HEDGE_SUBTITLE: Final = "greeks interact — don't chase them one at a time"
"""Why the combined hedge exists: fixing one greek with an option moves the others."""

JointHedgeRole = Literal["future", "gamma", "vega"]
"""What one leg of the combined hedge is for."""

JOINT_HEDGE_ROLE_LABELS: Final[Mapping[JointHedgeRole, str]] = MappingProxyType(
    {
        # web/src/components/SimulatorView.tsx:684
        "future": "cleans up Δ (last)",
        "gamma": "gamma",
        "vega": "vega",
    }
)
"""Label beside each leg of the combined hedge."""

JOINT_HEDGE_GAMMA_MAX_TENOR_DAYS: Final = 30
"""An option leg of at most this many days is the combined hedge's GAMMA leg (short-dated
options are the gamma instrument); a longer one is its VEGA leg."""


def joint_hedge_role(instrument: Literal["future", "option"], tenor_days: float | None) -> str:
    """Label for one leg of the combined hedge (web/src/components/SimulatorView.tsx:684).

    The future goes LAST and only cleans up the residual delta; an option leg is the gamma
    leg when short-dated (≤ :data:`JOINT_HEDGE_GAMMA_MAX_TENOR_DAYS`), else the vega leg.
    A missing or zero tenor counts as the vega leg, as in the TypeScript.
    """
    if instrument == "future":
        return JOINT_HEDGE_ROLE_LABELS["future"]
    if tenor_days and tenor_days <= JOINT_HEDGE_GAMMA_MAX_TENOR_DAYS:
        return JOINT_HEDGE_ROLE_LABELS["gamma"]
    return JOINT_HEDGE_ROLE_LABELS["vega"]
