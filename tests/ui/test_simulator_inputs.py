"""Pure helpers of the simulator's steady inputs (:mod:`eqd_desk.app.ui.simulator_inputs`).

Their Streamlit behaviour (explicit defaults, remount on ``set_value``, user edits synced to
the canonical key) is covered by ``tests/app/test_simulator.py``.
"""

from __future__ import annotations

import math

import pytest

from eqd_desk.app.ui.simulator_inputs import (
    GEN_SUFFIX,
    WIDGET_SUFFIX,
    clamp_number,
    gen_key,
    widget_key,
)


def test_keys_are_derived_from_the_canonical_key() -> None:
    assert gen_key("sim.tk_K") == f"sim.tk_K{GEN_SUFFIX}" == "sim.tk_K__gen"
    assert widget_key("sim.tk_K", 0) == f"sim.tk_K{WIDGET_SUFFIX}0" == "sim.tk_K__w0"
    assert widget_key("sim.tk_K", 3) == "sim.tk_K__w3"


def test_each_generation_is_a_distinct_widget() -> None:
    keys = {widget_key("sim.spread", g) for g in range(5)}
    assert len(keys) == 5
    assert "sim.spread" not in keys  # the canonical key is never a widget key
    assert gen_key("sim.spread") not in keys


@pytest.mark.parametrize(
    ("value", "lo", "hi", "integer", "expected"),
    [
        (6300.0, 25, None, True, 6300.0),
        (10.0, 25, None, True, 25.0),  # below the strike grid's minimum
        (1e9, 1, 3650, True, 3650.0),  # tenor capped at ten years
        (60.4, 1, 3650, True, 60.0),
        (0.0525, 0.005, 0.2, False, 0.0525),  # spread stays a fraction
        (-0.5, -0.03, 0.03, False, -0.03),
        (math.nan, 30, 504, True, 30.0),
    ],
)
def test_clamp_number(
    value: float, lo: float, hi: float | None, integer: bool, expected: float
) -> None:
    assert clamp_number(value, lo, hi, integer=integer) == expected
