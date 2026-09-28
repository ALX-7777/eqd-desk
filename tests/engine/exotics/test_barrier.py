"""Single-barrier closed forms: in-out parity, limits, a Monte-Carlo cross-check of every
knock-out formula branch, and the near-barrier gamma behaviour.

Ported from ``web/src/engine/exotics/__tests__/barrier.test.ts`` (same cases, seeds and
tolerances; TS ``toBeCloseTo(x, n)`` is ``|a − b| < 0.5·10⁻ⁿ``), plus Python-side checks
of input validation and of the bump greeks' units against the analytic vanilla greeks.
"""

from __future__ import annotations

import math
from dataclasses import replace
from itertools import islice
from typing import Any

import numpy as np
import pytest

from eqd_desk.engine import BsmInputs, OptionType, analyze_option
from eqd_desk.engine import price as vanilla_price
from eqd_desk.engine.exotics import (
    BARRIER_KINDS,
    BarrierInputs,
    BarrierKind,
    barrier_greeks,
    barrier_price,
    iter_normal_blocks,
    obs_paths_from_normals,
)

BASE = BarrierInputs(
    S=100, K=100, T=1, r=0.05, q=0.01, sigma=0.2, type="call", H=90, kind="down-out"
)


def _inputs(K: float, H: float, option_type: OptionType, kind: BarrierKind) -> BarrierInputs:
    return replace(BASE, K=K, H=H, type=option_type, kind=kind)


def _bsm(i: BarrierInputs) -> BsmInputs:
    """The vanilla with the same S, K, T, r, q, σ."""
    return BsmInputs(S=i.S, K=i.K, T=i.T, r=i.r, q=i.q, sigma=i.sigma)


def _vanilla(K: float, option_type: OptionType) -> float:
    return vanilla_price(_bsm(replace(BASE, K=K)), option_type)


# --- knock-in + knock-out = vanilla (in-out parity) -------------------------------------

PARITY_CASES = [
    (option_type, direction, H, K)
    for option_type in ("call", "put")
    for direction, H, Ks in (("down", 90.0, (100.0, 85.0)), ("up", 110.0, (100.0, 115.0)))
    for K in Ks
]


@pytest.mark.parametrize(("option_type", "direction", "H", "K"), PARITY_CASES)
def test_in_out_parity(option_type: OptionType, direction: str, H: float, K: float) -> None:
    kind_in: BarrierKind = "down-in" if direction == "down" else "up-in"
    kind_out: BarrierKind = "down-out" if direction == "down" else "up-out"
    ki = barrier_price(_inputs(K, H, option_type, kind_in))
    ko = barrier_price(_inputs(K, H, option_type, kind_out))
    assert ki + ko == pytest.approx(_vanilla(K, option_type), abs=5e-10)


# --- barrier limits ----------------------------------------------------------------------


def test_down_and_out_call_with_far_barrier_is_vanilla() -> None:
    price = barrier_price(_inputs(100, 1, "call", "down-out"))
    assert price == pytest.approx(_vanilla(100, "call"), abs=5e-7)


def test_up_and_out_call_with_far_barrier_is_vanilla() -> None:
    price = barrier_price(_inputs(100, 1e6, "call", "up-out"))
    assert price == pytest.approx(_vanilla(100, "call"), abs=5e-7)


def test_down_and_in_call_with_far_barrier_is_worthless() -> None:
    assert barrier_price(_inputs(100, 1, "call", "down-in")) < 1e-4


def test_already_breached() -> None:
    # down barrier above spot ⇒ already breached: knock-out dead, knock-in = vanilla
    assert barrier_price(_inputs(100, 105, "call", "down-out")) == 0
    in_price = barrier_price(_inputs(100, 105, "call", "down-in"))
    assert in_price == pytest.approx(_vanilla(100, "call"), abs=5e-10)


@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize("kind", BARRIER_KINDS)
def test_breach_is_inclusive_at_the_barrier(option_type: OptionType, kind: BarrierKind) -> None:
    """Spot exactly AT the barrier counts as touched."""
    H = 90.0 if kind.startswith("down") else 110.0
    i = replace(_inputs(100, H, option_type, kind), S=H)
    expected = 0.0 if kind.endswith("out") else vanilla_price(_bsm(i), option_type)
    assert barrier_price(i) == expected


# --- closed form vs Monte Carlo (discrete monitoring + BGK continuity correction) --------


