"""Seed snapshot loader, validation and seeded inputs (port of
``web/src/data/__tests__/data.test.ts`` › snapshot loader, plus Python-side extras)."""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Any

import numpy as np
import pytest

from eqd_desk.data import (
    SEED_T,
    SkewParams,
    TermPoint,
    load_snapshot,
    read_snapshot_json,
    seed_inputs,
    validate_snapshot,
)
from eqd_desk.engine import BsmInputs

SNAP = load_snapshot()
BS = chr(92)  # a single backslash, spelled out so escape-heavy expectations stay readable


def _raw(**changes: Any) -> dict[str, Any]:
    """The committed snapshot as raw JSON, with top-level keys replaced (``{...snapshot}``)."""
    return {**SNAP.as_dict(), **changes}


def _raw_without(key: str) -> dict[str, Any]:
    raw = SNAP.as_dict()
    del raw[key]
    return raw


# --------------------------------------------------------------------- ported TS tests


def test_loads_and_validates_the_committed_seed() -> None:
    assert SNAP.spot > 0
    assert SNAP.atm_vol_30d > 0
    assert SNAP.underlying == "spx"
    assert SNAP.skew.atm == pytest.approx(SNAP.atm_vol_30d, abs=5e-7)
    assert len(SNAP.term_structure) > 0


@pytest.mark.parametrize(
    "raw",
    [
        None,
        _raw(spot=-1),
        _raw(atm_vol_30d="x"),
        _raw(r=None),
        _raw_without("r"),
    ],
    ids=["null", "negative spot", "string vol", "r null", "r missing"],
)
def test_rejects_malformed_snapshots(raw: object) -> None:
    with pytest.raises(ValueError, match=r"^snapshot: "):
        validate_snapshot(raw)


def test_seeds_a_sensible_default_option_from_the_snapshot() -> None:
    i = seed_inputs(SNAP)
    assert SNAP.spot == i.S
    assert i.sigma == SNAP.atm_vol_30d
    assert i.r == SNAP.r
    assert i.q == SNAP.q
    assert pytest.approx(30 / 365, abs=5e-10) == i.T
    assert i.K % 25 == 0  # strike snapped to a round level
    assert abs(i.K - SNAP.spot) < 25


# ------------------------------------------------------------------------------ extras


def test_committed_seed_values() -> None:
    """Pin the committed seed so an accidental edit of snapshot.json is noticed."""
    assert SNAP.asof == "2026-06-23"
    assert (SNAP.spot, SNAP.r, SNAP.q, SNAP.realized_vol) == (6312.45, 0.043, 0.013, 0.1118)
    assert SNAP.skew == SkewParams(atm=0.146, slope=-0.48, curv=0.62)
    assert SNAP.term_structure[0] == TermPoint(t=0.0833, atm_iv=0.139)
    assert [p.t for p in SNAP.term_structure] == sorted(p.t for p in SNAP.term_structure)
    assert SNAP.tickers.vol_ticker == "^VIX"
    assert SNAP.currency == "USD"
    assert len(SNAP.source_notes) == 3


def test_as_dict_is_the_inverse_of_validation() -> None:
    assert SNAP.as_dict() == read_snapshot_json()
    assert validate_snapshot(SNAP.as_dict()) == SNAP


def test_loader_is_cached_and_the_result_immutable_and_hashable() -> None:
    assert load_snapshot() is load_snapshot()
    with pytest.raises(dataclasses.FrozenInstanceError):
        SNAP.spot = 1.0  # type: ignore[misc]
    assert isinstance(SNAP.term_structure, tuple)
    assert hash(SNAP) == hash(validate_snapshot(read_snapshot_json()))


def test_read_snapshot_json_returns_a_fresh_object() -> None:
    raw = read_snapshot_json()
    raw["spot"] = -1
    assert read_snapshot_json()["spot"] == SNAP.spot


def test_skew_atm_defaults_to_the_vol_index_anchor() -> None:
    for skew in ({"slope": -0.3, "curv": 0.4}, {"atm": None, "slope": -0.3, "curv": 0.4}):
        s = validate_snapshot(_raw(skew=skew))
        assert s.skew == SkewParams(atm=SNAP.atm_vol_30d, slope=-0.3, curv=0.4)


