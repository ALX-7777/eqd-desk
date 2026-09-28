"""Underlying presets (port of ``web/src/data/__tests__/data.test.ts`` › underlying config)."""

from __future__ import annotations

import dataclasses
import typing

import pytest

from eqd_desk.data import DEFAULT_UNDERLYING, UNDERLYING_KEYS, UNDERLYINGS, UnderlyingKey


def test_spx_and_sx5e_presets_spx_default() -> None:
    assert DEFAULT_UNDERLYING == "spx"
    assert UNDERLYINGS["spx"].index_ticker == "^GSPC"
    assert UNDERLYINGS["spx"].vol_index_ticker == "^VIX"
    assert UNDERLYINGS["spx"].options_proxy == "SPY"
    assert UNDERLYINGS["sx5e"].currency == "EUR"
    assert UNDERLYINGS["sx5e"].vol_index_ticker == "V2TX.DE"


def test_presets_match_the_project_spec() -> None:
    """CLAUDE.md: SPX ^GSPC/^VIX/SPY/USD/1.3%, SX5E ^STOXX50E/V2TX.DE/FEZ/EUR/3%."""
    spx, sx5e = UNDERLYINGS["spx"], UNDERLYINGS["sx5e"]
    assert (spx.name, spx.currency, spx.default_div_yield) == ("S&P 500", "USD", 0.013)
    assert (sx5e.name, sx5e.index_ticker, sx5e.options_proxy) == (
        "Euro Stoxx 50",
        "^STOXX50E",
        "FEZ",
    )
    assert sx5e.default_div_yield == 0.03


def test_keys_are_consistent() -> None:
    assert set(UNDERLYINGS) == set(UNDERLYING_KEYS) == set(typing.get_args(UnderlyingKey))
    assert UNDERLYING_KEYS[0] == DEFAULT_UNDERLYING
    for key, cfg in UNDERLYINGS.items():
        assert cfg.key == key


def test_presets_are_read_only() -> None:
    with pytest.raises(TypeError):
        UNDERLYINGS["spx"] = UNDERLYINGS["sx5e"]  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        UNDERLYINGS["spx"].currency = "EUR"  # type: ignore[misc]
