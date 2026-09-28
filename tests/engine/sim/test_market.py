"""Market simulation and the skew surface. Port of the ``market simulation`` and ``skew
surface`` blocks of ``web/src/engine/sim/__tests__/sim.test.ts``, plus checks of the draw
order (two normals per step) and the vol floor/cap."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from eqd_desk.engine.rng import Mulberry32, NormalSampler
from eqd_desk.engine.sim import (
    DEFAULT_SIM_PARAMS,
    VOL_CAP,
    VOL_FLOOR,
    MarketSimulator,
    MarketState,
    gbm_leverage_process,
    realised_vol,
    vol_for_strike,
)
from tests.engine.sim.common import M0, SKEW_MARKET, close, fixed_normal

# --- market simulation ---------------------------------------------------------------------


def test_is_reproducible_with_a_fixed_seed() -> None:
    a = MarketSimulator(M0, DEFAULT_SIM_PARAMS, 123)
    b = MarketSimulator(M0, DEFAULT_SIM_PARAMS, 123)
    for _ in range(10):
        assert a.next().state.spot == b.next().state.spot


def test_leverage_spot_up_vol_down_and_spot_down_vol_up() -> None:
    p = replace(DEFAULT_SIM_PARAMS, vol_mean_rev=0, vol_of_vol=0)
    up = gbm_leverage_process.step(M0, p, fixed_normal([2, 0]))
    assert up.spot_return > 0
    assert up.d_vol < 0
    dn = gbm_leverage_process.step(M0, p, fixed_normal([-2, 0]))
    assert dn.spot_return < 0
    assert dn.d_vol > 0


def test_keeps_spot_positive_and_vol_within_the_floor_and_cap() -> None:
    sim = MarketSimulator(M0, DEFAULT_SIM_PARAMS, 7)
    for _ in range(300):
        s = sim.next().state
        assert s.spot > 0
        assert s.atm_vol >= 0.05 - 1e-9
        assert s.atm_vol <= 1.2 + 1e-9


def test_realised_vol_zero_for_constant_return_path_positive_for_noisy_one() -> None:
    flat = [100 * math.exp(0.001 * k) for k in range(20)]
    assert realised_vol(flat, 1 / 252) == close(0, 6)
    noisy = [100, 102, 99, 103, 98, 104, 97]
    rv = realised_vol(noisy, 1 / 252)
    assert rv is not None
    assert rv > 0
    assert realised_vol([100], 1 / 252) is None


# --- beyond the TS tests -------------------------------------------------------------------


def test_simulator_consumes_two_normals_per_step_in_order() -> None:
    """Spot uses z1 and vol uses z2 of each pair, from NormalSampler(Mulberry32(seed))."""
    seed = 0x9A17
    sim = MarketSimulator(M0, DEFAULT_SIM_PARAMS, seed)
    normal = NormalSampler(Mulberry32(seed))
    state = M0
    for _ in range(25):
        z1, z2 = normal(), normal()
        manual = gbm_leverage_process.step(state, DEFAULT_SIM_PARAMS, fixed_normal([z1, z2]))
        got = sim.next()
        assert got == manual
        state = manual.state
    assert sim.state == state


def test_step_formula_and_bookkeeping() -> None:
    p = DEFAULT_SIM_PARAMS
    res = gbm_leverage_process.step(SKEW_MARKET, p, fixed_normal([0.7, -1.3]))
    sigma = SKEW_MARKET.atm_vol
    ret = (p.drift - 0.5 * sigma * sigma) * p.dt + sigma * math.sqrt(p.dt) * 0.7
    spot = 100 * math.exp(ret)
    assert res.state.spot == pytest.approx(spot, rel=1e-15)
    assert res.dS == pytest.approx(spot - 100, rel=1e-12)
    assert res.spot_return == pytest.approx(spot / 100 - 1, rel=1e-12)
    vol = (
        sigma
        - p.leverage * res.spot_return
        + p.vol_mean_rev * (p.base_vol - sigma) * p.dt
        + p.vol_of_vol * math.sqrt(p.dt) * -1.3
    )
    assert res.state.atm_vol == pytest.approx(vol, rel=1e-15)
    assert res.d_vol == pytest.approx(vol - sigma, rel=1e-12)
    assert res.state.t == pytest.approx(p.dt, rel=1e-15)
    # r, q and the skew shape are carried through unchanged
    assert (res.state.r, res.state.q) == (SKEW_MARKET.r, SKEW_MARKET.q)
    assert (res.state.skew_slope, res.state.skew_curv) == (-0.5, 0.4)


def test_vol_is_clamped_at_floor_and_cap() -> None:
    p = replace(DEFAULT_SIM_PARAMS, vol_mean_rev=0)
    assert gbm_leverage_process.step(M0, p, fixed_normal([0, -50])).state.atm_vol == VOL_FLOOR
    assert gbm_leverage_process.step(M0, p, fixed_normal([0, 50])).state.atm_vol == VOL_CAP


def test_realised_vol_matches_population_std_of_log_returns() -> None:
    spots = [100, 101, 99.5, 100.7, 102.1, 101.2]
    lr = [math.log(spots[i] / spots[i - 1]) for i in range(1, len(spots))]
    mean = sum(lr) / len(lr)
    var = sum((x - mean) ** 2 for x in lr) / len(lr)
    assert realised_vol(spots, 1 / 252) == pytest.approx(math.sqrt(var * 252), rel=1e-9)
    assert realised_vol([100, 101], 1 / 252) is None


# --- skew surface --------------------------------------------------------------------------


def test_downside_puts_price_at_higher_vol_than_upside_calls() -> None:
    F = 100 * math.exp((0.03 - 0.01) * 0.25)
    low_k = vol_for_strike(SKEW_MARKET, F * 0.9, 0.25)
    atm = vol_for_strike(SKEW_MARKET, F, 0.25)
    high_k = vol_for_strike(SKEW_MARKET, F * 1.1, 0.25)
    assert low_k > atm
    assert high_k < atm
    assert atm == close(0.2, 6)


def test_flat_surface_ignores_the_strike() -> None:
    flat = MarketState(t=0, spot=100, atm_vol=0.2, r=0.03, q=0.01)
    assert vol_for_strike(flat, 80, 0.5) == close(0.2, 9)
    assert vol_for_strike(flat, 120, 0.5) == close(0.2, 9)


def test_surface_is_quadratic_in_log_moneyness_and_clamped() -> None:
    F = 100 * math.exp((0.03 - 0.01) * 0.5)
    k = math.log(90 / F)
    assert vol_for_strike(SKEW_MARKET, 90, 0.5) == pytest.approx(
        0.2 - 0.5 * k + 0.4 * k * k, rel=1e-14
    )
    steep = replace(SKEW_MARKET, skew_slope=-20.0)
    assert vol_for_strike(steep, 10, 0.5) == VOL_CAP
    assert vol_for_strike(steep, 400, 0.5) == VOL_FLOOR
    # T is floored at 1e-6 in the forward
    assert vol_for_strike(SKEW_MARKET, 95, 0) == vol_for_strike(SKEW_MARKET, 95, 1e-6)
    # a flat surface still clamps the ATM level
    assert vol_for_strike(replace(M0, atm_vol=2.0), 100, 0.5) == VOL_CAP