def _mc_barrier(i: BarrierInputs, paths: int, steps: int, seed: int) -> tuple[float, float]:
    """Discretely-monitored MC price and its standard error, same draws as the TS test.

    Broadie–Glasserman–Kou: to approximate the CONTINUOUS-barrier price with a discrete
    MC, shift the monitored barrier so breaching is as easy as under continuous
    monitoring: down-barrier UP, up-barrier DOWN, by a factor e^(±β·σ·√dt), β ≈ 0.5826.

    Paths are simulated in chunks from :func:`iter_normal_blocks` (the same path-major
    stream as the TS loop) so 60 000 × 200 draws never sit in memory at once.
    """
    dt = i.T / steps
    is_down = i.kind in ("down-in", "down-out")
    is_out = i.kind in ("down-out", "up-out")
    beta = 0.5826
    shift = beta * i.sigma * math.sqrt(dt)
    h_adj = i.H * math.exp(shift) if is_down else i.H * math.exp(-shift)
    df = math.exp(-i.r * i.T)

    chunk = 500
    assert paths % chunk == 0
    total = 0.0
    total2 = 0.0
    for z in islice(iter_normal_blocks(seed, chunk * steps), paths // chunk):
        levels = obs_paths_from_normals(i.S, i.r, i.q, i.sigma, dt, z.reshape(chunk, steps))
        breached = (levels <= h_adj if is_down else levels >= h_adj).any(axis=1)
        s_t = levels[:, -1]
        intrinsic = np.maximum(s_t - i.K, 0.0) if i.type == "call" else np.maximum(i.K - s_t, 0.0)
        alive = ~breached if is_out else breached
        pv = np.where(alive, df * intrinsic, 0.0)
        total += float(pv.sum())
        total2 += float((pv * pv).sum())
    price = total / paths
    stderr = math.sqrt(max(total2 / paths - price * price, 0.0) / paths)
    return price, stderr


# All four knock-OUT types (KI = vanilla − KO follows exactly from parity), spanning both
# the K>H and K<H formula branches:
#   down-out call K>H (A−C), up-out call K<H (A−B+C−D),
#   down-out put  K>H (A−B+C−D), up-out put  K<H (A−C).
MC_CASES = {
    "down-out call": _inputs(100, 90, "call", "down-out"),
    "up-out call": _inputs(100, 120, "call", "up-out"),
    "down-out put": _inputs(100, 90, "put", "down-out"),
    "up-out put": _inputs(100, 110, "put", "up-out"),
    "down-in put": _inputs(100, 90, "put", "down-in"),
}


@pytest.mark.slow
@pytest.mark.parametrize("name", list(MC_CASES))
def test_closed_form_matches_monte_carlo(name: str) -> None:
    i = MC_CASES[name]
    cf = barrier_price(i)
    price, stderr = _mc_barrier(i, 60_000, 200, 0x1234 + int(i.K))
    # within ~4 standard errors plus a small absolute floor for discretisation
    assert abs(cf - price) < 4 * stderr + 0.05


# --- greeks ------------------------------------------------------------------------------


def test_greeks_are_finite_and_gamma_is_large_near_the_barrier() -> None:
    near = barrier_greeks(replace(_inputs(100, 90, "call", "down-out"), S=91))
    far = barrier_greeks(replace(_inputs(100, 90, "call", "down-out"), S=110))
    assert math.isfinite(near.gamma)
    assert abs(near.gamma) > abs(far.gamma)


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_far_barrier_greeks_equal_vanilla_desk_greeks(option_type: OptionType) -> None:
    """With the barrier out of reach a knock-out IS the vanilla, so the bump greeks must
    reproduce the analytic vanilla greeks in the same desk units (vega/rho per point,
    theta per day)."""
    i = _inputs(100, 1, option_type, "down-out")
    got = barrier_greeks(i)
    want = analyze_option(_bsm(i), option_type).reported
    for name in ("price", "delta", "gamma", "vega", "theta", "rho"):
        assert getattr(got, name) == pytest.approx(getattr(want, name), rel=1e-5, abs=1e-8), name


def test_degenerate_vol_returns_nan_like_typescript() -> None:
    """σ → 0 on an up barrier overflows (H/S)^(2μ) (inf in JS); the TS then returns NaN.
    Python must not raise OverflowError."""
    i = replace(_inputs(100, 103, "call", "up-out"), sigma=0.0)
    assert math.isnan(barrier_price(i))


@pytest.mark.parametrize(("field", "value"), [("H", 0.0), ("H", -1.0), ("S", 0.0), ("K", 0.0)])
def test_rejects_non_positive_levels(field: str, value: float) -> None:
    changes: dict[str, Any] = {field: value}
    i = replace(_inputs(100, 90, "call", "down-out"), **changes)
    with pytest.raises(ValueError, match="barrier"):
        barrier_price(i)


@pytest.mark.parametrize(("direction", "H"), [("down", 90.0), ("up", 110.0)])
def test_zero_strike_limit_is_the_prepaid_forward(direction: str, H: float) -> None:
    """K = 0 is rejected, but a strike just above 0 gives the limit the TypeScript returns
    AT K = 0 (see the Raises notes): a zero-strike call is the asset, so in + out is the
    prepaid forward S·e^(−qT), and a zero-strike put is worthless."""
    tiny = 1e-300
    forward = BASE.S * math.exp(-BASE.q * BASE.T)
    kin: BarrierKind = "down-in" if direction == "down" else "up-in"
    kout: BarrierKind = "down-out" if direction == "down" else "up-out"
    knock_in = barrier_price(_inputs(tiny, H, "call", kin))
    knock_out = barrier_price(_inputs(tiny, H, "call", kout))
    assert knock_in > 0
    assert knock_out > 0
    assert knock_in + knock_out == pytest.approx(forward, rel=1e-12)
    for kind in (kin, kout):
        assert barrier_price(_inputs(tiny, H, "put", kind)) == 0.0
