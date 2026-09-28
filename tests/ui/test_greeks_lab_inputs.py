"""The greeks lab's input panel spec equals ``InputPanel.tsx``: bounds, steps, the header
displays (as in the React screenshot) and the seed values."""

from __future__ import annotations

import pytest

from eqd_desk.app.ui import greeks_lab_inputs as lab
from eqd_desk.content import GREEK_KEYS
from eqd_desk.data import load_snapshot, seed_inputs

SNAP = load_snapshot()
SEED = seed_inputs(SNAP)


def spec(field: lab.InputField, spot: float = SNAP.spot) -> lab.InputSpec:
    return next(s for s in lab.input_specs(spot, "USD") if s.field == field)


def test_inputs_come_in_panel_order_with_labels_and_symbols() -> None:
    specs = lab.input_specs(SNAP.spot, SNAP.currency)
    assert [s.field for s in specs] == list(lab.INPUT_FIELDS)
    assert [(s.label, s.symbol) for s in specs] == [
        ("Spot", "S"),
        ("Strike", "K"),
        ("Time to expiry", "T"),
        ("Volatility", "σ"),
        ("Rate", "r"),
        ("Dividend yield", "q"),
    ]
    assert [s.key for s in specs] == ["lab.S", "lab.K", "lab.T", "lab.sigma", "lab.r", "lab.q"]


@pytest.mark.parametrize("field", ["S", "K"])
def test_spot_and_strike_span_60_to_140_percent_of_the_snapshot(field: lab.InputField) -> None:
    s = spec(field)
    # Math.round(6312.45 × 0.6) = 3787, Math.round(6312.45 × 1.4) = 8837
    assert (s.min_value, s.max_value, s.step) == (3787.0, 8837.0, 1.0)
    assert s.input_format == "%.2f"


@pytest.mark.parametrize(("spot", "step"), [(6312.45, 1.0), (500.0, 0.5), (150.0, 0.1)])
def test_level_step_follows_the_index_level(spot: float, step: float) -> None:
    assert spec("S", spot).step == step
    assert spec("K", spot).step == step


@pytest.mark.parametrize(
    ("field", "bounds"),
    [
        ("T", (0.003, 2.0, 0.003)),
        ("sigma", (0.02, 1.0, 0.0025)),
        ("r", (-0.02, 0.1, 0.0005)),
        ("q", (0.0, 0.06, 0.0005)),
    ],
)
def test_other_bounds_are_the_react_ones(
    field: lab.InputField, bounds: tuple[float, float, float]
) -> None:
    s = spec(field)
    assert (s.min_value, s.max_value, s.step) == bounds


def test_header_displays_match_the_react_screenshot() -> None:
    specs = {s.field: s for s in lab.input_specs(SNAP.spot, SNAP.currency)}
    shown = {f: specs[f].display(getattr(SEED, f)) for f in lab.INPUT_FIELDS}
    assert shown == {
        "S": "6,312.45 USD",
        "K": "6,300 USD",
        "T": "0.082 y · 30 d",
        "sigma": "14.60%",
        "r": "4.30%",
        "q": "1.30%",
    }


def test_seed_values_roundtrip_to_the_seed_option() -> None:
    values = lab.seed_values(SEED)
    assert values == {
        "lab.S": SEED.S,
        "lab.K": SEED.K,
        "lab.T": SEED.T,
        "lab.sigma": SEED.sigma,
        "lab.r": SEED.r,
        "lab.q": SEED.q,
    }
    assert lab.inputs_from_values(values) == SEED


def test_every_seed_value_is_inside_its_bounds() -> None:
    for s in lab.input_specs(SNAP.spot, SNAP.currency):
        assert s.min_value <= getattr(SEED, s.field) <= s.max_value, s.field


def test_selection_validators_fall_back_to_the_defaults() -> None:
    for key in GREEK_KEYS:
        assert lab.valid_greek(key) == key
    assert lab.valid_greek("zeta") == lab.DEFAULT_GREEK == "delta"
    assert lab.valid_greek(None) == "delta"
    for x in ("S", "sigma", "T"):
        assert lab.valid_x_axis(x) == x
    assert lab.valid_x_axis("K") == lab.DEFAULT_X_AXIS == "S"
