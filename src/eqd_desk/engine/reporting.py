"""Reporting layer: the ONLY place that converts raw mathematical greeks into conventional
desk units.

Keeping every scale factor here means the rest of the engine stays unit-pure and trivially
finite-difference testable, and the UI has one labelled source of truth for units.

Conventions (see ``docs/WORKLOG.md`` for the rationale of each)::

    vega  ÷100    per 1 vol point  (σ moves 0.01)
    rho   ÷100    per 1 rate point (r moves 0.01)
    theta ÷365    per calendar day
    vanna ÷100    Δdelta per 1 vol point
    volga ÷10000  change in the (per-vol-point) vega, per 1 vol point
    charm ÷365    delta decay per calendar day
    color ÷365    gamma decay per calendar day
    delta, gamma, speed, price: unchanged (already in natural desk units)
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from eqd_desk.engine.types import RawGreeks, ReportedGreeks


@dataclass(frozen=True, slots=True)
class GreekUnit:
    """Display metadata for one greek (for UI labels and education panels)."""

    label: str
    """Short display name."""
    unit: str
    """Human-readable reporting unit."""
    scale_note: str
    """How the raw partial maps to the reported number."""
    divisor: float
    """reported = raw / divisor."""


GREEK_UNITS: Final = MappingProxyType(
    {
        "price": GreekUnit("Price", "premium", "raw", 1.0),
        "delta": GreekUnit("Delta", "per $1 spot", "raw", 1.0),
        "gamma": GreekUnit("Gamma", "Δdelta per $1 spot", "raw", 1.0),
        "vega": GreekUnit("Vega", "per 1 vol pt", "÷100", 100.0),
        "theta": GreekUnit("Theta", "per day", "÷365", 365.0),
        "rho": GreekUnit("Rho", "per 1 rate pt", "÷100", 100.0),
        "vanna": GreekUnit("Vanna", "Δdelta per 1 vol pt", "÷100", 100.0),
        "volga": GreekUnit("Volga", "Δvega per 1 vol pt", "÷10000", 10_000.0),
        "charm": GreekUnit("Charm", "Δdelta per day", "÷365", 365.0),
        "speed": GreekUnit("Speed", "Δgamma per $1 spot", "raw", 1.0),
        "color": GreekUnit("Color", "Δgamma per day", "÷365", 365.0),
    }
)
"""Per-greek display metadata, keyed by the :class:`~eqd_desk.engine.types.Greeks` field
name. Read-only."""


def to_reported(raw: RawGreeks) -> ReportedGreeks:
    """Convert raw greeks to conventional desk-reported units."""
    return ReportedGreeks(
        price=raw.price,
        delta=raw.delta,
        gamma=raw.gamma,
        vega=raw.vega / 100.0,
        theta=raw.theta / 365.0,
        rho=raw.rho / 100.0,
        vanna=raw.vanna / 100.0,
        volga=raw.volga / 10_000.0,
        charm=raw.charm / 365.0,
        speed=raw.speed,
        color=raw.color / 365.0,
    )
