"""Preset structures: exact leg geometry of every preset, the JS-compatible strike
rounding, the registry of labels, and input handling. Complements the preset cases ported
from the TS suite in ``test_strategy.py``."""

from __future__ import annotations

from dataclasses import replace
from typing import get_args

import pytest

from eqd_desk.engine.presets import (
    CALENDAR_BACK_OFFSET,
    PRESETS,
    PresetName,
    PresetParams,
    build_preset,
    round_to,
)
from eqd_desk.engine.strategy import Leg


def flat_vol(_K: float, _T: float) -> float:
    return 0.2


PARAMS = PresetParams(S=100, base_t=0.25, width_pct=0.05, strike_step=5, vol_for=flat_vol)

# (type, side, quantity, K) per leg, at S=100, width 5%, step 5 → atm = 100, w = 5.
EXPECTED: dict[PresetName, list[tuple[str, str, float, float]]] = {
    "call-vertical": [("call", "long", 1, 100), ("call", "short", 1, 105)],
    "put-vertical": [("put", "long", 1, 100), ("put", "short", 1, 95)],
    "straddle": [("call", "long", 1, 100), ("put", "long", 1, 100)],
    "strangle": [("put", "long", 1, 95), ("call", "long", 1, 105)],
    "risk-reversal": [("put", "short", 1, 95), ("call", "long", 1, 105)],
    "butterfly": [("call", "long", 1, 95), ("call", "short", 2, 100), ("call", "long", 1, 105)],
    "iron-condor": [
        ("put", "long", 1, 90),
        ("put", "short", 1, 95),
        ("call", "short", 1, 105),
        ("call", "long", 1, 110),
    ],
    "calendar": [("call", "short", 1, 100), ("call", "long", 1, 100)],
}


def _shape(legs: list[Leg]) -> list[tuple[str, str, float, float]]:
    return [(leg.type, leg.side, leg.quantity, leg.K) for leg in legs]


def test_registry_lists_every_preset_once_in_display_order() -> None:
    names = [p.name for p in PRESETS]
    assert names == list(get_args(PresetName))
    assert [p.label for p in PRESETS] == [
        "Bull call spread",
        "Bear put spread",
        "Straddle",
        "Strangle",
        "Risk reversal",
        "Butterfly",
        "Iron condor",
        "Calendar",
    ]


@pytest.mark.parametrize("name", list(EXPECTED))
def test_leg_geometry(name: PresetName) -> None:
    legs = build_preset(name, PARAMS)
    assert _shape(legs) == EXPECTED[name]
    assert [leg.id for leg in legs] == [f"{name}-{i}" for i in range(len(legs))]
    assert all(leg.sigma == 0.2 for leg in legs)
    if name == "calendar":
        assert [leg.T for leg in legs] == [0.25, 0.25 + CALENDAR_BACK_OFFSET]
    else:
        assert all(leg.T == 0.25 for leg in legs)


def test_index_level_grid() -> None:
    """SPX-like: 6312.45 on a 25-pt grid → atm 6300; 5% wing = 315.6 → 325 (one grid step
    of rounding)."""
    legs = build_preset("iron-condor", replace(PARAMS, S=6312.45, strike_step=25))
    assert [leg.K for leg in legs] == [5650, 5975, 6625, 6950]


def test_wing_width_never_below_one_strike_step() -> None:
    legs = build_preset("strangle", replace(PARAMS, width_pct=0.001))  # 0.1 → rounds to 0
    assert [leg.K for leg in legs] == [95, 105]


def test_vol_provider_called_per_leg_in_order_with_leg_strike_and_expiry() -> None:
    calls: list[tuple[float, float]] = []

    def recording_vol(K: float, T: float) -> float:
        calls.append((K, T))
        return 0.1 + K / 1000

    legs = build_preset("butterfly", replace(PARAMS, vol_for=recording_vol))
    assert calls == [(95, 0.25), (100, 0.25), (105, 0.25)]
    assert [leg.sigma for leg in legs] == [0.1 + K / 1000 for K, _ in calls]


def test_unknown_preset_raises() -> None:
    with pytest.raises(ValueError, match="unknown preset"):
        build_preset("jade-lizard", PARAMS)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("x", "step", "expected"),
    [
        (100.0, 5, 100.0),
        (102.4, 5, 100.0),
        (102.5, 5, 105.0),  # tie → up (Python's round() would give 100: banker's rounding)
        (107.5, 5, 110.0),  # tie → up (round() also up here: 22 is even)
        (6312.5, 25, 6325.0),  # tie on an index grid
        (6312.45, 25, 6300.0),
        (-2.5, 1, -2.0),  # JS Math.round(-2.5) = -2: ties toward +∞, not away from 0
        (-2.6, 1, -3.0),
        (0.49999999999999994, 1, 0.0),  # largest double < 0.5: must NOT round up
        (315.62, 25, 325.0),
    ],
)
def test_round_to_matches_js_math_round(x: float, step: float, expected: float) -> None:
    assert round_to(x, step) == expected
    assert isinstance(round_to(x, step), float)
