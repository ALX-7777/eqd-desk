"""Client RFQs (requests for quote).

A request can be a single vanilla or a multi-leg STRUCTURE (straddle / strangle /
risk-reversal / vertical), reusing the Phase-2 preset builder for the leg geometry.
``legs`` describe the package as the CLIENT would hold it if they BUY it; ``client_side``
says whether they buy or sell the package.

Example::

    from eqd_desk.engine.rng import Mulberry32
    from eqd_desk.engine.sim import generate_rfq

    rng = Mulberry32(0x2BAD)
    rfq = generate_rfq(spot=6312.45, strike_step=25, rng=rng, id=1)
    rfq.label, rfq.client_side, rfq.size, [(leg.type, leg.K) for leg in rfq.legs]
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from eqd_desk.engine.presets import PresetName, PresetParams, build_preset, round_to
from eqd_desk.engine.strategy import LegSide
from eqd_desk.engine.types import OptionType

ClientSide = Literal["buy", "sell"]
"""What the CLIENT does with the package: ``"buy"`` it from you or ``"sell"`` it to you."""

UniformFn = Callable[[], float]
"""A zero-argument uniform [0, 1) generator, e.g. ``Mulberry32(seed)``."""


@dataclass(frozen=True, slots=True)
class RfqLeg:
    """One leg of an RFQ package, as the client would hold it if they BUY the package."""

    type: OptionType
    """``"call"`` or ``"put"``."""
    side: LegSide
    """``"long"`` or ``"short"`` (for a client who BUYS the package)."""
    ratio: float
    """Per-package ratio (e.g. 2 for a butterfly body)."""
    K: float
    """Strike (price units)."""
    T: float
    """Time to expiry in years, from the moment the RFQ is quoted."""


@dataclass(frozen=True, slots=True)
class RFQ:
    """A client request for a two-way price on a package."""

    id: int
    """Unique id within a session."""
    label: str
    """Display label, e.g. ``"Call"``, ``"Risk reversal"``."""
    legs: tuple[RfqLeg, ...]
    """The package's legs (client-long convention, see :class:`RfqLeg`)."""
    size: float
    """Number of packages."""
    client_side: ClientSide
    """Whether the client buys or sells the package."""
    born_day: int = 0
    """Day the RFQ arrived (for expiry in auto-flow mode)."""


StructKind = Literal["single-call", "single-put"] | PresetName
"""Kind of RFQ package: a single vanilla or a Phase-2 preset structure."""


@dataclass(frozen=True, slots=True)
class _Structure:
    """One entry of the RFQ-mix table."""

    name: StructKind
    label: str
    weight: float


_EXPIRIES: Final[tuple[float, ...]] = (1 / 12, 0.25, 0.5, 1)
"""Tenors (years) a client asks for: 1 month, 3 months, 6 months, 1 year."""

_SIZES: Final[tuple[float, ...]] = (10, 25, 50, 100)
"""Package sizes a client asks for."""

_STRUCTURES: Final[tuple[_Structure, ...]] = (
    _Structure("single-call", "Call", 4),
    _Structure("single-put", "Put", 4),
    _Structure("straddle", "Straddle", 1),
    _Structure("strangle", "Strangle", 1),
    _Structure("risk-reversal", "Risk reversal", 1),
    _Structure("call-vertical", "Call spread", 1),
    _Structure("put-vertical", "Put spread", 1),
)
"""The RFQ mix: singles are 4× as likely as each structure (8/13 of the flow)."""


def _pick[ItemT](arr: Sequence[ItemT], u: float) -> ItemT:
    """Pick ``arr[floor(u·n)]`` for a uniform ``u`` in [0, 1) (clamped to the last item)."""
    return arr[min(len(arr) - 1, math.floor(u * len(arr)))]


def _weighted_structure(u: float) -> _Structure:
    """Pick a structure from :data:`_STRUCTURES` with probability ∝ its weight."""
    total = sum(s.weight for s in _STRUCTURES)
    r = u * total
    for s in _STRUCTURES:
        if r < s.weight:
            return s
        r -= s.weight
    return _STRUCTURES[0]


def _flat_vol(_K: float, _T: float) -> float:
    """Placeholder vol for the preset builder (RFQ legs carry no vol)."""
    return 0.2


def single_option_rfq(
    option_type: OptionType,
    K: float,
    T: float,
    size: float,
    client_side: ClientSide,
    id: int,
    born_day: int = 0,
) -> RFQ:
    """Build a single-vanilla RFQ (also handy in tests)."""
    return RFQ(
        id=id,
        label="Call" if option_type == "call" else "Put",
        legs=(RfqLeg(type=option_type, side="long", ratio=1, K=K, T=T),),
        size=size,
        client_side=client_side,
        born_day=born_day,
    )


def generate_rfq(
    spot: float,
    strike_step: float,
    rng: UniformFn,
    id: int,
    day: int = 0,
) -> RFQ:
    """Generate a random RFQ (single or structure) around the current spot.

    Draws from ``rng`` in this exact order (so a seeded stream reproduces the TS engine):

    1. the structure (weighted: see :data:`_STRUCTURES`);
    2. the tenor, from 1m / 3m / 6m / 1y;
    3. the client side (``< 0.5`` ⇒ buy);
    4. the size, from 10 / 25 / 50 / 100;
    5. singles: the strike offset, uniform in ±10% of spot, rounded to the strike grid
       (never below one step); structures: the wing width, uniform in 3%–8% of spot.

    Structure legs come from :func:`~eqd_desk.engine.presets.build_preset` (quantity →
    ratio); the preset vols are irrelevant here (the book re-marks off the live surface).
    """
    struct = _weighted_structure(rng())
    T = _pick(_EXPIRIES, rng())
    client_side: ClientSide = "buy" if rng() < 0.5 else "sell"
    size = _pick(_SIZES, rng())

    name = struct.name
    if name == "single-call" or name == "single-put":
        option_type: OptionType = "call" if name == "single-call" else "put"
        offset = (rng() - 0.5) * 0.2
        K = max(strike_step, round_to(spot * (1 + offset), strike_step))
        return RFQ(
            id=id,
            label=struct.label,
            legs=(RfqLeg(type=option_type, side="long", ratio=1, K=K, T=T),),
            size=size,
            client_side=client_side,
            born_day=day,
        )

    width_pct = 0.03 + rng() * 0.05
    params = PresetParams(
        S=spot, base_t=T, width_pct=width_pct, strike_step=strike_step, vol_for=_flat_vol
    )
    legs = tuple(
        RfqLeg(type=leg.type, side=leg.side, ratio=leg.quantity, K=leg.K, T=leg.T)
        for leg in build_preset(name, params)
    )
    return RFQ(
        id=id,
        label=struct.label,
        legs=legs,
        size=size,
        client_side=client_side,
        born_day=day,
    )


__all__ = [
    "RFQ",
    "ClientSide",
    "RfqLeg",
    "StructKind",
    "UniformFn",
    "generate_rfq",
    "single_option_rfq",
]
