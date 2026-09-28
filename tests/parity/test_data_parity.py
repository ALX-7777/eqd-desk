"""The Python market-data layer reproduces the TypeScript one (golden values exported by
``web/scripts/golden/data.golden.ts``).

Validation and seeding involve no arithmetic beyond one division and a rounding, so they
must match EXACTLY, including the error messages, which render values with JavaScript's
JSON.stringify / String() rules (checked on raw JSON text that both sides parse). The
surface is a handful of flops plus one ``log``, so it gets the shared tight float tolerance.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from eqd_desk.data import (
    DEFAULT_UNDERLYING,
    UNDERLYINGS,
    VOL_FLOOR,
    build_surface,
    default_surface,
    load_history,
    load_snapshot,
    seed_inputs,
    validate_snapshot,
)
from eqd_desk.engine import BsmInputs
from tests.parity.golden_io import assert_close, load_golden

GOLDEN = load_golden("data")


def test_underlying_presets() -> None:
    g = GOLDEN["config"]
    assert g["defaultUnderlying"] == DEFAULT_UNDERLYING
    assert set(g["underlyings"]) == set(UNDERLYINGS)
    for key, ts in g["underlyings"].items():
        cfg = UNDERLYINGS[key]
        assert (cfg.key, cfg.name, cfg.currency) == (ts["key"], ts["name"], ts["currency"])
        assert cfg.index_ticker == ts["indexTicker"]
        assert cfg.vol_index_ticker == ts["volIndexTicker"]
        assert cfg.options_proxy == ts["optionsProxy"]
        assert cfg.default_div_yield == ts["defaultDivYield"]


def test_committed_snapshot_validates_identically() -> None:
    assert load_snapshot().as_dict() == GOLDEN["snapshot"]


@pytest.mark.parametrize("case", GOLDEN["validated"], ids=lambda c: c["label"])
def test_accepted_variants(case: dict[str, Any]) -> None:
    assert validate_snapshot(case["raw"]).as_dict() == case["snapshot"]


@pytest.mark.parametrize("case", GOLDEN["rejected"], ids=lambda c: c["label"])
def test_rejected_variants_with_identical_messages(case: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"^snapshot: ") as err:
        validate_snapshot(case["raw"])
    assert str(err.value) == case["error"]


@pytest.mark.parametrize("case", GOLDEN["validatedText"], ids=lambda c: c["label"])
def test_accepted_json_text_coerces_strings_like_javascript(case: dict[str, Any]) -> None:
    """Same file bytes on both sides: String() coercions (true, 1.0, arrays, objects,
    Infinity) and number narrowing (5000.0, a 301-digit integer literal) must agree."""
    assert validate_snapshot(json.loads(case["text"])).as_dict() == case["snapshot"]


@pytest.mark.parametrize("case", GOLDEN["rejectedText"], ids=lambda c: c["label"])
def test_rejected_json_text_renders_values_like_json_stringify(case: dict[str, Any]) -> None:
    """Error text renders the offending value exactly as JSON.stringify does (JS number
    layout, raw non-ASCII, key order), and huge integer literals are rejected as Infinity
    (ValueError, never OverflowError)."""
    with pytest.raises(ValueError, match=r"^snapshot: ") as err:
        validate_snapshot(json.loads(case["text"]))
    assert str(err.value) == case["error"]


@pytest.mark.parametrize("case", GOLDEN["nonFinite"], ids=lambda c: c["label"])
def test_non_finite_numbers_are_reported_as_null(case: dict[str, Any]) -> None:
    raw = load_snapshot().as_dict()
    *parents, leaf = case["path"]
    target = raw[parents[0]] if parents else raw
    target[leaf] = float(case["value"])
    with pytest.raises(ValueError, match=r"^snapshot: ") as err:
        validate_snapshot(raw)
    assert str(err.value) == case["error"]


def test_non_finite_source_notes() -> None:
    g = GOLDEN["nonFiniteNotes"]
    notes = [float(v) for v in g["values"]]
    raw = {**load_snapshot().as_dict(), "source_notes": notes}
    assert list(validate_snapshot(raw).source_notes) == g["notes"]


def test_seed_inputs() -> None:
    snap = load_snapshot()
    first, *rest = GOLDEN["seeds"]
    assert first["inputs"] == _as_dict(seed_inputs())
    for row in rest:
        custom = validate_snapshot({**snap.as_dict(), "spot": row["spot"]})
        got = _as_dict(seed_inputs(custom, row["step"]))
        assert got == row["inputs"], f"spot={row['spot']} step={row['step']}"


def _as_dict(i: BsmInputs) -> dict[str, float]:
    return {"S": i.S, "K": i.K, "T": i.T, "r": i.r, "q": i.q, "sigma": i.sigma}


def test_vol_floor() -> None:
    assert GOLDEN["volFloor"] == VOL_FLOOR


@pytest.mark.parametrize("case", GOLDEN["surfaces"], ids=lambda c: c["label"])
def test_surface_atm_vol_and_get_vol_grid(case: dict[str, Any]) -> None:
    surface = build_surface(validate_snapshot(case["snapshot"]))
    assert surface.spot == case["spot"]
    for T, expected in zip(case["Ts"], case["atm"], strict=True):
        assert_close(surface.atm_vol(T), expected, label=f"atm_vol({T})")
    for K, row in zip(case["Ks"], case["vol"], strict=True):
        for T, expected in zip(case["Ts"], row, strict=True):
            assert_close(surface.get_vol(K, T), expected, label=f"get_vol({K}, {T})")


def test_default_surface() -> None:
    g, surface, spot = GOLDEN["defaultSurface"], default_surface(), load_snapshot().spot
    Ts = GOLDEN["surfaces"][0]["Ts"]
    assert surface.spot == g["spot"]
    for T, expected in zip(Ts, g["atm"], strict=True):
        assert_close(surface.atm_vol(T), expected, label=f"atm_vol({T})")
    for m, row in zip(GOLDEN["mults"], g["vol"], strict=True):
        for T, expected in zip(Ts, row, strict=True):
            assert_close(surface.get_vol(spot * m, T), expected, label=f"get_vol({m}·S, {T})")


def test_history_series_and_meta() -> None:
    g, history = GOLDEN["history"], load_history()
    assert len(history.series) == g["length"]
    meta = history.meta
    assert {"asof": meta.asof, "source": meta.source, "count": meta.count} == g["meta"]
    for row in g["sampled"]:
        p = history.series[row["index"]]
        assert {"date": p.date, "spot": p.spot, "vix": p.vix} == row["point"]
