"""Exotics teaching content: what each instrument is, the behaviour that makes it
interesting (and dangerous), and the key risk. These are the teaching points the spec
calls out: digital pin risk, barrier gamma explosion, autocall path-dependence, and the
variance-swap / VIX link.

Source: ``web/src/components/exoticsDocs.ts``, ported VERBATIM (every string equals the
TypeScript, enforced by ``tests/parity/test_content_parity.py``).

The constants after :data:`EXOTIC_DOCS` are teaching prose lifted out of the React markup
(each carries its ``file:line``): the card headings, the sub-tab labels, the "how to read
this" captions under each exotic's characteristic chart, and the notes beside the
readout numbers. A few are Streamlit-UI additions for controls and notes the React views do
not have (the barrier's direction / knock split and its "already knocked" notes, the
asset-or-nothing payout, the autocallable's missing gamma, the variance swap's skew switch);
each is marked as such.

The chart captions name the React chart styling ("Blue", "Orange", "Red dashed", "dotted",
"accent" …): a UI that shows them should draw the corresponding series in matching styles
(or adapt the wording). All text is plain (no markup); see :mod:`eqd_desk.content` for how
to render it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from eqd_desk.content.greeks import GreekDocField

ExoticKind = Literal["digital", "barrier", "autocall", "varswap"]
"""The four Phase 3 exotics."""

EXOTIC_KINDS: Final[tuple[ExoticKind, ...]] = ("digital", "barrier", "autocall", "varswap")
"""Every exotic, in the order of :data:`EXOTIC_DOCS` (the tabs use
:data:`EXOTIC_TAB_LABELS`' order instead)."""

ExoticMetric = Literal["price", "delta", "gamma", "vega", "theta", "rho"]
"""The price + greeks an exotic computes (subset of the vanilla greeks)."""

EXOTIC_METRICS: Final[tuple[ExoticMetric, ...]] = (
    "price",
    "delta",
    "gamma",
    "vega",
    "theta",
    "rho",
)
"""The price + greeks an exotic computes, in chip order."""


@dataclass(frozen=True, slots=True)
class ExoticDoc:
    """The education card for one exotic."""

    kind: ExoticKind
    title: str
    what: str
    """What the instrument is and what view it expresses."""
    behaviour: str
    """The behaviour that matters — the teaching point."""
    risk: str
    """The principal risk / why it's hard to hedge."""


EXOTIC_DOCS: Final[Mapping[ExoticKind, ExoticDoc]] = MappingProxyType(
    {
        "digital": ExoticDoc(
            kind="digital",
            title="Digital (binary) option",
            what=(
                "Pays a fixed cash amount if the underlying finishes beyond the strike — a bet on "
                "a LEVEL, not a magnitude. The building block of structured coupons (an autocall "
                "coupon is a digital)."
            ),
            behaviour=(
                "A digital is the limit of an infinitely tight call spread: replicate it with "
                "(Q/Δ) call spreads of width Δ and let Δ → 0. Right at the strike near expiry, "
                "delta and gamma spike toward infinity — drag the spot across the strike and the "
                "payout flips from 0 to Q."
            ),
            risk=(
                "Un-hedgeable pin risk at expiry: an arbitrarily small move across the strike "
                "changes the payout by the full Q. Desks over-hedge with a FINITE call spread and "
                "charge the spread width as a cushion — you cannot hold the exact digital delta "
                "near expiry."
            ),
        ),
        "barrier": ExoticDoc(
            kind="barrier",
            title="Barrier option",
            what=(
                "A vanilla that switches on (knock-in) or off (knock-out) if the underlying "
                "touches a barrier H. Cheaper than the vanilla — you give up the knocked-out "
                "states — so it is a popular way to cheapen a directional view. Closed-form under "
                "continuous monitoring; knock-in + knock-out = vanilla."
            ),
            behaviour=(
                "Near the barrier a knock-out’s value and delta collapse toward zero, so GAMMA "
                "EXPLODES there: the hedge flips violently as spot approaches H. That barrier "
                "region is where a barrier book lives or dies."
            ),
            risk=(
                "Barrier / gap risk: a jump through the barrier can leave you badly mis-hedged. "
                "The closed form assumes continuous monitoring; real contracts monitor discretely, "
                "which is worth a continuity correction (the price sits between the discrete and "
                "continuous values)."
            ),
        ),
        "autocall": ExoticDoc(
            kind="autocall",
            title="Autocallable (Phoenix)",
            what=(
                "A yield product: it pays periodic CONDITIONAL coupons and redeems early "
                "(autocalls) at par if the underlying is above the autocall barrier on an "
                "observation date. If it survives to maturity you are long the downside below a "
                "protection barrier."
            ),
            behaviour=(
                "Path-dependent — the cashflows depend on the whole observation path, not just the "
                "final spot — so it is priced by Monte Carlo. The early-redemption probability and "
                "the EXPECTED LIFE matter as much as the price; the yield comes from an embedded "
                "short down-and-in put."
            ),
            risk=(
                "You are effectively short a put: a sell-off below the protection barrier turns "
                "the coupon stream into a capital loss (par·S/S0). The greeks shift as spot "
                "approaches the autocall and coupon barriers — discontinuously around the autocall "
                "level."
            ),
        ),
        "varswap": ExoticDoc(
            kind="varswap",
            title="Variance swap",
            what=(
                "Pays realised variance minus a fixed strike (the fair variance) — PURE exposure "
                "to realised volatility, with constant vega in variance terms and no "
                "path-dependent delta to manage."
            ),
            behaviour=(
                "Its fair variance is model-free: replicate the log contract with a STATIC strip "
                "of OTM options weighted 1/K². The 1/K² weighting overweights low-strike puts, so "
                "with equity skew the fair vol prints ABOVE the ATM vol. VIX² is essentially the "
                "fair variance of a 30-day S&P variance swap."
            ),
            risk=(
                "You own the whole smile: a jump or a spike in realised vol is your P&L. The "
                "replication needs a continuum of strikes, so wing liquidity and strike truncation "
                "cause real-world tracking error (and make a true var swap behave differently from "
                "a vol swap in a crash)."
            ),
        ),
    }
)
"""The education card of every exotic. Read-only."""

# ------------------------------------------------------------------ prose from the markup

ExoticDocField = Literal["what", "behaviour", "risk"]
"""The prose fields of an :class:`ExoticDoc`, in the order the card shows them."""

EXOTIC_DOC_FIELD_LABELS: Final[Mapping[ExoticDocField, str]] = MappingProxyType(
    {
        # web/src/components/ExoticInfo.tsx:34-39 (the <dt> headings of the card)
        "what": "What it is",
        "behaviour": "Behaviour",
        "risk": "Principal risk",
    }
)
"""Heading shown above each prose field of the exotic card, in display order."""

# web/src/components/ExoticInfo.tsx:60-63
EXOTIC_GREEK_DOC_FIELDS: Final[tuple[GreekDocField, ...]] = ("measures", "intuition")
"""The fields of the selected metric's greek card shown beside an exotic (a shorter card
than the greeks lab's: definition and intuition only). The variance swap shows no greek
card at all (VarSwapView.tsx:133)."""

EXOTIC_TAB_LABELS: Final[Mapping[ExoticKind, str]] = MappingProxyType(
    {
        # web/src/components/ExoticsLab.tsx:13-18 (tab order; the barrier is the default)
        "barrier": "Barrier",
        "digital": "Digital",
        "autocall": "Autocallable",
        "varswap": "Variance swap",
    }
)
"""Sub-tab label of each exotic, in tab order."""

# web/src/components/exotics/BarrierView.tsx:160-163
BARRIER_CHART_CAPTION: Final = (
    "Red dashed = barrier H, dotted = strike K, accent = current spot. Watch gamma spike as "
    "spot nears the barrier — that is where a knock-out hedge is hardest."
)
"""Caption under the barrier's metric-vs-spot chart."""

# Streamlit-UI addition (the React view picks one of four kinds; this UI splits the kind
# into a direction and a knock, which also shows the in/out pairing).
BARRIER_DIRECTION_HINT: Final = (
    "Down: the barrier sits below spot. Up: it sits above spot. Switching side mirrors H to "
    "about the same distance on the other side of spot, so the option does not start out "
    "already knocked in or out."
)
"""Tooltip of the barrier's direction control (Down / Up)."""

# Streamlit-UI addition (see BARRIER_DIRECTION_HINT).
BARRIER_KNOCK_HINT: Final = (
    "Out: the option dies the moment spot touches H. In: it only comes alive if spot "
    "touches H. Same barrier, same strike: knock-in + knock-out = the vanilla."
)
"""Tooltip of the barrier's knock control (Out / In)."""

# Streamlit-UI addition (no React counterpart: the React view shows the zero premium bare).
BARRIER_BREACHED_NOTES: Final[Mapping[Literal["down-out", "down-in", "up-out", "up-in"], str]] = (
    MappingProxyType(
        {
            "down-out": (
                "Spot is at or below the barrier, so this down-and-out has already knocked "
                "out: it is worth nothing and every greek is zero. Move H below spot to bring "
                "it back to life."
            ),
            "down-in": (
                "Spot is at or below the barrier, so this down-and-in has already knocked in: "
                "it is simply the vanilla now. Move H below spot to see the barrier matter."
            ),
            "up-out": (
                "Spot is at or above the barrier, so this up-and-out has already knocked out: "
                "it is worth nothing and every greek is zero. Move H above spot to bring it "
                "back to life."
            ),
            "up-in": (
                "Spot is at or above the barrier, so this up-and-in has already knocked in: it "
                "is simply the vanilla now. Move H above spot to see the barrier matter."
            ),
        }
    )
)
"""Shown beside the barrier chart when spot is already at or beyond the barrier (the
engine's breached case): why the knock-out reads zero, or the knock-in the vanilla."""

# Streamlit-UI addition (no React counterpart).
BARRIER_STRIKE_BEYOND_NOTES: Final[Mapping[Literal["out", "in"], str]] = MappingProxyType(
    {
        "out": (
            "The strike is beyond the barrier: to finish in the money, spot must first cross "
            "H, which kills the option. This knock-out can never pay, so it is worth nothing "
            "and every greek is zero. Put K on spot's side of H."
        ),
        "in": (
            "The strike is beyond the barrier: to finish in the money, spot must first cross "
            "H, which switches the option on. This knock-in is the whole vanilla. Put K on "
            "spot's side of H to see the barrier matter."
        ),
    }
)
"""Shown beside the barrier chart when the strike lies beyond the barrier (an up call
struck at or above H, a down put struck at or below it): the knock-out is structurally
worthless and the knock-in is the vanilla, by knock."""

# web/src/components/exotics/DigitalView.tsx:157
DIGITAL_PRICE_CAPTION: Final = (
    "Blue: the digital. Orange: the replicating call spread of width Δ — shrink Δ (or T) "
    "and it converges to the digital step. The (Q/Δ) size needed is the un-hedgeable bit."
)
"""Caption under the digital's value-vs-spot chart (digital vs its call-spread
replication)."""

# web/src/components/exotics/DigitalView.tsx:158
DIGITAL_GREEK_CAPTION: Final = (
    "The delta/gamma spike at the strike sharpens as T → 0 — the digital cannot be hedged "
    "exactly at expiry."
)
"""Caption under the digital's chart when a greek (not the price) is selected."""

# Streamlit-UI addition (no React counterpart: the React digital is cash-or-nothing only).
DIGITAL_PAYOUT_HINT: Final = (
    "Cash-or-nothing pays a fixed amount Q if the option finishes in the money. "
    "Asset-or-nothing pays the index itself, S_T."
)
"""Tooltip of the digital's payout control (Cash / Asset), naming both payouts in full."""

# Streamlit-UI addition (no React counterpart: the React digital is cash-or-nothing only).
DIGITAL_ASSET_PRICE_CAPTIONS: Final[Mapping[Literal["call", "put"], str]] = MappingProxyType(
    {
        "call": (
            "Blue: asset-or-nothing. Orange: a vanilla call + (K/Δ) call spreads — AoN = "
            "vanilla + K × cash digital, so it inherits the digital's pin risk, K times over."
        ),
        "put": (
            "Blue: asset-or-nothing. Orange: (K/Δ) put spreads − a vanilla put — AoN = "
            "K × cash digital − vanilla, so it inherits the digital's pin risk, K times over."
        ),
    }
)
"""Caption under the digital's value-vs-spot chart for an ASSET-or-nothing payout (the
counterpart of :data:`DIGITAL_PRICE_CAPTION`), by option type: the asset-or-nothing
(blue) against its replication (orange), and why it is as hard to hedge at the strike as
the cash digital."""

# web/src/components/exotics/AutocallView.tsx:162-166
AUTOCALL_PATHS_CAPTION: Final = (
    "Each path either crosses the autocall line on an observation date (early redemption at "
    "par) or runs to maturity — where finishing below the protection line means a capital "
    "loss. The payoff depends on the whole path, so the note is priced by Monte Carlo."
)
"""Caption under the autocallable's sample-paths-and-barriers chart."""

# web/src/components/exotics/AutocallView.tsx:95
AUTOCALL_MEMORY_HINT: Final = "Memory (snowball) coupon"
"""Hint for the memory toggle: missed coupons are paid later if the coupon barrier is
met again."""

# Streamlit-UI addition (the React Learn panel offers a gamma chip the view never fills).
AUTOCALL_GAMMA_NOTE: Final = (
    "No gamma here: a Monte-Carlo gamma is the second difference of three noisy prices, too "
    "noisy to report even with common random numbers."
)
"""Shown under the autocallable's price & greek chips, which leave gamma out."""


@dataclass(frozen=True, slots=True)
class ReadoutNote:
    """A readout row's label and the short note (unit / definition) printed beside it."""

    label: str
    note: str


AUTOCALL_DIAGNOSTICS: Final[tuple[ReadoutNote, ...]] = (
    # web/src/components/exotics/AutocallView.tsx:124-126
    ReadoutNote("P(autocall)", "early redeem"),
    ReadoutNote("P(capital loss)", "at maturity"),
    ReadoutNote("Expected life", "years"),
)
"""The autocallable's Monte-Carlo diagnostics, shown above its greeks: they matter as much
as the price."""

# web/src/components/exotics/VarSwapView.tsx:78-79
VARSWAP_FAIR_VOL_NOTE: Final = ReadoutNote("fair volatility", "√(fair variance)")
"""The variance swap's hero number: the fair vol, quoted as the square root of the fair
variance (VIX-style)."""

VARSWAP_READOUT: Final[tuple[ReadoutNote, ...]] = (
    # web/src/components/exotics/VarSwapView.tsx:84-86
    ReadoutNote("Fair variance", "annualised"),
    ReadoutNote("ATM vol", "at forward"),
    ReadoutNote("Convexity premium", "fair − ATM"),
)
"""The variance swap's readout rows (the forward row, in the snapshot currency, follows)."""

# web/src/components/exotics/VarSwapView.tsx:64-67
VARSWAP_SKEW_HINT: Final = (
    "Steepen the skew (more negative slope) and watch the fair vol pull above ATM — the "
    "replication overweights the now-richer downside puts."
)
"""Instruction under the variance swap's smile controls."""

# Streamlit-UI addition (the React views have no Reset).
RESET_VIEW_HINT: Final = "Restore the opening inputs"
"""Tooltip of each exotic view's Reset button: every input back to the view's seed."""

# Streamlit-UI addition (no React counterpart: the React variance swap has no skew switch).
VARSWAP_SKEW_SWITCH_HINT: Final = "Off: a flat smile at the ATM vol (slope and curvature ignored)."
"""Hint for the variance swap's skew on/off switch: off prices the strip on a flat smile,
so the fair vol falls to (about) the ATM vol; switching it back on shows what the skew adds."""

# web/src/components/exotics/VarSwapView.tsx:110-113
VARSWAP_STRIP_CAPTION: Final = (
    "Each OTM option's 1/K²-weighted contribution to fair variance. Puts (below F) carry "
    "more weight — the source of the convexity premium."
)
"""Caption under the variance swap's replication-strip chart."""


__all__ = [
    "AUTOCALL_DIAGNOSTICS",
    "AUTOCALL_GAMMA_NOTE",
    "AUTOCALL_MEMORY_HINT",
    "AUTOCALL_PATHS_CAPTION",
    "BARRIER_BREACHED_NOTES",
    "BARRIER_CHART_CAPTION",
    "BARRIER_DIRECTION_HINT",
    "BARRIER_KNOCK_HINT",
    "BARRIER_STRIKE_BEYOND_NOTES",
    "DIGITAL_ASSET_PRICE_CAPTIONS",
    "DIGITAL_GREEK_CAPTION",
    "DIGITAL_PAYOUT_HINT",
    "DIGITAL_PRICE_CAPTION",
    "EXOTIC_DOCS",
    "EXOTIC_DOC_FIELD_LABELS",
    "EXOTIC_GREEK_DOC_FIELDS",
    "EXOTIC_KINDS",
    "EXOTIC_METRICS",
    "EXOTIC_TAB_LABELS",
    "RESET_VIEW_HINT",
    "VARSWAP_FAIR_VOL_NOTE",
    "VARSWAP_READOUT",
    "VARSWAP_SKEW_HINT",
    "VARSWAP_SKEW_SWITCH_HINT",
    "VARSWAP_STRIP_CAPTION",
    "ExoticDoc",
    "ExoticDocField",
    "ExoticKind",
    "ExoticMetric",
    "ReadoutNote",
]
