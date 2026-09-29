"""Leg editing of the strategy builder: presets and new legs are built exactly as the React
``StrategyBuilder.tsx`` builds them, and table edits convert units as ``LegsEditor.tsx``."""

from __future__ import annotations

import dataclasses
import math

import pytest

from eqd_desk.app.ui.bounds import SPOT_RANGE_FACTORS
from eqd_desk.app.ui.strategy_builder_legs import (
    CALENDAR_BACK_DAYS,
    CUSTOM,
    CUSTOM_LABEL,
    DAYS_LIMITS,
    DEFAULT_PRESET,
    DEFAULT_TENOR_DAYS,
    DEFAULT_WING_PCT,
    LEG_DAYS_MAX,
    LEG_FIELDS,
    MIN_VOL,
    PRESET_LABELS,
    QUANTITY_LIMITS,
    STRIKE_LIMITS,
    TENOR_MAX_DAYS,
    VOL_LIMITS,
    FieldLimits,
    custom_leg_id,
    edit_leg,
    field_values,
    flip_side,
    flip_type,
    leg_button_help,
    leg_display,
    leg_field_label,
    make_preset,
    new_leg,
    remove_leg,
    round2,
    strike_step_for,
    structure_label,
    update_leg,
)
from eqd_desk.data import default_surface, load_snapshot
from eqd_desk.engine.presets import CALENDAR_BACK_OFFSET, PRESETS, PresetParams, build_preset
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


def test_field_values_are_the_displayed_fields_in_table_order() -> None:
    leg = dataclasses.replace(LEG, K=6312.456, T=29.6 / 365, quantity=2)
    values = field_values(leg)
    assert tuple(values) == LEG_FIELDS == ("quantity", "K", "days", "vol")
    assert values == {"quantity": 2, "K": 6312.46, "days": 30, "vol": 16.72}
    # every field round-trips: typing back what is shown keeps the (rounded) value
    for field, shown in values.items():
        assert field_values(edit_leg(leg, field, shown))[field] == shown


def test_labels_and_tooltips_name_the_leg() -> None:
    assert leg_field_label(2, "K") == "Leg 2 strike"
    assert [leg_field_label(1, f) for f in LEG_FIELDS] == [
        "Leg 1 quantity",
        "Leg 1 strike",
        "Leg 1 expiry (days)",
        "Leg 1 vol (%)",
    ]
    assert leg_button_help(3, "side") == "Leg 3: toggle long / short"
    assert leg_button_help(3, "type") == "Leg 3: toggle call / put"
    assert leg_button_help(3, "remove") == "Remove leg 3"


# ------------------------------------------------------------------ field bounds


def test_field_limits_widen_only_to_contain_the_shown_value() -> None:
    days = FieldLimits(lo=1, hi=3650, step=1)
    assert days.around(30) == days  # inside: unchanged
    assert days.around(3710) == FieldLimits(lo=1, hi=3710, step=1)
    assert days.around(0) == FieldLimits(lo=0, hi=3650, step=1)
    vol = FieldLimits(lo=1.0, hi=300.0, step=0.5)
    assert vol.around(470.23) == FieldLimits(lo=1.0, hi=470.23, step=0.5)
    unbounded = FieldLimits(lo=0.01, hi=None, step=5.0)
    assert unbounded.around(1e6) == unbounded


def test_field_limits_match_the_edit_rules() -> None:
    # a field accepts exactly what edit_leg keeps: >= 1 contract, >= 1 day, >= 1 vol point
    assert (QUANTITY_LIMITS.lo, DAYS_LIMITS.lo, VOL_LIMITS.lo) == (1, 1, MIN_VOL * 100)
    assert STRIKE_LIMITS.lo > 0
    assert STRIKE_LIMITS.hi is None
    # integer columns stay integer inputs, the others float inputs
    assert isinstance(QUANTITY_LIMITS.step, int)
    assert isinstance(DAYS_LIMITS.step, int)
    assert isinstance(STRIKE_LIMITS.step, float)
    assert isinstance(VOL_LIMITS.step, float)


def test_the_expiry_field_reaches_the_longest_calendar_back_leg() -> None:
    assert CALENDAR_BACK_DAYS == 60
    assert CALENDAR_BACK_DAYS / 365 == CALENDAR_BACK_OFFSET
    assert LEG_DAYS_MAX == TENOR_MAX_DAYS + CALENDAR_BACK_DAYS == 3710
    back = make_preset(
        "calendar",
        spot=SNAP.spot,
        tenor_days=TENOR_MAX_DAYS,
        wing_pct=5,
        strike_step=25,
        vol_for=SURFACE.get_vol,
    )[1]
    assert leg_display(back).days == LEG_DAYS_MAX == DAYS_LIMITS.hi


def _inside(lo: float, hi: float | None, value: float) -> bool:
    return lo <= value and (hi is None or value <= hi)


@pytest.mark.parametrize("name", [p.name for p in PRESETS])
@pytest.mark.parametrize("spot_factor", SPOT_RANGE_FACTORS)
@pytest.mark.parametrize(("tenor", "wing"), [(1, 1), (TENOR_MAX_DAYS, 45)])
def test_every_preset_value_fits_its_field(
    name: str, spot_factor: float, tenor: int, wing: int
) -> None:
    """No preset, at either end of the spot slider and of the tenor and wing fields, builds
    a leg its row's fields would clamp: the table always shows the leg that is priced."""
    legs = make_preset(
        name,  # type: ignore[arg-type]
        spot=SNAP.spot * spot_factor,
        tenor_days=tenor,
        wing_pct=wing,
        strike_step=25,
        vol_for=SURFACE.get_vol,
    )
    for leg in legs:
        shown = leg_display(leg)
        # contracts, strikes and expiries fit the fixed bounds ...
        assert _inside(QUANTITY_LIMITS.lo, QUANTITY_LIMITS.hi, shown.quantity), leg
        assert _inside(STRIKE_LIMITS.lo, STRIKE_LIMITS.hi, shown.strike), leg
        assert _inside(DAYS_LIMITS.lo, DAYS_LIMITS.hi, shown.days), leg
        # ... and a far wing's smile vol, which can exceed the cap, fits the widened ones
        vol = VOL_LIMITS.around(shown.vol_pct)
        assert _inside(vol.lo, vol.hi, shown.vol_pct), leg


def test_a_steep_wing_vol_is_above_the_usual_cap_and_the_field_widens() -> None:
    # 45 % iron condor: the outer put is struck at 600, where the seed smile gives ~470 %
    condor = make_preset(
        "iron-condor",
        spot=SNAP.spot,
        tenor_days=30,
        wing_pct=45,
        strike_step=25,
        vol_for=SURFACE.get_vol,
    )
    shown = leg_display(condor[0])
    assert shown.strike == 600.0
    assert VOL_LIMITS.hi is not None
    assert shown.vol_pct > VOL_LIMITS.hi
    assert VOL_LIMITS.around(shown.vol_pct).hi == shown.vol_pct


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