def test_optional_fields_default() -> None:
    s = validate_snapshot(
        {"spot": 5000, "r": 0, "q": 0, "atm_vol_30d": 1, "skew": {"slope": 0, "curv": 0}}
    )
    assert (s.asof, s.underlying, s.name, s.currency) == ("", "", "", "")
    assert s.realized_vol is None
    assert s.term_structure == ()
    assert s.source_notes == ()
    assert (s.tickers.index_ticker, s.tickers.vol_ticker, s.tickers.options_proxy) == ("", "", "")
    assert isinstance(s.spot, float)  # ints are widened
    # non-list term structure / notes are ignored (as in the TS `Array.isArray` guard)
    s2 = validate_snapshot(_raw(term_structure="abc", source_notes={"a": 1}, tickers=None))
    assert s2.term_structure == ()
    assert s2.source_notes == ()
    assert s2.tickers.index_ticker == ""


def test_numpy_floats_are_accepted() -> None:
    s = validate_snapshot(_raw(spot=np.float64(5000.5)))
    assert s.spot == 5000.5
    assert type(s.spot) is float


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"spot": 0}, "snapshot: spot must be > 0"),
        ({"atm_vol_30d": -0.1}, "snapshot: atm_vol_30d must be > 0"),
        ({"spot": "6000"}, 'expected finite number at "spot", got "6000"'),
        ({"spot": True}, 'expected finite number at "spot", got true'),
        # JSON.stringify(NaN / ±Infinity) is "null", so that is what TS reports
        ({"spot": math.nan}, 'snapshot: expected finite number at "spot", got null'),
        ({"r": math.inf}, 'snapshot: expected finite number at "r", got null'),
        ({"q": -math.inf}, 'snapshot: expected finite number at "q", got null'),
        ({"r": 10**400}, 'snapshot: expected finite number at "r", got null'),  # int > double
        ({"q": None}, 'expected finite number at "q", got null'),
        ({"realized_vol": "x"}, 'expected finite number at "realized_vol", got "x"'),
        ({"skew": None}, 'expected finite number at "skew.slope", got undefined'),
        ({"skew": {"atm": 0.2, "slope": -0.3}}, 'at "skew.curv", got undefined'),
        ({"term_structure": [{"t": 0.1, "atm_iv": 0.2}, {"t": 0.5}]}, "term_structure[1].atm_iv"),
        ({"term_structure": [None]}, 'at "term_structure[0].t", got undefined'),
    ],
)
def test_rejection_messages_name_the_offending_field(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=r"^snapshot: ") as err:
        validate_snapshot(_raw(**changes))
    assert message in str(err.value)


def _rejection(raw: object) -> str:
    with pytest.raises(ValueError, match=r"^snapshot: ") as err:
        validate_snapshot(raw)
    return str(err.value)


def _text_with(key: str, value_text: str) -> Any:
    """Parse the committed snapshot's JSON text with ``key``'s value replaced by raw JSON
    ``value_text``: exactly what the file on disk would give the loader."""
    return json.loads(json.dumps(_raw(**{key: "@RAW@"})).replace('"@RAW@"', value_text))


@pytest.mark.parametrize(
    ("value_text", "shown"),
    [
        # numbers print as JavaScript prints them, not as Python's repr
        ("[5.0]", "[5]"),
        ("[1e-7]", "[1e-7]"),
        (
            "[1e21, 1e20, 0.000001, -0.0, 0.1, 1.5e300, 123456789012345678901234]",
            "[1e+21,100000000000000000000,0.000001,0,0.1,1.5e+300,1.2345678901234569e+23]",
        ),
        ("[1e400, -1e400, 1" + "0" * 400 + "]", "[null,null,null]"),  # Infinity → null
        # strings keep non-ASCII characters; only quotes, backslashes and controls escape
        ('"€ é 😀"', '"€ é 😀"'),
        # (BS = one backslash) quote, backslash, newline, tab, U+0001 escape; DEL does not
        (json.dumps(f'a"b{BS}c\n\t\x01\x7f'), f'"a{BS}"b{BS}{BS}c{BS}n{BS}t{BS}u0001\x7f"'),
        (r'"\ud800"', r'"\ud800"'),  # lone surrogate
        # object keys in JavaScript property order: array indices first, ascending
        (
            '{"b": 1, "10": 2, "2": 3, "a": [true, null], "01": 4, "4294967295": 5}',
            '{"2":3,"10":2,"b":1,"a":[true,null],"01":4,"4294967295":5}',
        ),
        ("false", "false"),
    ],
)
def test_error_messages_render_values_like_json_stringify(value_text: str, shown: str) -> None:
    assert _rejection(_text_with("q", value_text)) == (
        f'snapshot: expected finite number at "q", got {shown}'
    )


