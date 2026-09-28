"""Strategy / position engine (Phase 2).

A position is a list of vanilla legs; everything here just COMPOSES the Phase-1 pricer and
greeks. Aggregate value and greeks are the signed-quantity-weighted sum of the per-leg
values, which keeps the position math trivially correct (and FD-validated at the position
level in ``tests/engine/test_strategy.py``).

Shared market params (S, r, q) live on the position; each leg carries its own strike,
expiry and vol (seeded from the surface so skew/term-structure are baked in). Multi-expiry
structures (calendars) are supported: payoff is evaluated at the FRONT expiry, valuing
not-yet-expired legs with their remaining maturity.

Example::

    from eqd_desk.engine.strategy import Leg, MarketParams, analyze_position

    legs = [
        Leg(id="a", type="call", side="long", quantity=1, K=100, T=0.25, sigma=0.2),
        Leg(id="b", type="call", side="short", quantity=1, K=105, T=0.25, sigma=0.19),
    ]
    a = analyze_position(legs, MarketParams(S=100, r=0.04, q=0.01))
    a.price  # net debit of the bull call spread
    a.reported.vega  # net vega per 1 vol point
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from eqd_desk.engine.bsm import price
from eqd_desk.engine.greeks import raw_greeks
from eqd_desk.engine.reporting import to_reported
from eqd_desk.engine.types import (
    GREEK_NAMES,
    BsmInputs,
    OptionType,
    RawGreeks,
    ReportedGreeks,
)

LegSide = Literal["long", "short"]
"""Direction of a leg: bought (``long``) or sold (``short``)."""

LEG_SIDES: tuple[LegSide, ...] = ("long", "short")

EXPIRED_EPS = 1e-9
"""A leg whose remaining maturity is at or below this many YEARS (~0.03 s) is treated as
expired by :func:`leg_value_at` and contributes its intrinsic value."""


@dataclass(frozen=True, slots=True)
class Leg:
    """One vanilla leg of a structure.

    Frozen, so an edit is ``dataclasses.replace(leg, sigma=leg.sigma + 0.01)``.
    """

    id: str
    """Identifier, unique within a position (e.g. ``"butterfly-1"``)."""
    type: OptionType
    """``"call"`` or ``"put"``."""
    side: LegSide
    """``"long"`` or ``"short"``."""
    quantity: float
    """Number of contracts (positive); sign comes from ``side``."""
    K: float
    """Strike (price level, same currency as spot)."""
    T: float
    """Time to expiry in years."""
    sigma: float
    """Implied vol for this leg (decimal), typically seeded from the surface."""


@dataclass(frozen=True, slots=True)
class MarketParams:
    """Market parameters shared by every leg of a position."""

    S: float
    """Spot price of the underlying."""
    r: float
    """Continuously-compounded risk-free rate (decimal)."""
    q: float
    """Continuously-compounded dividend yield (decimal)."""


@dataclass(frozen=True, slots=True)
class LegAnalysis:
    """Per-leg breakdown returned alongside the aggregate."""

    leg: Leg
    inputs: BsmInputs
    """The BSM inputs this leg was priced with (shared S, r, q + the leg's K, T, σ)."""
    signed_qty: float
    """Signed quantity = +qty (long) / −qty (short)."""
    unit: RawGreeks
    """Per-unit (single-contract) price + greeks, raw units."""


@dataclass(frozen=True, slots=True)
class PositionAnalysis:
    """Aggregate analysis of a whole position."""

    price: float
    """Net premium (signed: positive = the structure costs you / is a debit)."""
    raw: RawGreeks
    """Aggregate price + greeks in raw mathematical units."""
    reported: ReportedGreeks
    """Aggregate price + greeks in desk reporting units (vega per vol point, theta per
    day, ...; see :mod:`eqd_desk.engine.reporting`)."""
    legs: tuple[LegAnalysis, ...]
    """Per-leg breakdown, in the order the legs were given."""


GREEK_FIELDS: tuple[str, ...] = ("price", *GREEK_NAMES)
"""Every field of :class:`~eqd_desk.engine.types.Greeks` that aggregates across legs
(the price and all ten greeks)."""


def signed_qty(leg: Leg) -> float:
    """Signed quantity of a leg (+ long, − short)."""
    return (1 if leg.side == "long" else -1) * leg.quantity


def leg_inputs(leg: Leg, m: MarketParams) -> BsmInputs:
    """BSM inputs for a leg under the shared market params."""
    return BsmInputs(S=m.S, K=leg.K, T=leg.T, r=m.r, q=m.q, sigma=leg.sigma)


def analyze_position(legs: Sequence[Leg], m: MarketParams) -> PositionAnalysis:
    """Aggregate price + greeks for a position: Σ signedQty · (per-unit greek).

    Greeks at different expiries sum directly: they are all sensitivities with respect to
    the same underlying S, r, q.

    An empty position analyses to all zeros.
    """
    agg = dict.fromkeys(GREEK_FIELDS, 0.0)
    leg_analyses: list[LegAnalysis] = []
    for leg in legs:
        inputs = leg_inputs(leg, m)
        unit = raw_greeks(inputs, leg.type)
        k = signed_qty(leg)
        for f in GREEK_FIELDS:
            agg[f] += k * getattr(unit, f)
        leg_analyses.append(LegAnalysis(leg=leg, inputs=inputs, signed_qty=k, unit=unit))
    raw = RawGreeks(**agg)
    return PositionAnalysis(
        price=raw.price, raw=raw, reported=to_reported(raw), legs=tuple(leg_analyses)
    )


def front_expiry(legs: Sequence[Leg]) -> float:
    """The earliest expiry among the legs (the "front" expiry), in years. 0 for an empty
    list."""
    if len(legs) == 0:
        return 0.0
    return min(leg.T for leg in legs)


def _intrinsic(option_type: OptionType, K: float, S: float) -> float:
    """Intrinsic value of a single option at terminal spot: max(S − K, 0) for a call,
    max(K − S, 0) for a put."""
    return max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)


