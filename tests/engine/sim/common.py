"""Shared fixtures for the simulator tests (the constants at the top of
``web/src/engine/sim/__tests__/sim.test.ts``). A helper module, not a test file.

TS ``toBeCloseTo(x, n)`` means |a − b| < 0.5·10⁻ⁿ, i.e. ``close(x, n)`` here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest

from eqd_desk.engine.sim import CostModel, MarketState

M0 = MarketState(t=0, spot=100, atm_vol=0.2, r=0.03, q=0.01)
"""Flat-surface market used by most tests."""

SKEW_MARKET = MarketState(
    t=0, spot=100, atm_vol=0.2, r=0.03, q=0.01, skew_slope=-0.5, skew_curv=0.4
)
"""Equity-skewed market."""

COSTS = CostModel(underlying_half_spread=0.0001, option_half_spread=0.01)
"""1 bp on the underlying, 1% of premium on options (the UI's cost model)."""


def fixed_normal(vals: Sequence[float]) -> Callable[[], float]:
    """A "normal sampler" that cycles through ``vals`` (TS ``fixedNormal``)."""
    i = 0

    def draw() -> float:
        nonlocal i
        v = vals[i % len(vals)]
        i += 1
        return v

    return draw


def close(expected: float, digits: int) -> object:
    """``pytest.approx`` equivalent of vitest ``toBeCloseTo(expected, digits)``."""
    return pytest.approx(expected, abs=0.5 * 10.0**-digits)
