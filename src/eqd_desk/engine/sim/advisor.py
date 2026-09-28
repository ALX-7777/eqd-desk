"""Desk advisor: reads the live book and the market and returns ranked, explained hedging
advice.

Each actionable item carries a concrete HEDGE PLAN: the exact instrument, side and
quantity to trade, and why that instrument is the right tool (future for delta, ATM for
vega, short-dated ATM for gamma). Pure and deterministic, so it is unit-tested.

The advice text is part of the teaching content and is kept VERBATIM identical to the
TypeScript engine (``web/src/engine/sim/advisor.ts``), including how numbers are printed:
the small ``_js_*`` helpers below reproduce JavaScript's ``Math.round``,
``Number.prototype.toFixed`` and ``toLocaleString('en-US')`` exactly (Python's ``round``
and ``format`` round ties to even and print ``-0`` differently).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal

from eqd_desk.engine.greeks import raw_greeks
from eqd_desk.engine.sim.book import Book, book_greeks, book_greeks_raw
from eqd_desk.engine.sim.market import MarketState, vol_for_strike
from eqd_desk.engine.sim.rfq import RFQ
from eqd_desk.engine.types import BsmInputs, OptionType, RawGreeks

AdviceAction = Literal["flatten-delta", "flatten-vega", "flatten-gamma"] | None
"""The one-click hedge an advice item maps to (``None`` = informational only)."""

Severity = Literal["high", "medium", "low", "ok"]
"""How urgent an advice item is (advice is sorted high → ok)."""

Instrument = Literal["future", "option"]
"""Hedge instrument: the delta-1 index future, or a listed option."""

TradeSide = Literal["buy", "sell"]
"""Direction of a suggested hedge trade."""

RiskVerdict = Literal["hedges", "adds", "neutral"]
"""Whether winning an RFQ reduces, increases, or barely touches your dominant risk."""


@dataclass(frozen=True, slots=True)
class HedgePlan:
    """A concrete trade that flattens the greek the advice is about."""

    instrument: Instrument
    """``"future"`` for delta, ``"option"`` for vega / gamma."""
    side: TradeSide
    """Buy or sell."""
    quantity: float
    """Suggested quantity (contracts / future units); round before trading."""
    rationale: str
    """Plain-language "what to do and why"."""
    option_type: OptionType | None = None
    """Option flavour (options only)."""
    K: float | None = None
    """Strike (options only): spot rounded to the strike grid (ATM)."""
    tenor_days: int | None = None
    """Tenor in calendar days (options only)."""


@dataclass(frozen=True, slots=True)
class Advice:
    """One ranked advice item."""

    severity: Severity
    title: str
    detail: str
    action: AdviceAction
    plan: HedgePlan | None = None
    """The concrete hedge to apply (load into the ticket), if any."""


_RANK: Final = {"high": 0, "medium": 1, "low": 2, "ok": 3}
"""Sort order of the severities."""


# --- JavaScript-compatible number formatting (keeps the text identical to the TS app) ---


def _js_round(x: float) -> float:
    """JavaScript ``Math.round``: nearest integer, ties toward +∞ (2.5 → 3, −2.5 → −2),
    and −0 for x in [−0.5, 0) (which ``toLocaleString`` then prints as "-0")."""
    if not math.isfinite(x):
        return x
    if -0.5 <= x < 0 or (x == 0 and math.copysign(1.0, x) < 0):
        return -0.0
    f = math.floor(x)
    return float(f + 1 if x - f >= 0.5 else f)


def _money(x: float) -> str:
    """JS ``Math.round(x).toLocaleString('en-US')``: a rounded integer with thousands
    separators (``-1,235``; ``-0`` for tiny negatives)."""
    v = _js_round(x)
    if math.isnan(v):
        return "NaN"
    if math.isinf(v):
        return "∞" if v > 0 else "-∞"
    if v == 0:
        return "-0" if math.copysign(1.0, v) < 0 else "0"
    return f"{int(v):,}"


def _to_fixed(x: float, digits: int) -> str:
    """JS ``x.toFixed(digits)``: round the EXACT binary value to ``digits`` decimals, ties
    away from zero; negative numbers keep their "-" even when they round to zero
    (``(-0.04).toFixed(1) = "-0.0"``) but −0 itself prints as "0.0"."""
    if math.isnan(x):
        return "NaN"
    if x < 0:
        return "-" + _to_fixed(-x, digits)
    if x >= 1e21:
        return "Infinity" if math.isinf(x) else _js_str(x)
    q = Decimal(abs(x)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return format(q, "f")


def _js_str(x: float) -> str:
    """JS ``String(x)`` for the values printed here (integral strikes print without
    ``.0``)."""
    if math.isfinite(x) and x == math.floor(x) and abs(x) < 1e21:
        return str(int(x))
    return repr(x)


def _pct(x: float) -> str:
    """A decimal as a percentage with one decimal: 0.1234 → ``"12.3%"``."""
    return f"{_to_fixed(x * 100, 1)}%"


def _sign(x: float) -> int:
    """``Math.sign`` for comparisons: −1, 0 or +1 (−0 counts as 0)."""
    return (x > 0) - (x < 0)


def _atm_strike(market: MarketState, strike_step: float) -> float:
    """Spot rounded to the strike grid (JS ``Math.round(spot / step) * step``); a
    non-positive step falls back to 1."""
    step = strike_step if strike_step > 0 else 1
    return _js_round(market.spot / step) * step


def _atm_call_greeks(market: MarketState, atm_k: float, tenor_years: float) -> RawGreeks:
    """Per-contract greeks (raw units) of an ATM call hedge of the given tenor."""
    sigma = vol_for_strike(market, atm_k, tenor_years)
    inputs = BsmInputs(S=market.spot, K=atm_k, T=tenor_years, r=market.r, q=market.q, sigma=sigma)
    return raw_greeks(inputs, "call")


# --- RFQ risk impact ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RiskImpact:
    """How winning an RFQ (you take the opposite side) would move your net risk."""

    d_delta: float
    """Change in net raw delta if you win it."""
    d_vega: float
    """Change in net raw vega (per 1.00 of vol) if you win it."""
    d_gamma: float
    """Change in net raw gamma if you win it."""
    verdict: RiskVerdict
    """Whether winning it reduces, increases, or barely touches your dominant risk."""
    note: str
    """One-line note + lean guidance."""


def rfq_risk_impact(rfq: RFQ, book: Book, market: MarketState) -> RiskImpact:
    """The cheapest hedge is offsetting client flow.

    For a live RFQ, compute the greeks you'd pick up if you WON it, and judge whether that
    flattens your book (lean in to win it) or piles on (quote wide / pass). Vega "matters"
    above 50 raw (0.5 per vol point) and gamma above 1e-5; a trade counts only if it moves
    that greek by more than 8% of the book's net.
    """
    net = book_greeks_raw(book, market)
    d_delta = 0.0
    d_vega = 0.0
    d_gamma = 0.0
    for leg in rfq.legs:
        # your signed direction if you win (opposite of the client on each leg)
        your_sign = (-1 if rfq.client_side == "buy" else 1) * (1 if leg.side == "long" else -1)
        qty = your_sign * leg.ratio * rfq.size
        sigma = vol_for_strike(market, leg.K, leg.T)
        g = raw_greeks(
            BsmInputs(S=market.spot, K=leg.K, T=leg.T, r=market.r, q=market.q, sigma=sigma),
            leg.type,
        )
        d_delta += qty * g.delta
        d_vega += qty * g.vega
        d_gamma += qty * g.gamma

    vega_matters = abs(net.vega) > 50
    gamma_matters = abs(net.gamma) > 1e-5
    big_vega = abs(d_vega) > 0.08 * abs(net.vega)
    cuts_vega = vega_matters and _sign(d_vega) != _sign(net.vega) and big_vega
    adds_vega = vega_matters and _sign(d_vega) == _sign(net.vega) and big_vega
    cuts_gamma = (
        gamma_matters
        and _sign(d_gamma) != _sign(net.gamma)
        and abs(d_gamma) > 0.08 * abs(net.gamma)
    )

    win_side = "lower your ask" if rfq.client_side == "buy" else "raise your bid"
    vega_dir = "short" if net.vega < 0 else "long"
    verdict: RiskVerdict = "neutral"
    note = "Little impact on your book — price it for the edge."
    if cuts_vega:
        verdict = "hedges"
        note = (
            f"Cuts your {vega_dir} vega by ~{_money(abs(d_vega) / 100)}/pt — "
            f"lean in ({win_side}) to win it and get PAID to hedge."
        )
    elif cuts_gamma:
        verdict = "hedges"
        gamma_dir = "long" if net.gamma < 0 else "short"
        note = f"Brings {gamma_dir} gamma that offsets your book — lean in ({win_side}) to win it."
    elif adds_vega:
        verdict = "adds"
        note = (
            f"Adds to your {vega_dir} vega — quote it wide (defensive) "
            "or pass unless the edge is fat."
        )
    return RiskImpact(d_delta=d_delta, d_vega=d_vega, d_gamma=d_gamma, verdict=verdict, note=note)


# --- Book advice ---------------------------------------------------------------------------


def advise_book(
    book: Book,
    market: MarketState,
    realised_vol: float | None,
    strike_step: float = 1,
) -> list[Advice]:
    """Ranked advice for the book (most severe first; stable within a severity).

    Checks, in order:

    1. Directional risk: |Δ·S·1%| > $150 (high above $1,200). Plan: the FUTURE.
    2. Vol level: |vega| > $100 per vol point (high if short vega while implied < 13%).
       Plan: a ~60-day ATM call.
    3. Gamma vs realised-vs-implied (needs ``realised_vol``): short gamma while realised
       > implied is high; short gamma in a quiet tape medium; long gamma in a quiet tape
       low. Plan: a ~21-day ATM call.
    4. Theta context: |theta| > $40/day (informational).
    5. Hedging costs above half the captured edge.
    6. The axe: when vega or gamma is material, lean your quotes into offsetting flow.

    An empty list never comes back: a flat book gets one ``"ok"`` item.

    Args:
        book: the live book.
        market: the current market.
        realised_vol: annualised realised vol of the session so far (``None`` if too
            short to measure; the gamma check is then skipped).
        strike_step: listed strike grid (the ATM hedge strike is spot rounded to it).
    """
    greeks = book_greeks(book, market)
    reported, raw = greeks.reported, greeks.raw
    out: list[Advice] = []
    atm_k = _atm_strike(market, strike_step)
    atm_k_str = _js_str(atm_k)

    # 1) Directional risk — delta. Hedge with the future (cheapest, pure delta).
    per_1pct = reported.delta * market.spot * 0.01
    if abs(per_1pct) > 150:
        long_mkt = reported.delta > 0
        verb = "Sell" if long_mkt else "Buy"
        out.append(
            Advice(
                severity="high" if abs(per_1pct) > 1200 else "medium",
                title=f"Directional risk — net Δ {_to_fixed(reported.delta, 1)}",
                detail=(
                    f"You're {'long' if long_mkt else 'short'} the market: a 1% "
                    f"{'drop' if long_mkt else 'rally'} costs roughly "
                    f"${_money(abs(per_1pct))}. Delta is the cheapest greek to remove — "
                    "flatten it first, then look at your vol risk."
                ),
                action="flatten-delta",
                plan=HedgePlan(
                    instrument="future",
                    side="sell" if long_mkt else "buy",
                    quantity=abs(reported.delta),
                    rationale=(
                        "Use the index FUTURE, not options: it's delta-1 with no gamma, vega "
                        "or theta and the tightest spread, so it kills pure directional risk "
                        f"without adding new greeks. {verb} ≈ {_money(abs(reported.delta))} "
                        "future units to bring net Δ ≈ 0."
                    ),
                ),
            )
        )

    # 2) Vol level — vega. Hedge with an ATM option (most vega per lot).
    if abs(reported.vega) > 100:
        short_vega = reported.vega < 0
        low_vol = market.atm_vol < 0.13
        detail = (
            f"Vega {_to_fixed(reported.vega, 0)} → you {'lose' if short_vega else 'gain'} "
            f"about ${_money(abs(reported.vega))} per vol point. "
        )
        if short_vega and low_vol:
            detail += (
                f"Implied vol is low ({_pct(market.atm_vol)}); a sell-off would spike vol "
                "right when you're short it (leverage). Buy some vega back."
            )
        elif short_vega:
            detail += "You're short vol — fine while calm, painful on a spike."
        else:
            detail += "You're long vol — you profit if implied rises, bleed if it drifts lower."
        lg = _atm_call_greeks(market, atm_k, 60 / 365)
        n = abs(raw.vega / lg.vega) if lg.vega > 1e-9 else 0.0
        buy = short_vega
        signed_delta = (1 if buy else -1) * n * lg.delta
        vega_plan = (
            HedgePlan(
                instrument="option",
                option_type="call",
                K=atm_k,
                tenor_days=60,
                side="buy" if buy else "sell",
                quantity=n,
                rationale=(
                    "Vega is densest at-the-money, and a ~60-day ATM option is liquid and "
                    f"vega-rich (~${_to_fixed(lg.vega / 100, 1)}/vol-pt per lot). "
                    f"{'Buy' if buy else 'Sell'} ≈ {_money(n)} ATM {atm_k_str} "
                    f"call{'s' if n >= 2 else ''} to offset your "
                    f"{'short' if short_vega else 'long'} vega. Note it also brings some "
                    f"{'long' if buy else 'short'} gamma and about {_money(signed_delta)} "
                    "delta — clean that up with the future afterward."
                ),
            )
            if n > 0
            else None
        )
        out.append(
            Advice(
                severity="high" if short_vega and low_vol else "medium",
                title=f"Vol exposure — vega {_to_fixed(reported.vega, 0)}/pt",
                detail=detail,
                action="flatten-vega",
                plan=vega_plan,
            )
        )

    # 3) Gamma vs realised-vs-implied. Hedge with a SHORT-dated ATM option.
    if abs(raw.gamma) > 1e-7 and realised_vol is not None:
        short_gamma = raw.gamma < 0
        hotter = realised_vol > market.atm_vol
        lg = _atm_call_greeks(market, atm_k, 21 / 365)
        n = abs(raw.gamma / lg.gamma) if lg.gamma > 1e-12 else 0.0
        buy = short_gamma
        signed_vega = ((1 if buy else -1) * n * lg.vega) / 100
        signed_delta = (1 if buy else -1) * n * lg.delta
        gamma_plan = (
            HedgePlan(
                instrument="option",
                option_type="call",
                K=atm_k,
                tenor_days=21,
                side="buy" if buy else "sell",
                quantity=n,
                rationale=(
                    "Gamma concentrates in SHORT-dated at-the-money options, so a ~21-day "
                    "ATM option flattens gamma with the least vega baggage. "
                    f"{'Buy' if buy else 'Sell'} ≈ {_money(n)} ATM {atm_k_str} "
                    f"call{'s' if n >= 2 else ''}. It brings about ${_money(signed_vega)}"
                    f"/vol-pt of vega and ~{_money(signed_delta)} delta — re-hedge that "
                    "delta with the future."
                ),
            )
            if n > 0
            else None
        )
        rv, iv = _pct(realised_vol), _pct(market.atm_vol)

        if short_gamma and hotter:
            out.append(
                Advice(
                    severity="high",
                    title="Short gamma into a moving market",
                    detail=(
                        f"Realised vol ({rv}) is running ABOVE implied ({iv}) while you're "
                        "short gamma — your delta-hedged P&L ≈ ½·Γ·S²·(realised²−implied²) "
                        "is negative, so you bleed on every move. Buy gamma back, or widen "
                        "your re-hedge band and quote wider."
                    ),
                    action="flatten-gamma",
                    plan=gamma_plan,
                )
            )
        elif not short_gamma and not hotter:
            out.append(
                Advice(
                    severity="low",
                    title="Long gamma in a quiet tape",
                    detail=(
                        f"Realised ({rv}) is below implied ({iv}) and you're long gamma — "
                        "you're paying more theta than you scalp back. Accept it for the "
                        "convexity, or trim."
                    ),
                    action="flatten-gamma",
                    plan=gamma_plan,
                )
            )
        elif short_gamma:
            out.append(
                Advice(
                    severity="medium",
                    title="Short gamma — exposed to a jump",
                    detail=(
                        f"You're short gamma. It's quiet now (realised {rv} vs implied {iv}), "
                        "but a sudden move forces you to hedge into it at a loss. Keep size "
                        "modest or buy a little gamma back."
                    ),
                    action="flatten-gamma",
                    plan=gamma_plan,
                )
            )

    # 4) Theta context (no direct hedge — it's the consequence of gamma/vega).
    if abs(reported.theta) > 40:
        if reported.theta < 0:
            theta_detail = (
                f"You pay ${_money(abs(reported.theta))}/day in theta — the rent for being "
                "long gamma/vega. Worth it only if the market moves enough to scalp it back."
            )
        else:
            theta_detail = (
                f"You collect ${_money(reported.theta)}/day, but that usually means short "
                "gamma: one big move can erase many days of decay."
            )
        out.append(
            Advice(
                severity="low",
                title=f"Time decay {_to_fixed(reported.theta, 0)}/day",
                detail=theta_detail,
                action=None,
            )
        )

    # 5) Hedging costs eating the edge.
    if book.realized_edge > 0 and book.total_costs > 0.5 * book.realized_edge:
        out.append(
            Advice(
                severity="medium",
                title="Hedging is eating your edge",
                detail=(
                    f"You've paid ${_money(book.total_costs)} in hedge costs against "
                    f"${_money(book.realized_edge)} of captured edge. Every option hedge "
                    "crosses the spread — prefer the cheaper future for delta and don't "
                    "over-trim small greeks."
                ),
                action=None,
            )
        )

    # 6) Axe via flow — the cheapest hedge of all is offsetting client flow.
    if abs(reported.vega) > 100 or abs(raw.gamma) > 1e-6:
        dominant_vol = abs(reported.vega) > 100
        short_vega = reported.vega < 0
        short_gamma = raw.gamma < 0
        if dominant_vol:
            what = (
                "a client SELLING you vol (a straddle / strangle / option you buy)"
                if short_vega
                else "a client BUYING vol from you"
            )
            lean = (
                "lean your prices UP to win client SELLS"
                if short_vega
                else "lean DOWN to win client BUYS"
            )
        else:
            what = (
                "a client selling you short-dated options (you go long gamma)"
                if short_gamma
                else "a client buying short-dated options from you"
            )
            lean = "lean toward the side that lengthens your gamma"
        out.append(
            Advice(
                severity="low",
                title="Cheapest hedge: axe your quotes to the flow you want",
                detail=(
                    "Paying up in the market costs the spread every time. The cheapest hedge "
                    "is the next client trade that offsets you — you cut risk AND get PAID "
                    "the edge (a negative-cost hedge) instead of paying it. "
                    f"Wait for {what}, and {lean}. Each live RFQ in your queue is tagged ↓ "
                    "(helps) or ↑ (hurts) so you can lean into the right flow."
                ),
                action=None,
            )
        )

    if len(out) == 0:
        out.append(
            Advice(
                severity="ok",
                title="Book looks balanced",
                detail=(
                    "Net greeks are small — no pressing risk. Keep quoting two-way and "
                    "capturing edge; re-check after a few fills or a market move."
                ),
                action=None,
            )
        )

    # sorted() is stable, like JS Array.prototype.sort: equal severities keep their order.
    return sorted(out, key=lambda a: _RANK[a.severity])


# --- Joint (delta + gamma + vega) hedge ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class JointLeg:
    """One leg of a combined hedge."""

    instrument: Instrument
    side: TradeSide
    quantity: float
    """Unsigned quantity (contracts / future units); ``side`` carries the direction."""
    option_type: OptionType | None = None
    K: float | None = None
    tenor_days: int | None = None


@dataclass(frozen=True, slots=True)
class JointHedge:
    """A combined hedge (two ATM options + the future), or ``feasible=False``."""

    feasible: bool
    legs: tuple[JointLeg, ...]
    """21-day ATM call, 180-day ATM call, then the future (in that order)."""
    rationale: str


def joint_hedge(book: Book, market: MarketState, strike_step: float = 1) -> JointHedge:
    """A combined hedge that flattens DELTA, GAMMA and VEGA together, instead of one greek
    at a time.

    Because an option moves all three at once, hedging greek-by-greek chases its tail. We
    solve the 2×2 system for the quantities of a SHORT-dated (21-day) ATM call (gamma-rich)
    and a LONG-dated (180-day) ATM call (vega-rich) that zero gamma and vega
    simultaneously::

        [g1.γ  g2.γ] [n1]   [−net.γ]
        [g1.ν  g2.ν] [n2] = [−net.ν]

    then add the FUTURE (the only clean single-greek tool) to mop up the residual delta,
    nf = −(net.Δ + n1·g1.Δ + n2·g2.Δ), so the future always goes LAST. Infeasible (no legs)
    when the system is singular (|det| < 1e-14 or not finite).
    """
    net = book_greeks_raw(book, market)
    atm_k = _atm_strike(market, strike_step)
    g1 = _atm_call_greeks(market, atm_k, 21 / 365)  # gamma-rich
    g2 = _atm_call_greeks(market, atm_k, 180 / 365)  # vega-rich
    det = g1.gamma * g2.vega - g2.gamma * g1.vega
    if not math.isfinite(det) or abs(det) < 1e-14:
        return JointHedge(feasible=False, legs=(), rationale="")

    # Solve [g1.γ g2.γ; g1.ν g2.ν]·[n1; n2] = [−net.γ; −net.ν] (Cramer's rule)
    n1 = (-net.gamma * g2.vega + net.vega * g2.gamma) / det
    n2 = (-net.vega * g1.gamma + net.gamma * g1.vega) / det
    nf = -(net.delta + n1 * g1.delta + n2 * g2.delta)  # residual delta → future

    def side(x: float) -> TradeSide:
        return "buy" if x >= 0 else "sell"

    legs = (
        JointLeg(
            instrument="option",
            option_type="call",
            K=atm_k,
            tenor_days=21,
            side=side(n1),
            quantity=abs(n1),
        ),
        JointLeg(
            instrument="option",
            option_type="call",
            K=atm_k,
            tenor_days=180,
            side=side(n2),
            quantity=abs(n2),
        ),
        JointLeg(instrument="future", side=side(nf), quantity=abs(nf)),
    )
    k = _js_str(atm_k)
    rationale = (
        "Hedges interact — one option moves delta, gamma AND vega at once, so flattening "
        "greeks one at a time chases your tail. Solve them together: a SHORT-dated ATM "
        "(gamma-rich) and a LONG-dated ATM (vega-rich) zero your gamma and vega at the same "
        "time, then the FUTURE mops up the leftover delta and adds nothing else, so it goes "
        f"last. Suggested: {side(n1)} {_money(abs(n1))} × 21d ATM {k}, "
        f"{side(n2)} {_money(abs(n2))} × 180d ATM {k}, "
        f"then {side(nf)} {_money(abs(nf))} × future."
    )
    return JointHedge(feasible=True, legs=legs, rationale=rationale)


__all__ = [
    "Advice",
    "AdviceAction",
    "HedgePlan",
    "Instrument",
    "JointHedge",
    "JointLeg",
    "RiskImpact",
    "RiskVerdict",
    "Severity",
    "TradeSide",
    "advise_book",
    "joint_hedge",
    "rfq_risk_impact",
]
