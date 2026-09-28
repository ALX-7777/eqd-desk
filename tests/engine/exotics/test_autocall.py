"""Phoenix autocallable Monte Carlo: reproducibility, diagnostics, monotonicity and a
deterministic cross-check against digitals.

Ported from ``web/src/engine/exotics/__tests__/autocall.test.ts`` (same cases, seeds,
path counts and tolerances), plus Python-side checks that the vectorised pricer walks the
SAME draws as the literal loop port, that the bump greeks use common random numbers, and
of input validation.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import pytest

from eqd_desk.engine.exotics import (
    AutocallInputs,
    DigitalInputs,
    asset_or_nothing_price,
    autocall_greeks,
    cash_or_nothing_price,
    price_autocall,
    price_autocall_loop,
)

BASE = AutocallInputs(
    S=100,
    S0=100,
    sigma=0.2,
    r=0.04,
    q=0.01,
    maturity=3,
    n_obs=3,
    coupon_rate=0.06,
    autocall_barrier=1.0,
    coupon_barrier=0.7,
    protection_barrier=0.7,
    memory=True,
    notional=100,
)


def test_is_reproducible_with_a_fixed_seed() -> None:
    a = price_autocall(BASE, 5000, 42)
    b = price_autocall(BASE, 5000, 42)
    assert a.price == b.price


def test_reports_sane_diagnostics() -> None:
    res = price_autocall(BASE, 40_000)
    assert res.price > 0
    assert 0 <= res.prob_autocall <= 1
    assert res.prob_capital_loss >= 0
    assert res.expected_life > 0
    assert res.expected_life <= BASE.maturity + 1e-9
    assert res.stderr > 0


def test_lower_autocall_barrier_means_more_early_redemption() -> None:
    high = price_autocall(replace(BASE, autocall_barrier=1.1), 40_000)
    low = price_autocall(replace(BASE, autocall_barrier=0.8), 40_000)
    assert low.prob_autocall > high.prob_autocall


def test_zero_coupon_never_called_note_equals_digital_replication() -> None:
    """No coupon, autocall barrier unreachable ⇒ only the maturity redemption matters::

    payoff = N · [ 1{S_T ≥ PB} + (S_T/S0)·1{S_T < PB} ]
    PV     = N · [ cash-or-nothing call(PB) + asset-or-nothing put(PB)/S0 ]
    """
    i = replace(BASE, coupon_rate=0, autocall_barrier=10, protection_barrier=0.7, memory=False)
    PB = i.protection_barrier * i.S0
    digital = DigitalInputs(
        S=i.S, K=PB, T=i.maturity, r=i.r, q=i.q, sigma=i.sigma, type="call", cash=1
    )
    cash_call = cash_or_nothing_price(digital)
    asset_put = asset_or_nothing_price(replace(digital, type="put", cash=0))
    analytic = i.notional * (cash_call + asset_put / i.S0)

    mc = price_autocall(i, 200_000, 20250624)
    assert abs(mc.price - analytic) < 4 * mc.stderr + 0.02


# --- Python-side: the vectorised pricer is the loop, faster -------------------------------

VARIANTS = {
    "base": BASE,
    "no memory": replace(BASE, memory=False),
    "single observation": replace(BASE, maturity=1, n_obs=1),
    "below fixing, monthly": replace(
        BASE, S=85, sigma=0.3, n_obs=12, autocall_barrier=0.95, coupon_barrier=0.8
    ),
    "rarely called": replace(BASE, sigma=0.45, n_obs=24, autocall_barrier=1.2, coupon_barrier=1.0),
    "always called at first date": replace(BASE, autocall_barrier=0.01, coupon_barrier=0.01),
}


@pytest.mark.parametrize("name", list(VARIANTS))
@pytest.mark.parametrize("seed", [1, 0x9E3779B1])
def test_vectorised_pricer_matches_the_loop(name: str, seed: int) -> None:
    """Same draws, same paths: every count is identical and the sums agree to rounding
    (numpy sums pairwise, the loop sequentially)."""
    i = VARIANTS[name]
    fast = price_autocall(i, 3000, seed)
    slow = price_autocall_loop(i, 3000, seed)
    assert fast.prob_autocall == slow.prob_autocall
    assert fast.prob_capital_loss == slow.prob_capital_loss
    assert fast.price == pytest.approx(slow.price, rel=1e-12)
    assert fast.expected_life == pytest.approx(slow.expected_life, rel=1e-12)
    # stderr = √((E[pv²] − E[pv]²)/n): when every path pays the same the difference is pure
    # rounding (0 summed sequentially, ~1e-15·E[pv²] pairwise), hence the absolute floor.
    assert fast.stderr == pytest.approx(slow.stderr, rel=1e-9, abs=1e-6)


def test_always_called_note_is_one_coupon_plus_par_after_one_period() -> None:
    """Autocall and coupon barriers far below spot: every path redeems at the first date
    with one coupon, so the price is deterministic and the MC error is ~0."""
    i = VARIANTS["always called at first date"]
    res = price_autocall(i, 2000, 3)
    dt = i.maturity / i.n_obs
    expected = i.notional * (1 + i.coupon_rate) * math.exp(-i.r * dt)
    assert res.price == pytest.approx(expected, rel=1e-12)
    assert res.prob_autocall == 1
    assert res.expected_life == pytest.approx(dt, rel=1e-12)
    assert res.stderr == pytest.approx(0, abs=1e-6)


def test_greeks_use_common_random_numbers() -> None:
    """The greeks' base price is exactly the seeded price (same draws), and the bump greeks
    are reproducible. (Their SIZE is noisy: a 1e-4·S spot bump flips only a handful of
    paths across the digital-like autocall barrier, which is why the TS default uses
    40 000 paths.)"""
    g = autocall_greeks(BASE, 8000, 42)
    assert g.price == price_autocall(BASE, 8000, 42).price
    assert autocall_greeks(BASE, 8000, 42) == g
    assert all(math.isfinite(v) for v in g.as_dict().values())


@pytest.mark.parametrize(
    ("changes", "paths"),
    [({}, 0), ({"n_obs": 0}, 100), ({"maturity": 0.0}, 100), ({"S0": 0.0}, 100)],
)
def test_rejects_degenerate_inputs(changes: dict[str, Any], paths: int) -> None:
    i = replace(BASE, **changes)
    for pricer in (price_autocall, price_autocall_loop, autocall_greeks):
        with pytest.raises(ValueError, match="autocall"):
            pricer(i, paths)
