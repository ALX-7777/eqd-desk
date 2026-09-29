"""Desk units in the snapshot's currency, for readouts, axis titles and badges.

The engine's unit strings (:data:`eqd_desk.engine.GREEK_UNITS`) are written for the default
underlying, in dollars: delta is "per $1 spot". The underlying is a config input, though,
and an index option's premium and spot are both quoted in index points of its currency, so
on the Euro Stoxx 50 the same delta is "per €1 spot". This module rewrites the ``$1`` of a
unit in the snapshot currency; the engine strings stay the single source of the wording.

Pure: no Streamlit, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from eqd_desk.engine import GREEK_UNITS

ENGINE_UNIT_MONEY: Final = "$1"
"""How the engine's unit strings write one unit of currency ("per $1 spot")."""

CURRENCY_SYMBOLS: Final[Mapping[str, str]] = MappingProxyType({"USD": "$", "EUR": "€"})
"""Symbol of each currency the underlying presets use (S&P 500: USD, Euro Stoxx 50: EUR)."""


def one_unit(currency: str) -> str:
    """One unit of ``currency`` as a greek unit prints it: ``"$1"`` (USD), ``"€1"`` (EUR),
    else the ISO code (``"1 GBP"``)."""
    symbol = CURRENCY_SYMBOLS.get(currency)
    return f"{symbol}1" if symbol else f"1 {currency}"


def greek_unit(key: str, currency: str | None = None) -> str:
    """The desk unit of a greek (a key of :data:`~eqd_desk.engine.GREEK_UNITS`) in
    ``currency``: ``greek_unit("delta", "EUR") == "per €1 spot"``. ``None`` keeps the
    engine's wording (dollars); units without money ("per 1 vol pt") never change."""
    unit = GREEK_UNITS[key].unit
    return unit if currency is None else unit.replace(ENGINE_UNIT_MONEY, one_unit(currency))


def axis_title(key: str, currency: str, *, prefix: str = "", price_label: str = "Price") -> str:
    """A chart's y-axis title for a greek or the price, with its unit in brackets.

    The price is in currency units (``"Price (USD)"``, or ``"Value (USD)"`` with
    ``price_label="Value"``); a greek carries its desk unit (``"Vega (per 1 vol pt)"``).
    ``prefix`` qualifies either (``"Net "`` for a whole structure: ``"Net Delta (per $1
    spot)"``).
    """
    if key == "price":
        return f"{prefix}{price_label} ({currency})"
    return f"{prefix}{GREEK_UNITS[key].label} ({greek_unit(key, currency)})"


__all__ = [
    "CURRENCY_SYMBOLS",
    "ENGINE_UNIT_MONEY",
    "axis_title",
    "greek_unit",
    "one_unit",
]
