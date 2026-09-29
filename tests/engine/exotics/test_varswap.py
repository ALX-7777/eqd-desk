"""Variance swap fair strike by the 1/K²-weighted OTM strip.

Ported from ``web/src/engine/exotics/__tests__/varswap.test.ts`` (same cases and
tolerances; TS ``toBeCloseTo(x, n)`` is ``|a − b| < 0.5·10⁻ⁿ``), plus Python-side checks
of the strip arithmetic (trapezoid end weights, the forward-kink correction), its accuracy
against a flat smile and a fine strip, the documented truncation, and input validation.
"""

from __future__ import annotations

import math
from collections.abc import Callable
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


SPX_S, SPX_R, SPX_Q = 6312.45, 0.043, 0.013


def _spx(T: float, vol_for: Callable[[float], float], **strip: Any) -> VarSwapInputs:
    return VarSwapInputs(S=SPX_S, T=T, r=SPX_R, q=SPX_Q, vol_for=vol_for, **strip)


def _spx_forward(T: float) -> float:
    return SPX_S * math.exp((SPX_R - SPX_Q) * T)


@pytest.mark.parametrize("days", [7, 14, 30, 60, 90, 180, 365])
@pytest.mark.parametrize("sig", [0.05, 0.1, 0.146, 0.2, 0.3])
def test_flat_smile_prices_the_atm_vol_to_1e4_on_the_default_strip(days: int, sig: float) -> None:
    """Regression: without the forward-kink correction a flat smile printed a nonzero
    "convexity premium" (30d at 14.6%: 14.585%; 7d at 5%: 4.805%, the wrong sign)."""
    res = price_variance_swap(_spx(days / 365, lambda _K: sig))
    assert res.fair_vol == pytest.approx(sig, abs=1e-4)
    assert res.fair_vol - res.atm_vol == pytest.approx(0, abs=1e-4)


def test_short_tenor_premium_has_the_sign_of_a_fine_strip() -> None:
    """7 days, ATM 5%, an UPWARD skew (slope +0.2): the fair vol sits a hair above ATM, as a
    40,000-strike strip confirms. The uncorrected 400-strike strip printed 4.81% (a −0.19 pt
    premium, the wrong sign)."""
    T = 7 / 365
    F = _spx_forward(T)

    def vol_for(K: float) -> float:  # the app's smile: floored at 3%
        return max(0.03, 0.05 + 0.2 * math.log(K / F))

    res = price_variance_swap(_spx(T, vol_for))
    fine = price_variance_swap(_spx(T, vol_for, n_strikes=40_000))
    assert res.fair_vol - res.atm_vol > 0
    assert res.fair_vol == pytest.approx(fine.fair_vol, abs=1e-4)


def test_skewed_default_strip_matches_a_fine_strip() -> None:
    """The snapshot's SPX smile (slope −0.48, curvature 0.62) at 30 days: the 0.3F end strike
    carries ~160% vol, so the strip's ends matter. With trapezoid end weights the 400-strike
    strip agrees with a 40,000-strike one to a few thousandths of a vol point (it read
    17.26% vs 17.15% with full end weights)."""
    T = 30 / 365
    F = _spx_forward(T)

    def vol_for(K: float) -> float:
        k = math.log(K / F)
        return 0.146 - 0.48 * k + 0.62 * k * k

    res = price_variance_swap(_spx(T, vol_for))
    fine = price_variance_swap(_spx(T, vol_for, n_strikes=40_000))
    assert res.fair_vol == pytest.approx(fine.fair_vol, abs=5e-5)
    assert res.fair_vol > res.atm_vol + 0.02  # a real equity skew: a ~2.6 pt premium


