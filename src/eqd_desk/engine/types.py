"""Shared types for the pricing/greeks engine.

The engine is pure: every function is a documented mathematical map from
:class:`BsmInputs` to numbers. No UI, no I/O, no global state.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Literal

OptionType = Literal["call", "put"]
"""Vanilla European option flavour."""

OPTION_TYPES: tuple[OptionType, ...] = ("call", "put")


@dataclass(frozen=True, slots=True)
class BsmInputs:
    """Inputs to Black–Scholes–Merton with a continuous dividend yield.

    Units:
      - ``S``, ``K``  : price level (same currency as the option premium).
      - ``T``         : time to expiry as a YEAR FRACTION (e.g. 0.25 = 3 months).
      - ``r``, ``q``  : continuously-compounded rate / dividend yield, as decimals (0.05 = 5%).
      - ``sigma``     : volatility as a decimal (0.20 = 20% annualised).

    Frozen, so a bump is ``dataclasses.replace(inputs, S=inputs.S + h)``.
    """

    S: float
    """Spot price of the underlying (> 0)."""
    K: float
    """Strike (> 0)."""
    T: float
    """Time to expiry in years (>= 0)."""
    r: float
    """Continuously-compounded risk-free rate (decimal)."""
    q: float
    """Continuously-compounded dividend yield (decimal)."""
    sigma: float
    """Volatility (decimal, >= 0)."""


@dataclass(frozen=True, slots=True)
class Greeks:
    """Price plus every greek, in ONE unit convention (raw or reported).

    RAW units are the exact partial derivatives of the BSM price, before any reporting
    convention is applied. :mod:`eqd_desk.engine.reporting` is the single place that
    rescales them to desk units.

    Raw units (per the natural variable):
      - delta : ∂V/∂S            per $1 of spot
      - gamma : ∂²V/∂S²          per $1 of spot, of delta
      - vega  : ∂V/∂σ            per 1.00 of vol (i.e. per 100 vol points)
      - theta : ∂V/∂t = −∂V/∂T   per 1.0 YEAR of calendar time (time-decay sign)
      - rho   : ∂V/∂r            per 1.00 of rate
      - vanna : ∂Δ/∂σ = ∂vega/∂S per 1.00 of vol
      - volga : ∂vega/∂σ         per 1.00 of vol
      - charm : ∂Δ/∂t = −∂Δ/∂T   per 1.0 year (delta decay)
      - speed : ∂Γ/∂S            per $1 of spot
      - color : ∂Γ/∂t = −∂Γ/∂T   per 1.0 year (gamma decay)
    """

    price: float
    """Option premium (the price itself, carried alongside the greeks)."""
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    vanna: float
    volga: float
    charm: float
    speed: float
    color: float

    def as_dict(self) -> dict[str, float]:
        """Field name → value, in declaration order (price first)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}


RawGreeks = Greeks
"""Greeks in raw mathematical units (see :class:`Greeks`)."""

ReportedGreeks = Greeks
"""Greeks rescaled to desk reporting units (see :mod:`eqd_desk.engine.reporting`)."""

GREEK_NAMES: tuple[str, ...] = (
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
"""Every greek field of :class:`Greeks`, excluding ``price``, in display order."""


@dataclass(frozen=True, slots=True)
class OptionAnalysis:
    """A full analysis bundle: identical math, two unit conventions."""

    inputs: BsmInputs
    type: OptionType
    raw: RawGreeks
    reported: ReportedGreeks
