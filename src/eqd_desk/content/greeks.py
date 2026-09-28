"""Greeks-lab teaching content: plain-language, desk-flavoured explanations for each greek
plus the key relationships a trainee must internalise.

Source: ``web/src/components/education.ts``, ported VERBATIM (every string equals the
TypeScript, enforced by ``tests/parity/test_content_parity.py``). This is a first-class
feature (a visible panel, not tooltips). Kept as data so the UI can render it consistently
and the plot/readout can deep-link to the relevant entry.

The constants after :data:`KEY_RELATIONSHIPS` are teaching prose lifted out of the React
markup (each carries its ``file:line``): the education-card field headings, the readout's
grouping of the greeks by order, and the captions under the greek-sweep and payoff charts.

All text is plain (no markup); see :mod:`eqd_desk.content` for how to render it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

GreekKey = Literal[
    "price",
    "delta",
    "gamma",
    "vega",
    "theta",
    "rho",
    "vanna",
    "volga",
    "charm",
    "speed",
    "color",
]
"""A key of the education content: the price itself or one of the greeks (the field names
of :class:`eqd_desk.engine.Greeks`)."""

GREEK_KEYS: Final[tuple[GreekKey, ...]] = (
    "price",
    "delta",
    "gamma",
    "vega",
    "theta",
    "rho",
    "vanna",
    "volga",
    "charm",
    "speed",
    "color",
)
"""The greeks in display order."""

PLOTTABLE_KEYS: Final[tuple[GreekKey, ...]] = GREEK_KEYS
"""Greeks the user can plot / explore (price is included — it's the premium curve)."""

GreekOrder = Literal["value", "first", "second", "third"]
"""Order of the derivative, for grouping (``"value"`` is the price itself)."""


@dataclass(frozen=True, slots=True)
class GreekDoc:
    """The education card for one greek (or the price)."""

    key: GreekKey
    title: str
    """e.g. "Delta (Δ)"."""
    order: GreekOrder
    """Order of the derivative, for grouping."""
    measures: str
    """What it measures, in one line."""
    intuition: str
    """Sign and size intuition."""
    when_large: str
    """When it is large / matters most."""
    desk: str
    """How a market-maker actually uses or hedges it."""


GREEK_DOCS: Final[Mapping[GreekKey, GreekDoc]] = MappingProxyType(
    {
        "price": GreekDoc(
            key="price",
            title="Price (Premium)",
            order="value",
            measures="The fair value of the option today under Black–Scholes–Merton.",
            intuition=(
                "Intrinsic value (how in-the-money you are, discounted) plus time value (the "
                "optionality). Always ≥ the discounted intrinsic; the gap is what you pay for "
                "convexity and the chance of finishing further ITM."
            ),
            when_large=(
                "Highest for deep ITM and for long-dated / high-vol options. Time value peaks "
                "around the money."
            ),
            desk=(
                "The number you quote. You make a two-way market around it: bid a bit below, offer "
                "a bit above, and manage the risk you are left with."
            ),
        ),
        "delta": GreekDoc(
            key="delta",
            title="Delta (Δ)",
            order="first",
            measures="Sensitivity of the option price to a $1 move in spot — the hedge ratio.",
            intuition=(
                "Call delta runs 0 → e^(−qT) (≈0 → 1); put delta runs −e^(−qT) → 0. ATM ≈ ±0.5. It "
                "is also a rough risk-neutral probability of finishing ITM. Buy a call → positive "
                "delta (long the market)."
            ),
            when_large=(
                "Approaches ±1 deep ITM near expiry, ~0 deep OTM. The transition is sharpest ATM "
                "as T → 0 (that steepness IS gamma)."
            ),
            desk=(
                "You hedge delta by trading the underlying (an index future proxy): short Δ units "
                "of the index against a long call to be delta-neutral, then re-hedge as Δ drifts."
            ),
        ),
        "gamma": GreekDoc(
            key="gamma",
            title="Gamma (Γ)",
            order="second",
            measures="How fast delta itself changes as spot moves (convexity of the position).",
            intuition=(
                "Long options are long gamma (Γ ≥ 0): your delta grows as spot rises and shrinks "
                "as it falls, so a delta-hedge mechanically buys low and sells high. That "
                "re-hedging harvests realised volatility — paid for with theta."
            ),
            when_large=(
                "Sharply peaked at-the-money and explodes as T → 0. A long-dated option has low, "
                "broad gamma; a 1-day ATM option has enormous gamma."
            ),
            desk=(
                "Gamma scalping: long gamma + delta-hedging profits when realised vol beats the "
                "implied vol you paid. Near expiry, ATM gamma creates pin risk — delta whips "
                "between 0 and 1 around the strike."
            ),
        ),
        "vega": GreekDoc(
            key="vega",
            title="Vega (ν)",
            order="first",
            measures="Sensitivity to a 1-point change in implied volatility.",
            intuition=(
                "Long options are long vega (ν ≥ 0): higher implied vol → richer optionality → "
                "higher premium. Vega is the pure implied-vol exposure, independent of whether "
                "spot actually moves."
            ),
            when_large=(
                "Largest at-the-money and for LONG-dated options (vega scales with √T). "
                "Short-dated options have little vega but lots of gamma."
            ),
            desk=(
                "Vega is the implied-vol play. You express a view on the level of the vol surface "
                "(the VIX/VSTOXX gauge) with longer-dated structures; you warehouse vega and hedge "
                "it with other options, not the underlying."
            ),
        ),
        "theta": GreekDoc(
            key="theta",
            title="Theta (Θ)",
            order="first",
            measures="Time decay — how much value the option loses as one calendar day passes.",
            intuition=(
                "Long options usually have negative theta: optionality bleeds away as expiry "
                "approaches. It is the rent you pay to be long gamma. Reported per calendar day "
                "(the engine uses ∂/∂t = −∂/∂T)."
            ),
            when_large=(
                "Most negative for at-the-money, short-dated options — exactly where gamma is "
                "largest. The two are locked together by the BSM PDE."
            ),
            desk=(
                "Theta vs gamma is the core trade-off: you collect/pay θ each day and earn/lose "
                "½ΓS²·(realised² − implied²). Short-dated ATM = max theta and max gamma."
            ),
        ),
        "rho": GreekDoc(
            key="rho",
            title="Rho (ρ)",
            order="first",
            measures="Sensitivity to a 1-point change in the risk-free rate.",
            intuition=(
                "Calls are rho-positive, puts rho-negative (higher rates lift the forward). "
                "Usually the quietest greek for short-dated index options, but real for long-dated "
                "structures and for the carry (r − q) embedded in the forward."
            ),
            when_large=(
                "Grows with maturity and moneyness (scales with K·T·e^(−rT)). Matters for LEAPS "
                "and rate-sensitive books; small for weeklies."
            ),
            desk=(
                "Index desks watch rho mostly through the forward and the financing/dividend basis "
                "(r − q); pure rate risk is hedged with rates instruments when a long-dated book "
                "accumulates it."
            ),
        ),
        "vanna": GreekDoc(
            key="vanna",
            title="Vanna",
            order="second",
            measures=(
                "Cross-greek: how delta moves when vol moves (= how vega moves when spot moves)."
            ),
            intuition=(
                "The link between spot risk and vol risk. Sign depends on moneyness (it flips "
                "through the money). With equity skew — where spot down tends to push vol up — "
                "vanna means your delta-hedge needs adjusting precisely when the market gaps."
            ),
            when_large=(
                "Largest in the wings (away from ATM, where d2 is sizeable) and for shorter "
                "maturities. Zero where d2 = 0."
            ),
            desk=(
                "Vanna is the heart of skew/risk-reversal trading. A risk reversal (long call vs "
                "short put) is essentially a vanna position — a bet on how the surface tilts as "
                "spot moves."
            ),
        ),
        "volga": GreekDoc(
            key="volga",
            title="Volga (Vomma)",
            order="second",
            measures=(
                "Convexity in volatility — how vega changes as implied vol changes (vol-of-vol)."
            ),
            intuition=(
                "Long volga = long the wings: strangles and far-OTM options gain vega as vol "
                "rises, so they benefit from an unstable, moving vol surface. It is exactly zero "
                "where d1·d2 = 0."
            ),
            when_large=(
                "Largest for out-of-the-money options (where d1·d2 is big); near zero around the "
                "money."
            ),
            desk=(
                "Volga prices the smile. A butterfly (long wings, short body) is a volga / "
                "vol-of-vol bet: it pays if implied vol is itself volatile."
            ),
        ),
        "charm": GreekDoc(
            key="charm",
            title="Charm (Delta Decay)",
            order="second",
            measures="How delta drifts as one calendar day passes, with spot unchanged.",
            intuition=(
                "Your hedge does not stand still in time: even on a flat day, delta moves. Charm "
                "tells you how much to re-hedge purely because the clock ticked."
            ),
            when_large=(
                "Largest for near-ATM options approaching expiry; notable across weekends (three "
                "days of decay at once)."
            ),
            desk=(
                "Desks pre-hedge charm into Friday/over weekends and around expiry so they are not "
                "forced to chase a drifting delta on Monday."
            ),
        ),
        "speed": GreekDoc(
            key="speed",
            title="Speed",
            order="third",
            measures="Third-order: how gamma changes as spot moves (∂Γ/∂S).",
            intuition=(
                "The rate of change of your convexity. For a single vanilla it is small, but "
                "across a large book — or near barriers and on big gap moves — speed governs how "
                "quickly your gamma profile shifts under you."
            ),
            when_large=(
                "Largest near the money for short maturities, where gamma is most sharply peaked."
            ),
            desk=(
                "Watched on big or path-dependent books: when gamma is itself moving fast, a "
                "static delta/gamma hedge degrades quickly and must be refreshed."
            ),
        ),
        "color": GreekDoc(
            key="color",
            title="Color (Gamma Decay)",
            order="third",
            measures="How gamma changes as one calendar day passes (∂Γ/∂t).",
            intuition=(
                "Gamma is not static in time: as expiry nears, an ATM option’s gamma concentrates "
                "and spikes, while away-from-money gamma fades. Color is that re-shaping of the "
                "gamma profile day by day."
            ),
            when_large=(
                "Largest at-the-money close to expiry — the same region where pin risk lives."
            ),
            desk=(
                "Tells you how your gamma (and therefore your scalping P&L and pin risk) will look "
                "tomorrow, so you can plan re-hedging into expiry."
            ),
        ),
    }
)
"""The education card of every :data:`GreekKey`, in display order. Read-only."""


@dataclass(frozen=True, slots=True)
class Relationship:
    """One of the standing "key relationships" shown under the greek card."""

    title: str
    body: str


KEY_RELATIONSHIPS: Final[tuple[Relationship, ...]] = (
    Relationship(
        title="Gamma ↔ Theta (the BSM PDE)",
        body=(
            "They are two sides of one coin: Θ + ½σ²S²Γ + (r−q)SΔ − rV = 0. A delta-hedged "
            "option’s P&L over a small step is ≈ ½·Γ·S²·((ΔS/S)² − σ²·dt) — i.e. ½·Γ·S²·(realised "
            "vol² − implied vol²). Long gamma makes money when the market moves MORE than the "
            "implied vol you paid in theta; it loses when the market is calmer than implied."
        ),
    ),
    Relationship(
        title="Gamma vs Vega across maturities",
        body=(
            "Short-dated options are a gamma / realised-vol play: huge gamma, tiny vega — you live "
            "or die on day-to-day moves. Long-dated options are a vega / implied-vol play: little "
            "gamma, lots of vega — you live or die on the level of the vol surface. The same "
            "volatility view is expressed with a different instrument depending on the horizon."
        ),
    ),
    Relationship(
        title="Pin risk near expiry",
        body=(
            "As T → 0, ATM gamma, charm and color all blow up. Delta snaps between 0 and 1 across "
            "the strike, so a tiny spot move flips your hedge from flat to fully long/short. "
            "Hedging becomes violent and expensive — that is pin risk, and it is why the "
            "acceptance test watches ATM gamma spike as T shrinks."
        ),
    ),
    Relationship(
        title="Why the surface must move with spot",
        body=(
            "Equity skew is real: spot down → vol up (the leverage effect). That co-movement is "
            "what makes vanna (∂Δ/∂σ) and volga bite — your delta-hedge has to change exactly when "
            "the market gaps and vol jumps. A static surface would make skew cosmetic and teach "
            "the wrong lessons; later phases evolve the whole surface with the simulated path."
        ),
    ),
)
"""The relationships every trainee must internalise: gamma↔theta (the BSM PDE), gamma vs
vega across maturities, pin risk near expiry, and why the surface must move with spot."""

# ------------------------------------------------------------------ prose from the markup

GreekDocField = Literal["measures", "intuition", "when_large", "desk"]
"""The prose fields of a :class:`GreekDoc`, in the order the education card shows them."""

GREEK_DOC_FIELD_LABELS: Final[Mapping[GreekDocField, str]] = MappingProxyType(
    {
        # web/src/components/EducationPanel.tsx:39-46 (the <dt> headings of the card)
        "measures": "Measures",
        "intuition": "Intuition",
        "when_large": "When it's large",
        "desk": "On the desk",
    }
)
"""Heading shown above each prose field of the greek education card, in display order."""


@dataclass(frozen=True, slots=True)
class GreekGroup:
    """A titled group of greeks in the price & greeks readout."""

    title: str
    keys: tuple[GreekKey, ...]


GREEK_GROUPS: Final[tuple[GreekGroup, ...]] = (
    # web/src/components/GreeksReadout.tsx:20-24 (identical in PositionReadout.tsx:19-23)
    GreekGroup("First order", ("delta", "vega", "theta", "rho")),
    GreekGroup("Second order / cross", ("gamma", "vanna", "volga", "charm")),
    GreekGroup("Third order", ("speed", "color")),
)
"""How the readout groups the greeks (price is shown separately, as the hero number)."""

XAxisKey = Literal["S", "sigma", "T"]
"""The variable a greek is swept against in the greeks lab: spot, vol or time to expiry
(the :class:`eqd_desk.engine.BsmInputs` field names)."""

GREEK_SWEEP_CAPTION_SUFFIXES: Final[Mapping[XAxisKey, str]] = MappingProxyType(
    {
        # web/src/components/PlotsPanel.tsx:146-147 (appended to the greek's `measures`)
        "S": " — dashed: current spot; dotted: strike.",
        "sigma": " — dashed: current vol.",
        "T": " — dashed: current tenor.",
    }
)
"""How to read the greek-vs-x chart's reference lines, per x axis. Each starts with a
space: it is appended directly to the greek's one-line definition (see
:func:`greek_sweep_caption`)."""


def greek_sweep_caption(key: GreekKey, x_axis: XAxisKey) -> str:
    """Caption under the greek-vs-x chart (web/src/components/PlotsPanel.tsx:144-148).

    The greek's one-line definition (``GREEK_DOCS[key].measures``) followed by what the
    chart's reference lines mark for that x axis.
    """
    return GREEK_DOCS[key].measures + GREEK_SWEEP_CAPTION_SUFFIXES[x_axis]


# web/src/components/PlotsPanel.tsx:196-198
PAYOFF_CAPTION: Final = (
    "Solid: value at expiry (intrinsic). Thin: value now (premium) — the gap is time value."
)
"""Caption under the single-option payoff chart (intrinsic at expiry vs premium now)."""

# web/src/components/InputPanel.tsx:163
SURFACE_VOL_HINT: Final = "Set σ to the seed vol surface at this strike & tenor (shows the skew)"
"""Hint for the "σ ← surface" action, which snaps σ to the seed skew at the current
strike/tenor (so the skew is something you can feel, not just read about)."""
