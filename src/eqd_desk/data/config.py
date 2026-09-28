"""Underlying presets.

The app is built around a config object, not a hardcoded index, so the whole simulator
can be re-pointed with a single flag. S&P 500 is the default (richest free data, deepest
options proxy in SPY).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

UnderlyingKey = Literal["spx", "sx5e"]
"""Short key of a supported underlying (also the ``--underlying`` flag of the scripts)."""

UNDERLYING_KEYS: tuple[UnderlyingKey, ...] = ("spx", "sx5e")
"""Every supported underlying key, default first."""


@dataclass(frozen=True, slots=True)
class UnderlyingConfig:
    """Everything the app needs to know about one underlying index."""

    key: UnderlyingKey
    """Short key (``"spx"`` / ``"sx5e"``)."""
    name: str
    """Display name."""
    index_ticker: str
    """Real index ticker (spot + realized vol source)."""
    vol_index_ticker: str
    """Vol-gauge ticker that anchors the ATM level (VIX / VSTOXX)."""
    options_proxy: str
    """Listed ETF proxy whose option chain gives the skew shape (SPY / FEZ)."""
    currency: str
    """Premium currency."""
    default_div_yield: float
    """Fallback continuous dividend yield if not estimated (decimal, 0.013 = 1.3%)."""


UNDERLYINGS: Final[Mapping[UnderlyingKey, UnderlyingConfig]] = MappingProxyType(
    {
        "spx": UnderlyingConfig(
            key="spx",
            name="S&P 500",
            index_ticker="^GSPC",
            vol_index_ticker="^VIX",
            options_proxy="SPY",
            currency="USD",
            default_div_yield=0.013,
        ),
        "sx5e": UnderlyingConfig(
            key="sx5e",
            name="Euro Stoxx 50",
            index_ticker="^STOXX50E",
            vol_index_ticker="V2TX.DE",
            options_proxy="FEZ",
            currency="EUR",
            default_div_yield=0.03,
        ),
    }
)
"""The two presets, keyed by :data:`UnderlyingKey`. Read-only."""

DEFAULT_UNDERLYING: Final[UnderlyingKey] = "spx"
"""S&P 500 is the default underlying."""
