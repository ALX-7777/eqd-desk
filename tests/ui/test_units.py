"""Desk units in the snapshot currency (:mod:`eqd_desk.app.ui.units`)."""

from __future__ import annotations

import pytest

from eqd_desk.app.ui import units
from eqd_desk.data import UNDERLYINGS
from eqd_desk.engine import GREEK_UNITS


def test_one_unit_of_each_preset_currency() -> None:
    assert units.one_unit("USD") == "$1"
    assert units.one_unit("EUR") == "€1"
    assert units.one_unit("GBP") == "1 GBP"
    for cfg in UNDERLYINGS.values():  # every underlying preset has a symbol
        assert cfg.currency in units.CURRENCY_SYMBOLS


@pytest.mark.parametrize("key", list(GREEK_UNITS))
def test_greek_unit_rewrites_only_the_money(key: str) -> None:
    engine = GREEK_UNITS[key].unit
    assert units.greek_unit(key) == engine  # no currency: the engine's wording
    assert units.greek_unit(key, "USD") == engine  # the engine writes dollars
    eur = units.greek_unit(key, "EUR")
    assert "$" not in eur
    assert eur == engine.replace("$1", "€1")


def test_axis_titles() -> None:
    assert units.axis_title("delta", "USD") == "Delta (per $1 spot)"
    assert units.axis_title("gamma", "EUR") == "Gamma (Δdelta per €1 spot)"
    assert units.axis_title("vega", "EUR") == "Vega (per 1 vol pt)"
    assert units.axis_title("price", "USD") == "Price (USD)"
    assert units.axis_title("price", "EUR", price_label="Value") == "Value (EUR)"
    assert units.axis_title("price", "USD", prefix="Net ") == "Net Price (USD)"
    assert units.axis_title("theta", "USD", prefix="Net ") == "Net Theta (per day)"
