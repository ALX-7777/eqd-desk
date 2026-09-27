from __future__ import annotations

import math
from dataclasses import replace

import pytest

from eqd_desk.engine import (
    BsmInputs,
    bsm_core,
    call_price,
    forward,
    price,
    put_price,
    validate_inputs,
)

CANONICAL = BsmInputs(S=100, K=100, T=1, r=0.05, q=0, sigma=0.2)


def test_bsm_core_canonical() -> None:
    c = bsm_core(CANONICAL)
    assert c.d1 == pytest.approx(0.35, abs=1e-12)  # (0.05 + 0.02) / 0.2
    assert c.d2 == pytest.approx(0.15, abs=1e-12)
    assert c.df_r == pytest.approx(math.exp(-0.05), abs=1e-15)
    assert c.df_q == 1.0


def test_textbook_reference_prices() -> None:
    # S=K=100, T=1, r=5%, q=0, σ=20% (Hull).
    assert call_price(CANONICAL) == pytest.approx(10.450583572185565, abs=1e-6)
    assert put_price(CANONICAL) == pytest.approx(5.573526022256971, abs=1e-6)


def test_price_dispatches_by_type() -> None:
    assert price(CANONICAL, "call") == call_price(CANONICAL)
    assert price(CANONICAL, "put") == put_price(CANONICAL)


@pytest.mark.parametrize(
    "i",
    [
        CANONICAL,
        BsmInputs(S=100, K=120, T=0.5, r=0.03, q=0.02, sigma=0.25),
        BsmInputs(S=130, K=100, T=0.75, r=0.04, q=0.015, sigma=0.18),
        BsmInputs(S=50, K=100, T=2, r=0.06, q=0.01, sigma=0.4),
    ],
)
def test_put_call_parity(i: BsmInputs) -> None:
    """C − P = S·e^(−qT) − K·e^(−rT)."""
    lhs = call_price(i) - put_price(i)
    rhs = i.S * math.exp(-i.q * i.T) - i.K * math.exp(-i.r * i.T)
    assert lhs == pytest.approx(rhs, abs=1e-9)


@pytest.mark.parametrize(
    "i",
    [
        CANONICAL,
        BsmInputs(S=150, K=100, T=1, r=0.05, q=0.0, sigma=0.2),  # deep ITM call
        BsmInputs(S=60, K=100, T=1, r=0.05, q=0.0, sigma=0.2),  # deep OTM call
    ],
)
def test_no_arbitrage_bounds(i: BsmInputs) -> None:
    c, p = call_price(i), put_price(i)
    df_r, fwd = math.exp(-i.r * i.T), forward(i)
    assert c >= 0
    assert p >= 0
    assert c >= df_r * max(fwd - i.K, 0) - 1e-9
    assert p >= df_r * max(i.K - fwd, 0) - 1e-9


def test_deep_itm_call_has_no_time_value() -> None:
    i = BsmInputs(S=1000, K=100, T=1, r=0.05, q=0.02, sigma=0.2)
    intrinsic = i.S * math.exp(-i.q * i.T) - i.K * math.exp(-i.r * i.T)
    assert call_price(i) == pytest.approx(intrinsic, abs=1e-6)


def test_zero_vol_tends_to_discounted_intrinsic() -> None:
    i = BsmInputs(S=110, K=100, T=1, r=0.05, q=0.0, sigma=0)
    assert call_price(i) == pytest.approx(math.exp(-i.r) * max(forward(i) - i.K, 0), abs=1e-4)


def test_zero_time_tends_to_payoff() -> None:
    itm = BsmInputs(S=110, K=100, T=0, r=0.05, q=0.0, sigma=0.2)
    otm = replace(itm, S=90)
    assert call_price(itm) == pytest.approx(10, abs=1e-3)
    assert call_price(otm) == pytest.approx(0, abs=1e-3)
    assert put_price(otm) == pytest.approx(10, abs=1e-3)


def test_finite_at_the_boundaries() -> None:
    i = BsmInputs(S=100, K=100, T=0, r=0.05, q=0.0, sigma=0)
    assert math.isfinite(call_price(i))
    assert math.isfinite(put_price(i))


@pytest.mark.parametrize(
    "bad",
    [
        {"S": 0},
        {"K": -1},
        {"T": -0.5},
        {"sigma": -0.1},
        {"S": math.nan},
        {"r": math.inf},
        {"q": math.nan},
    ],
)
def test_rejects_invalid_inputs(bad: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="BSM"):
        validate_inputs(replace(CANONICAL, **bad))