def leg_value_at(leg: Leg, S: float, at_t: float, m: MarketParams) -> float:
    """Value of one leg at terminal spot ``S`` evaluated at calendar time ``at_t`` (years
    from now).

    Legs that have expired by ``at_t`` contribute intrinsic value; legs still alive are
    priced with their remaining maturity. Signed by side/quantity. The market's own spot
    ``m.S`` is ignored (``S`` replaces it); only ``m.r`` and ``m.q`` are used.
    """
    remaining = leg.T - at_t
    k = signed_qty(leg)
    if remaining <= EXPIRED_EPS:
        return k * _intrinsic(leg.type, leg.K, S)
    v = price(BsmInputs(S=S, K=leg.K, T=remaining, r=m.r, q=m.q, sigma=leg.sigma), leg.type)
    return k * v


def position_value_at(legs: Sequence[Leg], S: float, at_t: float, m: MarketParams) -> float:
    """Position value at terminal spot ``S``, evaluated at calendar time ``at_t`` (years)."""
    v = 0.0
    for leg in legs:
        v += leg_value_at(leg, S, at_t, m)
    return v


def position_premium(legs: Sequence[Leg], m: MarketParams) -> float:
    """Net premium of the position at the current market (debit positive)."""
    return position_value_at(legs, m.S, 0.0, m)


@dataclass(frozen=True, slots=True)
class PayoffPoint:
    """One sample of the P&L profile vs terminal spot."""

    S: float
    """Terminal spot."""
    expiry_pnl: float
    """Profit/loss at the front expiry: value-at-front-expiry − net premium paid now."""
    now_pnl: float
    """Profit/loss "now" (mark-to-market vs spot, today): value-now − net premium."""


def payoff_profile(
    legs: Sequence[Leg],
    m: MarketParams,
    s_lo: float,
    s_hi: float,
    n: int = 120,
) -> list[PayoffPoint]:
    """Sample the P&L profile vs terminal spot on ``n + 1`` evenly spaced points of
    ``[s_lo, s_hi]``.

    ``expiry_pnl`` is the classic payoff diagram (evaluated at the front expiry so
    calendars render correctly); ``now_pnl`` is the smooth current mark-to-market. Both are
    net of the premium paid today, so they cross zero at the break-evens.

    Raises:
        ValueError: if ``n < 1`` (the grid step (s_hi − s_lo)/n would be undefined).
    """
    if n < 1:
        raise ValueError(f"payoff_profile: need n >= 1 sample intervals (got {n})")
    premium = position_premium(legs, m)
    at_t = front_expiry(legs)
    pts: list[PayoffPoint] = []
    for i in range(n + 1):
        S = s_lo + ((s_hi - s_lo) * i) / n
        pts.append(
            PayoffPoint(
                S=S,
                expiry_pnl=position_value_at(legs, S, at_t, m) - premium,
                now_pnl=position_value_at(legs, S, 0.0, m) - premium,
            )
        )
    return pts


__all__ = [
    "EXPIRED_EPS",
    "GREEK_FIELDS",
    "LEG_SIDES",
    "Leg",
    "LegAnalysis",
    "LegSide",
    "MarketParams",
    "PayoffPoint",
    "PositionAnalysis",
    "analyze_position",
    "front_expiry",
    "leg_inputs",
    "leg_value_at",
    "payoff_profile",
    "position_premium",
    "position_value_at",
    "signed_qty",
]
