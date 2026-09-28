"""Static implied-vol surface (port of ``web/src/data/__tests__/data.test.ts`` › vol surface,
plus Python-side extras: the T floor, the vol floor, and finite-difference checks that the
surface's ATM skew and curvature are exactly the snapshot's ``slope`` and ``2·curv``)."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from eqd_desk.data import (
    T_MIN,
    VOL_FLOOR,
    MarketSnapshot,
    SkewParams,
    SnapshotVolSurface,
    TermPoint,
    VolSurface,
    build_surface,
    default_surface,
    load_snapshot,
)

SNAP = load_snapshot()
SURFACE: VolSurface = build_surface(SNAP)  # static check: the concrete class meets the protocol


def _close(n: int) -> float:
    """Tolerance of vitest ``toBeCloseTo(x, n)``: |a − b| < 0.5·10⁻ⁿ."""
    return 0.5 * 10.0**-n


# --------------------------------------------------------------------- ported TS tests


def test_atm_term_structure_interpolates_and_clamps() -> None:
    ts = SNAP.term_structure
    # exact at a knot
    assert SURFACE.atm_vol(ts[0].t) == pytest.approx(ts[0].atm_iv, abs=_close(9))
    # flat extrapolation beyond the ends
    assert SURFACE.atm_vol(0.0001) == pytest.approx(ts[0].atm_iv, abs=_close(9))
    assert SURFACE.atm_vol(50) == pytest.approx(ts[-1].atm_iv, abs=_close(9))
    # interpolated strictly between two knots
    mid = SURFACE.atm_vol((ts[0].t + ts[1].t) / 2)
    assert min(ts[0].atm_iv, ts[1].atm_iv) <= mid <= max(ts[0].atm_iv, ts[1].atm_iv)


def test_atm_strike_returns_the_atm_vol() -> None:
    T = 0.25
    assert SURFACE.get_vol(SNAP.spot, T) == pytest.approx(SURFACE.atm_vol(T), abs=_close(9))


def test_skew_slopes_downward_in_strike() -> None:
    T = 0.25
    low_k = SURFACE.get_vol(SNAP.spot * 0.95, T)
    atm_k = SURFACE.get_vol(SNAP.spot, T)
    high_k = SURFACE.get_vol(SNAP.spot * 1.05, T)
    assert low_k > atm_k
    assert high_k < atm_k


@pytest.mark.parametrize("mult", [0.5, 0.8, 1, 1.2, 2, 5])
def test_never_returns_vol_below_the_floor(mult: float) -> None:
    assert SURFACE.get_vol(SNAP.spot * mult, 0.1) >= VOL_FLOOR


def test_can_be_built_from_a_custom_snapshot() -> None:
    custom = replace(
        SNAP,
        spot=5000,
        atm_vol_30d=0.2,
        skew=SkewParams(atm=0.2, slope=-0.5, curv=0.5),
        term_structure=(TermPoint(t=0.25, atm_iv=0.2),),
    )
    s = build_surface(custom)
    assert s.spot == 5000
    assert s.get_vol(5000, 0.25) == pytest.approx(0.2, abs=_close(9))


# ------------------------------------------------------------------------------ extras


def test_linear_interpolation_value() -> None:
    a, b = SNAP.term_structure[0], SNAP.term_structure[1]
    assert SURFACE.atm_vol((a.t + b.t) / 2) == pytest.approx((a.atm_iv + b.atm_iv) / 2, rel=1e-14)
    w = 0.3
    T = a.t + w * (b.t - a.t)
    assert SURFACE.atm_vol(T) == pytest.approx(a.atm_iv + w * (b.atm_iv - a.atm_iv), rel=1e-14)


def test_term_structure_is_continuous_at_every_knot() -> None:
    eps = 1e-9
    for p in SNAP.term_structure:
        assert SURFACE.atm_vol(p.t) == pytest.approx(p.atm_iv, abs=1e-15)
        assert SURFACE.atm_vol(p.t - eps) == pytest.approx(p.atm_iv, abs=1e-9)
        assert SURFACE.atm_vol(p.t + eps) == pytest.approx(p.atm_iv, abs=1e-9)


def test_get_vol_is_the_quadratic_in_log_moneyness() -> None:
    sk = SNAP.skew
    for mult in (0.7, 0.9, 1.0, 1.1, 1.3):
        for T in (0.05, 0.25, 0.8, 3.0):
            k = math.log(mult)
            expected = SURFACE.atm_vol(T) + sk.slope * k + sk.curv * k * k
            assert SURFACE.get_vol(SNAP.spot * mult, T) == pytest.approx(expected, rel=1e-12)


def test_fd_atm_skew_and_curvature_match_the_snapshot() -> None:
    """Central differences of σ(k) in log-strike at k = 0: ∂σ/∂k = slope, ∂²σ/∂k² = 2·curv.

    This is what "slope" and "curv" MEAN on a desk: the ATM skew (vol points per unit of
    log-moneyness) and the smile's convexity.
    """
    h, T = 1e-3, 0.25
    up = SURFACE.get_vol(SNAP.spot * math.exp(h), T)
    mid = SURFACE.get_vol(SNAP.spot, T)
    dn = SURFACE.get_vol(SNAP.spot * math.exp(-h), T)
    assert (up - dn) / (2 * h) == pytest.approx(SNAP.skew.slope, rel=1e-8)
    assert (up - 2 * mid + dn) / (h * h) == pytest.approx(2 * SNAP.skew.curv, rel=1e-6)


def test_tenor_is_floored_at_t_min() -> None:
    snap = replace(SNAP, term_structure=(TermPoint(0.0, 0.1), TermPoint(1.0, 0.2)))
    s = build_surface(snap)
    floored = 0.1 + T_MIN * (0.2 - 0.1)
    for T in (-1.0, 0.0, 1e-9, T_MIN):
        assert s.atm_vol(T) == pytest.approx(floored, rel=1e-15)
        assert s.get_vol(snap.spot, T) == pytest.approx(floored, rel=1e-15)
    assert s.atm_vol(2 * T_MIN) > floored


def test_empty_term_structure_uses_the_30d_anchor_everywhere() -> None:
    s = build_surface(replace(SNAP, term_structure=()))
    for T in (0.0, 0.1, 1.0, 10.0):
        assert s.atm_vol(T) == SNAP.atm_vol_30d


def test_vol_floor_binds_for_tiny_atm_and_concave_wings() -> None:
    tiny = replace(
        SNAP,
        atm_vol_30d=0.005,
        skew=SkewParams(0.005, 0.0, 0.0),
        term_structure=(TermPoint(0.25, 0.005),),
    )
    assert build_surface(tiny).atm_vol(0.25) == VOL_FLOOR
    assert build_surface(tiny).get_vol(tiny.spot, 0.25) == VOL_FLOOR
    concave = build_surface(replace(SNAP, skew=SkewParams(0.146, -0.5, -2.0)))
    assert concave.get_vol(SNAP.spot * 5, 0.25) == VOL_FLOOR
    assert concave.get_vol(SNAP.spot, 0.25) > VOL_FLOOR


@pytest.mark.parametrize("K", [0.0, -100.0, math.nan, math.inf])
def test_get_vol_rejects_a_non_positive_or_non_finite_strike(K: float) -> None:
    with pytest.raises(ValueError, match="strike K"):
        SURFACE.get_vol(K, 0.25)


def test_default_surface_is_cached_and_built_from_the_seed() -> None:
    assert default_surface() is default_surface()
    assert default_surface() == build_surface(SNAP) == build_surface()
    assert isinstance(default_surface(), SnapshotVolSurface)
    assert default_surface().snapshot is SNAP
    assert hash(default_surface()) == hash(build_surface(SNAP))


def test_surface_tracks_its_own_snapshot() -> None:
    other: MarketSnapshot = replace(SNAP, spot=SNAP.spot * 2)
    s = build_surface(other)
    assert s.spot == other.spot
    assert s.get_vol(other.spot, 0.25) == pytest.approx(s.atm_vol(0.25), abs=1e-15)