def test_huge_integer_literal_is_a_value_error_not_an_overflow() -> None:
    """``json`` keeps ``1000…0`` (401 digits) exact; TS's JSON.parse reads it as Infinity."""
    for key in ("spot", "r", "atm_vol_30d"):
        assert _rejection(_text_with(key, "1" + "0" * 400)).endswith(f'"{key}", got null')
    big_step = 10**400
    with pytest.raises(ValueError, match="strike_step"):
        seed_inputs(SNAP, big_step)


def test_strings_are_coerced_like_javascript_string() -> None:
    raw = json.loads(
        json.dumps(
            _raw(
                asof="@1@",
                underlying="@2@",
                name="@3@",
                currency="@4@",
                tickers="@5@",
                source_notes="@6@",
            )
        )
        .replace('"@1@"', "true")
        .replace('"@2@"', "false")
        .replace('"@3@"', "1.0")
        .replace('"@4@"', "[1, [2, null], 3.50]")
        .replace('"@5@"', '{"index_ticker": 5.0, "vol_ticker": [], "options_proxy": {"a": 1}}')
        .replace(
            '"@6@"',
            '[true, 1.0, null, 1e21, 1e-7, 0.000001, -0.0, [1, [2, null]], {"a": 1}, "é", 1e400]',
        )
    )
    s = validate_snapshot(raw)
    assert (s.asof, s.underlying, s.name, s.currency) == ("true", "false", "1", "1,2,,3.5")
    assert (s.tickers.index_ticker, s.tickers.vol_ticker, s.tickers.options_proxy) == (
        "5",
        "",
        "[object Object]",
    )
    assert s.source_notes == (
        "true",
        "1",
        "null",
        "1e+21",
        "1e-7",
        "0.000001",
        "0",
        "1,2,",
        "[object Object]",
        "é",
        "Infinity",
    )
    nonfinite = validate_snapshot(_raw(source_notes=[math.nan, math.inf, -math.inf]))
    assert nonfinite.source_notes == ("NaN", "Infinity", "-Infinity")


def test_missing_key_is_reported_as_undefined() -> None:
    with pytest.raises(ValueError, match='at "spot", got undefined'):
        validate_snapshot(_raw_without("spot"))


@pytest.mark.parametrize("raw", [None, "snapshot", 42, True, [1, 2]])
def test_non_objects_are_rejected(raw: object) -> None:
    with pytest.raises(ValueError, match=r"^snapshot: not an object$"):
        validate_snapshot(raw)


def test_seed_inputs_defaults_to_the_committed_snapshot() -> None:
    i = seed_inputs()
    assert i == seed_inputs(SNAP)
    assert i == BsmInputs(S=6312.45, K=6300.0, T=SEED_T, r=0.043, q=0.013, sigma=0.146)


@pytest.mark.parametrize(
    ("spot", "step", "strike"),
    [
        # Ties (x.5 steps) go UP, like JavaScript Math.round; Python's round() would send
        # 252.5 and 254.5 DOWN to the even neighbour.
        (6312.5, 25, 6325.0),  # 252.5 steps
        (6287.5, 25, 6300.0),  # 251.5 steps
        (6337.5, 25, 6350.0),  # 253.5 steps
        (6362.5, 25, 6375.0),  # 254.5 steps
        (6312.45, 1, 6312.0),
        (6312.45, 100, 6300.0),
        (12.5, 25, 25.0),
        (7.49, 25, 0.0),  # a sub-step spot snaps to 0 (as in TS): pick a finer step
    ],
)
def test_seed_strike_snaps_like_javascript(spot: float, step: float, strike: float) -> None:
    s = dataclasses.replace(SNAP, spot=spot)
    assert strike == seed_inputs(s, step).K


@pytest.mark.parametrize("step", [0, -25, math.nan, math.inf])
def test_seed_inputs_rejects_a_bad_strike_step(step: float) -> None:
    with pytest.raises(ValueError, match="strike_step"):
        seed_inputs(SNAP, step)
