"""Variance swap fair strike by the 1/K²-weighted OTM strip.

Ported from ``web/src/engine/exotics/__tests__/varswap.test.ts`` (same cases and
tolerances; TS ``toBeCloseTo(x, n)`` is ``|a − b| < 0.5·10⁻ⁿ``), plus Python-side checks
of the strip arithmetic and input validation.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import pytest

from eqd_desk.engine.exotics import VarSwapInputs, price_variance_swap

BASE = VarSwapInputs(S=100, T=1, r=0.03, q=0.01, vol_for=lambda _K: 0.2)


def _flat(sig: float) -> VarSwapInputs:
    return replace(BASE, vol_for=lambda _K: sig)


@pytest.mark.parametrize("sig", [0.15, 0.2, 0.3])
def test_flat_vol_fair_variance_is_sigma_squared(sig: float) -> None:
    """The log contract recovers the GBM variance."""
    res = price_variance_swap(_flat(sig))
    assert res.fair_variance == pytest.approx(sig * sig, abs=5e-4)
    assert res.fair_vol == pytest.approx(sig, abs=5e-4)


def test_returns_the_forward_and_atm_vol() -> None:
    res = price_variance_swap(BASE)
    assert res.forward == pytest.approx(BASE.S * math.exp((BASE.r - BASE.q) * BASE.T), abs=5e-10)
    assert res.atm_vol == pytest.approx(0.2, abs=5e-10)


def test_downward_skew_lifts_fair_vol_above_atm() -> None:
    """Puts richer than calls (vol falls with strike): the convexity / VIX premium."""
    res = price_variance_swap(replace(BASE, vol_for=lambda K: max(0.05, 0.2 - 0.0015 * (K - 100))))
    assert res.fair_vol > res.atm_vol


def test_strip_is_otm_and_weighted_one_over_k_squared() -> None:
    res = price_variance_swap(BASE)
    for pt in res.strip:
        forward, strike = res.forward, pt.K
        assert pt.type == ("put" if strike < forward else "call")
        assert pt.weight > 0


def test_strip_arithmetic() -> None:
    """Weight = ΔK/K², contribution = weight·price, fair variance = 2e^(rT)/T · Σ."""
    res = price_variance_swap(replace(BASE, n_strikes=50))
    strikes = [pt.K for pt in res.strip]
    dK = strikes[1] - strikes[0]
    assert len(res.strip) == 50
    assert strikes[0] == pytest.approx(0.3 * res.forward, rel=1e-15)
    assert strikes[-1] == pytest.approx(3.0 * res.forward, rel=1e-12)
    for pt in res.strip:
        assert pt.weight == pytest.approx(dK / (pt.K * pt.K), rel=1e-12)
        assert pt.contribution == pt.weight * pt.option_price
    total = sum(pt.contribution for pt in res.strip)
    assert res.fair_variance == pytest.approx(2 * math.exp(BASE.r * BASE.T) / BASE.T * total)


def test_non_positive_strikes_are_skipped() -> None:
    res = price_variance_swap(replace(BASE, lo_mult=-0.5, n_strikes=40))
    assert 0 < len(res.strip) < 40
    assert all(pt.K > 0 for pt in res.strip)


@pytest.mark.parametrize(("field", "value"), [("T", 0.0), ("T", -1.0), ("n_strikes", 1)])
def test_rejects_degenerate_inputs(field: str, value: float) -> None:
    changes: dict[str, Any] = {field: value}
    with pytest.raises(ValueError, match="varswap"):
        price_variance_swap(replace(BASE, **changes))
