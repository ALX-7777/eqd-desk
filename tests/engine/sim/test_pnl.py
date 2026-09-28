"""P&L attribution. Port of the ``P&L attribution`` and ``attribution reconciles with a live
skew`` blocks of ``web/src/engine/sim/__tests__/sim.test.ts``, plus a term-by-term check of
the Taylor terms against the per-leg greeks."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eqd_desk.engine import BsmInputs, raw_greeks
from eqd_desk.engine.sim import (
    Book,
    BookTrade,
    MarketState,
    PnlAttribution,
    attribute,
    book_value,
    hedge_to_flat,
    vol_for_strike,
)
from tests.engine.sim.common import M0, SKEW_MARKET, close

# A 10-lot long call, no hedge.
LONG_CALL = Book(
    trades=(
        BookTrade(
            id=1, type="call", side="long", quantity=10, K=100, expiry_time=0.5, traded_price=5
        ),
    ),
    underlying_qty=0,
    cash=-50,
    realized_edge=0,
    total_costs=0,
    next_id=2,
)


def _explained(a: PnlAttribution) -> float:
    return a.delta + a.gamma + a.theta + a.vega + a.vanna + a.volga


def test_reconciles_exactly_sum_of_terms_plus_residual_is_total() -> None:
    after = MarketState(t=1 / 252, spot=101.5, atm_vol=0.205, r=0.03, q=0.01)
    a = attribute(LONG_CALL, M0, after)
    total = a.delta + a.gamma + a.theta + a.vega + a.vanna + a.volga + a.residual
    assert total == close(a.total, 9)


def test_pure_small_spot_move_delta_and_gamma_explain_it() -> None:
    after = replace(M0, spot=100.5)  # dS only
    a = attribute(LONG_CALL, M0, after)
    assert abs(a.residual) < 1e-3 * abs(a.total)
    assert a.vega == close(0, 12)
    assert a.theta == close(0, 12)


def test_pure_vol_move_vega_explains_it() -> None:
    after = replace(M0, atm_vol=0.21)  # dVol only
    a = attribute(LONG_CALL, M0, after)
    assert a.delta == 0
    assert abs(a.vega) > 0
    assert abs(a.residual) < 1e-2 * abs(a.total)


def test_long_gamma_delta_hedged_pnl_is_half_gamma_ds_squared() -> None:
    hedged = hedge_to_flat(LONG_CALL, M0)  # delta-neutral
    after = replace(M0, spot=103)
    a = attribute(hedged, M0, after)
    # delta term ~0 (hedged), gamma positive (long gamma), and it dominates
    assert abs(a.delta) < 1e-6
    assert a.gamma > 0
    assert a.total > 0


# --- attribution reconciles with a live skew ------------------------------------------------

SKEW_BOOK = Book(
    trades=(
        BookTrade(
            id=1, type="put", side="short", quantity=20, K=90, expiry_time=0.5, traded_price=2
        ),
        BookTrade(
            id=2, type="call", side="long", quantity=10, K=110, expiry_time=0.4, traded_price=1.5
        ),
    ),
    underlying_qty=5,
    cash=0,
    realized_edge=0,
    total_costs=0,
    next_id=3,
)


def test_reconciles_with_skew_taylor_terms_dominate_and_vanna_is_real() -> None:
    after = replace(SKEW_MARKET, t=1 / 252, spot=99, atm_vol=0.21)
    a = attribute(SKEW_BOOK, SKEW_MARKET, after)
    total = a.delta + a.gamma + a.theta + a.vega + a.vanna + a.volga + a.residual
    assert total == close(a.total, 9)
    explained = sum(
        abs(getattr(a, k)) for k in ("delta", "gamma", "theta", "vega", "vanna", "volga")
    )
    assert abs(a.residual) < 0.2 * explained
    assert a.vanna != 0  # skew ⇒ spot-vol cross P&L


# --- beyond the TS tests -------------------------------------------------------------------


def test_terms_match_the_per_leg_taylor_expansion() -> None:
    before = SKEW_MARKET
    after = replace(SKEW_MARKET, t=2 / 252, spot=98.7, atm_vol=0.215)
    a = attribute(SKEW_BOOK, before, after)
    dS, dt = after.spot - before.spot, after.t - before.t
    want = dict.fromkeys(("delta", "gamma", "theta", "vega", "vanna", "volga"), 0.0)
    for tr in SKEW_BOOK.trades:
        k = (1 if tr.side == "long" else -1) * tr.quantity
        T_b, T_a = tr.expiry_time - before.t, tr.expiry_time - after.t
        sig_b = vol_for_strike(before, tr.K, T_b)
        d_sig = vol_for_strike(after, tr.K, T_a) - sig_b
        inputs = BsmInputs(S=before.spot, K=tr.K, T=T_b, r=0.03, q=0.01, sigma=sig_b)
        g = raw_greeks(inputs, tr.type)
        want["delta"] += k * g.delta * dS
        want["gamma"] += 0.5 * k * g.gamma * dS**2
        want["theta"] += k * g.theta * dt
        want["vega"] += k * g.vega * d_sig
        want["vanna"] += k * g.vanna * dS * d_sig
        want["volga"] += 0.5 * k * g.volga * d_sig**2
    want["delta"] += SKEW_BOOK.underlying_qty * dS
    for name, value in want.items():
        assert getattr(a, name) == pytest.approx(value, rel=1e-12), name
    assert a.total == pytest.approx(
        book_value(SKEW_BOOK, after) - book_value(SKEW_BOOK, before), rel=1e-12
    )
    assert a.residual == pytest.approx(a.total - _explained(a), abs=1e-12)


def test_no_move_no_pnl() -> None:
    a = attribute(SKEW_BOOK, SKEW_MARKET, SKEW_MARKET)
    assert (a.total, a.delta, a.gamma, a.theta, a.vega, a.vanna, a.volga, a.residual) == (
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )


def test_hedge_only_book_is_pure_delta() -> None:
    hedge = replace(LONG_CALL, trades=(), underlying_qty=-3, cash=300)
    a = attribute(hedge, M0, replace(M0, spot=101, t=1 / 252, atm_vol=0.25))
    assert a.delta == pytest.approx(-3.0, rel=1e-12)
    assert a.total == pytest.approx(-3.0, rel=1e-12)
    assert a.gamma == a.theta == a.vega == a.vanna == a.volga == 0
    assert a.residual == pytest.approx(0, abs=1e-12)