def test_grid_correction_is_the_bernoulli_kink_term() -> None:
    """grid_correction = −(ΔK/F)²·B₂(θ)/T with θ = (F − lo)/ΔK mod 1, and it is what makes
    the answer insensitive to where F falls between two strikes."""
    T = 7 / 365
    res = price_variance_swap(_spx(T, lambda _K: 0.05))
    F = res.forward
    dK = (3.0 - 0.3) * F / 399
    theta = ((F - 0.3 * F) / dK) % 1
    expected = -((dK / F) ** 2) * (theta * theta - theta + 1 / 6) / T
    assert res.grid_correction == pytest.approx(expected, rel=1e-9)
    # Slide the strip so F lands at different fractions of a strike gap: the same answer to
    # O(ΔK³) (uncorrected, the spread was 0.6 vol pt: 4.80% … 5.38%).
    vols = [
        price_variance_swap(_spx(T, lambda _K: 0.05, lo_mult=0.3 + f * dK / F)).fair_vol
        for f in (0.0, 0.25, 0.5, 0.75)
    ]
    assert max(vols) - min(vols) < 5e-5


def test_no_grid_correction_when_the_forward_is_outside_the_strip() -> None:
    res = price_variance_swap(replace(BASE, lo_mult=1.1, hi_mult=3.0))
    assert res.grid_correction == 0
    total = sum(pt.contribution for pt in res.strip)
    assert res.fair_variance == pytest.approx(2 * math.exp(BASE.r * BASE.T) / BASE.T * total)


def test_truncation_drops_the_tails_at_long_tenor_and_high_vol() -> None:
    """Documented limitation: strikes outside 0.3F…3F are absent. A flat 60% smile at one
    year prices ≈59.53% (the truncated integral, which a fine strip on the same range
    confirms); widening the strip recovers 60%."""
    one_year = _spx(1.0, lambda _K: 0.6)
    res = price_variance_swap(one_year)
    same_range = price_variance_swap(replace(one_year, n_strikes=20_000))
    wide = price_variance_swap(replace(one_year, lo_mult=0.01, hi_mult=12.0, n_strikes=20_000))
    assert res.fair_vol == pytest.approx(0.5953, abs=1e-4)
    assert res.fair_vol == pytest.approx(same_range.fair_vol, abs=1e-4)
    assert wide.fair_vol == pytest.approx(0.6, abs=1e-4)


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
    """Weight = ΔK/K² (half at the two end strikes), contribution = weight·price, fair
    variance = 2e^(rT)/T · Σ + the forward-kink correction."""
    res = price_variance_swap(replace(BASE, n_strikes=50))
    strikes = [pt.K for pt in res.strip]
    dK = strikes[1] - strikes[0]
    assert len(res.strip) == 50
    assert strikes[0] == pytest.approx(0.3 * res.forward, rel=1e-15)
    assert strikes[-1] == pytest.approx(3.0 * res.forward, rel=1e-12)
    for j, pt in enumerate(res.strip):
        half = 0.5 if j in (0, len(res.strip) - 1) else 1.0
        assert pt.weight == pytest.approx(half * dK / (pt.K * pt.K), rel=1e-12)
        assert pt.contribution == pt.weight * pt.option_price
    total = sum(pt.contribution for pt in res.strip)
    assert res.grid_correction != 0
    assert res.fair_variance == pytest.approx(
        2 * math.exp(BASE.r * BASE.T) / BASE.T * total + res.grid_correction
    )


def test_non_positive_strikes_are_skipped() -> None:
    res = price_variance_swap(replace(BASE, lo_mult=-0.5, n_strikes=40))
    assert 0 < len(res.strip) < 40
    assert all(pt.K > 0 for pt in res.strip)
    # the grid's first strike (j = 0) was the skipped one, so the first KEPT strike has the
    # full ΔK/K² weight (only the grid's two ends are halved)
    dK = res.strip[1].K - res.strip[0].K
    assert res.strip[0].weight == pytest.approx(dK / res.strip[0].K ** 2, rel=1e-12)


@pytest.mark.parametrize(("field", "value"), [("T", 0.0), ("T", -1.0), ("n_strikes", 1)])
def test_rejects_degenerate_inputs(field: str, value: float) -> None:
    changes: dict[str, Any] = {field: value}
    with pytest.raises(ValueError, match="varswap"):
        price_variance_swap(replace(BASE, **changes))
