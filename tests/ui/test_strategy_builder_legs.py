"""Leg editing of the strategy builder: presets and new legs are built exactly as the React
``StrategyBuilder.tsx`` builds them, and table edits convert units as ``LegsEditor.tsx``."""

from __future__ import annotations

import dataclasses
import math

import pytest

from eqd_desk.app.ui.strategy_builder_legs import (
    CUSTOM,
    CUSTOM_LABEL,
    DEFAULT_PRESET,
    DEFAULT_TENOR_DAYS,
    DEFAULT_WING_PCT,
    MIN_VOL,
    PRESET_LABELS,
    custom_leg_id,
    edit_leg,
    flip_side,
    flip_type,
    leg_display,
    make_preset,
    new_leg,
    remove_leg,
    round2,
    strike_step_for,
    structure_label,
    update_leg,
)
from eqd_desk.data import default_surface, load_snapshot
from eqd_desk.engine.presets import PRESETS, PresetParams, build_preset
from eqd_desk.engine.strategy import Leg

SNAP = load_snapshot()
SURFACE = default_surface()


def flat_vol(K: float, T: float) -> float:
    return 0.2


LEG = Leg(id="x", type="call", side="long", quantity=1, K=6300.0, T=30 / 365, sigma=0.1672424)


# ------------------------------------------------------------------ geometry


@pytest.mark.parametrize(
    ("spot", "step"),
    [(6312.45, 25.0), (2000.0, 25.0), (1999.99, 5.0), (500.0, 5.0), (200.0, 5.0), (199.9, 1.0)],
)
def test_strike_step_for_matches_react(spot: float, step: float) -> None:
    assert strike_step_for(spot) == step


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (16.724248743022110, 16.72),
        (13.995005191021004, 14.0),  # displayed as "14" in the React field
        (11.725126017395042, 11.73),
        (5975.0, 5975.0),
        (1.005, 1.0),  # 1.005 * 100 = 100.49999999999999 in binary: JS rounds down too
        (-2.345, -2.35),  # -2.345 * 100 = -234.50000000000003: not a tie, as in JS
        (-0.125, -0.12),  # Math.round(-12.5) = -12: ties go toward +inf
        (0.125, 0.13),
    ],
)
def test_round2_is_math_round_based(x: float, expected: float) -> None:
    assert round2(x) == expected


def test_default_structure_constants() -> None:
    assert (DEFAULT_PRESET, DEFAULT_TENOR_DAYS, DEFAULT_WING_PCT) == ("butterfly", 30, 5)
    assert list(PRESET_LABELS) == [p.name for p in PRESETS]
    assert structure_label("butterfly") == "Butterfly"
    assert structure_label("iron-condor") == "Iron condor"
    assert structure_label(CUSTOM) == CUSTOM_LABEL == "Custom structure"


# ------------------------------------------------------------------ building


def test_default_butterfly_is_the_react_one() -> None:
    legs = make_preset(
        "butterfly",
        spot=SNAP.spot,
        tenor_days=30,
        wing_pct=5,
        strike_step=25,
        vol_for=SURFACE.get_vol,
    )
    assert [(leg.side, leg.quantity, leg.K) for leg in legs] == [
        ("long", 1, 5975.0),
        ("short", 2, 6300.0),
        ("long", 1, 6625.0),
    ]
    assert [leg.id for leg in legs] == ["butterfly-0", "butterfly-1", "butterfly-2"]
    for leg in legs:
        assert leg.T == 30 / 365
        assert leg.sigma == SURFACE.get_vol(leg.K, leg.T)


@pytest.mark.parametrize("name", [p.name for p in PRESETS])
@pytest.mark.parametrize(("tenor", "wing"), [(30, 5), (7, 1), (365, 12)])
def test_make_preset_equals_engine_build_preset(name: str, tenor: int, wing: int) -> None:
    ours = make_preset(
        name,  # type: ignore[arg-type]
        spot=6012.3,
        tenor_days=tenor,
        wing_pct=wing,
        strike_step=25,
        vol_for=SURFACE.get_vol,
    )
    engine = build_preset(
        name,  # type: ignore[arg-type]
        PresetParams(
            S=6012.3,
            base_t=tenor / 365,
            width_pct=wing / 100,
            strike_step=25,
            vol_for=SURFACE.get_vol,
        ),
    )
    assert ours == tuple(engine)


def test_wing_percent_is_the_same_double_as_react() -> None:
    # React stores widthPct = Math.max(1, v) / 100: 5 / 100 is the literal 0.05 exactly.
    assert DEFAULT_WING_PCT / 100 == 0.05


def test_new_leg_is_react_add_leg() -> None:
    leg = new_leg(custom_leg_id(3), spot=SNAP.spot, tenor_days=45, strike_step=25, vol_for=flat_vol)
    assert leg == Leg(
        id="custom-3", type="call", side="long", quantity=1, K=6300.0, T=45 / 365, sigma=0.2
    )
    # the vol comes from the surface at the leg's own strike and expiry
    leg2 = new_leg("custom-0", spot=6337.6, tenor_days=30, strike_step=25, vol_for=SURFACE.get_vol)
    assert leg2.K == 6350.0
    assert leg2.sigma == SURFACE.get_vol(6350.0, 30 / 365)


def test_new_leg_rounds_ties_up_like_math_round() -> None:
    leg = new_leg("custom-0", spot=6312.5, tenor_days=30, strike_step=25, vol_for=flat_vol)
    assert leg.K == 6325.0  # 252.5 → 253 (Python's round() would give 252 → 6300)


# ------------------------------------------------------------------ display


def test_leg_display_rounds_like_the_react_fields() -> None:
    shown = leg_display(dataclasses.replace(LEG, K=6312.456, T=29.6 / 365, quantity=2))
    assert shown.quantity == 2
    assert shown.strike == 6312.46
    assert shown.days == 30
    assert shown.vol_pct == 16.72
    assert isinstance(shown.quantity, int)
    assert isinstance(shown.days, int)


# ------------------------------------------------------------------ edits


@pytest.mark.parametrize(
    ("raw", "expected"), [(3, 3), (2.5, 3), (2.4, 2), (0, 1), (-4, 1), (None, 1), (math.nan, 1)]
)
def test_edit_quantity(raw: float | None, expected: int) -> None:
    assert edit_leg(LEG, "quantity", raw).quantity == expected


def test_edit_strike_keeps_everything_else() -> None:
    edited = edit_leg(LEG, "K", 6325.0)
    assert edited == dataclasses.replace(LEG, K=6325.0)
    assert edit_leg(LEG, "K", None) == LEG
    assert edit_leg(LEG, "K", math.inf) == LEG


@pytest.mark.parametrize("raw", [0.0, -100.0])
def test_non_positive_strike_is_ignored(raw: float) -> None:
    assert edit_leg(LEG, "K", raw) == LEG


@pytest.mark.parametrize(("raw", "days"), [(45, 45), (1, 1), (0, 1), (-3, 1), (7.5, 7.5)])
def test_edit_days_stores_a_year_fraction(raw: float, days: float) -> None:
    assert edit_leg(LEG, "days", raw).T == days / 365


def test_edit_days_without_a_number_keeps_the_expiry() -> None:
    assert edit_leg(LEG, "days", None).T == pytest.approx(LEG.T, rel=1e-15)


@pytest.mark.parametrize(("raw", "sigma"), [(16.5, 0.165), (20, 0.2), (1, 0.01), (0.5, MIN_VOL)])
def test_edit_vol_stores_a_decimal(raw: float, sigma: float) -> None:
    assert edit_leg(LEG, "vol", raw).sigma == sigma


def test_edit_vol_without_a_number_keeps_the_vol() -> None:
    assert edit_leg(LEG, "vol", None).sigma == pytest.approx(LEG.sigma, rel=1e-15)


def test_toggles() -> None:
    assert flip_side(LEG).side == "short"
    assert flip_side(flip_side(LEG)) == LEG
    assert flip_type(LEG).type == "put"
    assert flip_type(flip_type(LEG)) == LEG


def test_update_and_remove_by_id() -> None:
    a = dataclasses.replace(LEG, id="a")
    b = dataclasses.replace(LEG, id="b", K=6400.0)
    legs = (a, b)
    assert update_leg(legs, "b", flip_side) == (a, flip_side(b))
    assert update_leg(legs, "zzz", flip_side) == legs
    assert remove_leg(legs, "a") == (b,)
    assert remove_leg(legs, "zzz") == legs
    assert remove_leg((a,), "a") == ()
