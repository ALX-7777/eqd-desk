"""The Python strategy builder reproduces the TypeScript engine (golden values exported by
``web/scripts/golden/strategy.golden.ts``): preset leg geometry and vols, aggregate and
per-leg analysis (raw + reported greeks), payoff profiles, and leg/position values over
calendar time, for every preset on several grids plus a hand-built mixed-expiry book and
the empty position.

Tolerance policy: every comparison is RELATIVE, measured against the GROSS size of what was
summed to produce the number.

- A single leg's value or greek is one closed form, so no cross-leg netting happens. It is
  compared with plain ``RTOL`` and no absolute floor.
- A position aggregate Σᵢ kᵢ·gᵢ can cancel: a butterfly's delta, a P&L net of premium. The
  last-ulp libm differences between Python and V8 then survive as an ABSOLUTE error of
  order ulp × Σᵢ|kᵢ·gᵢ|, not ulp × |Σᵢ kᵢ·gᵢ|. So the absolute tolerance is
  ``RTOL · Σᵢ|kᵢ·gᵢ|``, which is the per-field gross, in that field's own units.

An absolute floor tied to the spot level (the earlier ``ATOL·max(1, S)``) is the wrong
scale. It fits price and delta, but gamma, speed and color shrink like 1/S and 1/S². At
SPX spot that floor (6.3e-9) exceeded some speed and color values outright, and it
accepted errors of several percent in others. ``test_tolerance_detects_a_one_ppm_error``
pins that regression down.

The gross is computed from the Python legs, which is sound. A wrong term widens the bound
by only RTOL times its own error while adding the full error to |Δ|, so with RTOL ≪ 1 it
can never hide itself.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Iterable, Sequence
from typing import Any

import pytest

from eqd_desk.engine import GREEK_NAMES, BsmInputs, Greeks
from eqd_desk.engine.presets import PRESETS, PresetParams, build_preset
from eqd_desk.engine.reporting import GREEK_UNITS
from eqd_desk.engine.strategy import (
    Leg,
    MarketParams,
    PositionAnalysis,
    analyze_position,
    front_expiry,
    leg_value_at,
    payoff_profile,
    position_premium,
    position_value_at,
)
from tests.parity.golden_io import RTOL, assert_close, load_golden

GOLDEN = load_golden("strategy")
FIELDS = ("price", *GREEK_NAMES)

SENSITIVITY = 1e-6
"""A relative error of 1 ppm in any non-zero compared greek must make the parity check
fail (see ``test_tolerance_detects_a_one_ppm_error``)."""


def skew_term_vol(S0: float) -> Callable[[float, float], float]:
    """Same provider (same operation order) as ``skewTermVol`` in the TS exporter."""
    return lambda K, T: 0.18 - 0.25 * math.log(K / S0) + 0.03 * math.sqrt(T)


def _leg(d: dict[str, Any]) -> Leg:
    return Leg(
        id=d["id"],
        type=d["type"],
        side=d["side"],
        quantity=d["quantity"],
        K=d["K"],
        T=d["T"],
        sigma=d["sigma"],
    )


def _market(d: dict[str, float]) -> MarketParams:
    return MarketParams(S=d["S"], r=d["r"], q=d["q"])


def _gross_atol(terms: Iterable[float]) -> float:
    """Absolute tolerance for a SUM of ``terms``: RTOL × Σ|term|, its gross size. Passed as
    ``atol`` next to the default ``rtol=RTOL``, it bounds |Δ| by RTOL·(gross + |net|)."""
    return RTOL * sum(abs(t) for t in terms)


def _check_single(got: float, expected: float, label: str) -> None:
    """One leg's closed-form value or greek. No netting, so the check is purely relative."""
    assert_close(got, expected, atol=0.0, label=label)


def _check_greeks(
    got: Greeks, expected: dict[str, float], atols: dict[str, float], label: str
) -> None:
    for f in FIELDS:
        assert_close(getattr(got, f), expected[f], atol=atols[f], label=f"{label} {f}")


def _check_analysis(got: PositionAnalysis, expected: dict[str, Any], label: str) -> None:
    # Per-field gross Σ|kᵢ·unitᵢ.f|, in raw units. A reported field is the raw one divided
    # by its reporting divisor (vega ÷100, theta ÷365, ...), and so is its gross.
    raw_atols = {
        f: _gross_atol(la.signed_qty * getattr(la.unit, f) for la in got.legs) for f in FIELDS
    }
    reported_atols = {f: raw_atols[f] / GREEK_UNITS[f].divisor for f in FIELDS}
    assert_close(got.price, expected["price"], atol=raw_atols["price"], label=f"{label} price")
    _check_greeks(got.raw, expected["raw"], raw_atols, f"{label} raw")
    _check_greeks(got.reported, expected["reported"], reported_atols, f"{label} reported")
    for i, want in enumerate(expected["legs"]):
        la = got.legs[i]
        assert la.signed_qty == want["signedQty"], f"{label} leg {i} signedQty"
        assert la.inputs == BsmInputs(**want["inputs"]), f"{label} leg {i} inputs"
        for f in FIELDS:
            _check_single(getattr(la.unit, f), want["unit"][f], f"{label} leg {i} unit {f}")


def _leg_values(legs: Sequence[Leg], S: float, at_t: float, m: MarketParams) -> list[float]:
    return [leg_value_at(leg, S, at_t, m) for leg in legs]


def _check_position(case: dict[str, Any], label: str) -> None:
    """Everything ``positionOut`` exported for one position, recomputed from its legs."""
    legs = [_leg(d) for d in case["legs"]]
    m = _market(case["market"])

    assert front_expiry(legs) == case["frontExpiry"], f"{label} frontExpiry"
    premium_legs = _leg_values(legs, m.S, 0.0, m)
    assert_close(
        position_premium(legs, m),
        case["premium"],
        atol=_gross_atol(premium_legs),
        label=f"{label} premium",
    )

    _check_analysis(analyze_position(legs, m), case["analysis"], label)
    shifted = _market(case["shiftedMarket"])
    _check_analysis(analyze_position(legs, shifted), case["shiftedAnalysis"], f"{label} @0.97S")

    pay = case["payoff"]
    pts = payoff_profile(legs, m, pay["sLo"], pay["sHi"], pay["n"])
    # The spot grid is pure IEEE arithmetic (no libm), so it is bit-identical.
    assert [p.S for p in pts] == pay["S"], f"{label} payoff grid"
    at_front = front_expiry(legs)
    for p, e_exp, e_now in zip(pts, pay["expiryPnl"], pay["nowPnl"], strict=True):
        # P&L = Σ leg values at S − Σ leg values today (the premium): gross is both sums.
        expiry_terms = [*_leg_values(legs, p.S, at_front, m), *premium_legs]
        now_terms = [*_leg_values(legs, p.S, 0.0, m), *premium_legs]
        assert_close(
            p.expiry_pnl,
            e_exp,
            atol=_gross_atol(expiry_terms),
            label=f"{label} expiryPnl S={p.S}",
        )
        assert_close(p.now_pnl, e_now, atol=_gross_atol(now_terms), label=f"{label} nowPnl S={p.S}")

    for v in case["values"]:
        where = f"{label} value S={v['S']} atT={v['atT']}"
        per_leg = _leg_values(legs, v["S"], v["atT"], m)
        total = position_value_at(legs, v["S"], v["atT"], m)
        assert_close(total, v["total"], atol=_gross_atol(per_leg), label=where)
        for leg, got, want in zip(legs, per_leg, v["perLeg"], strict=True):
            _check_single(got, want, f"{where} {leg.id}")


def test_preset_registry() -> None:
    assert [(p.name, p.label) for p in PRESETS] == [
        (d["name"], d["label"]) for d in GOLDEN["presetList"]
    ]


PRESET_CASES: list[dict[str, Any]] = GOLDEN["presets"]


def _case_id(c: dict[str, Any]) -> str:
    p = c["params"]
    return f"{c['name']}@S={p['S']},T={p['baseT']:.4f},w={p['widthPct']},step={p['strikeStep']}"


@pytest.mark.parametrize("case", PRESET_CASES, ids=[_case_id(c) for c in PRESET_CASES])
def test_build_preset_matches(case: dict[str, Any]) -> None:
    p = case["params"]
    legs = build_preset(
        case["name"],
        PresetParams(
            S=p["S"],
            base_t=p["baseT"],
            width_pct=p["widthPct"],
            strike_step=p["strikeStep"],
            vol_for=skew_term_vol(p["S"]),
        ),
    )
    assert len(legs) == len(case["legs"])
    for got, want in zip(legs, case["legs"], strict=True):
        # Geometry is pure arithmetic (JS-compatible rounding): exact.
        assert (got.id, got.type, got.side, got.quantity, got.K, got.T) == (
            want["id"],
            want["type"],
            want["side"],
            want["quantity"],
            want["K"],
            want["T"],
        )
        # The vol goes through log/sqrt: last-ulp libm differences allowed.
        assert_close(got.sigma, want["sigma"], label=f"{want['id']} sigma")


@pytest.mark.parametrize("case", PRESET_CASES, ids=[_case_id(c) for c in PRESET_CASES])
def test_preset_position_matches(case: dict[str, Any]) -> None:
    _check_position(case, _case_id(case))


@pytest.mark.parametrize("key", ["custom", "customAlive"])
def test_hand_built_mixed_expiry_position_matches(key: str) -> None:
    """Mixed expiries, fractional quantities, an already-expired leg (T = 0, priced at the
    T floor by the greeks but at intrinsic by the value functions) and a σ ≈ 0 leg."""
    _check_position(GOLDEN[key], key)


def test_empty_position_matches() -> None:
    e = GOLDEN["empty"]
    m = _market(e["market"])
    assert front_expiry([]) == e["frontExpiry"]
    assert position_premium([], m) == e["premium"]
    _check_analysis(analyze_position([], m), e["analysis"], "empty")
    pay = e["payoff"]
    pts = payoff_profile([], m, pay["sLo"], pay["sHi"], pay["n"])
    assert [(p.S, p.expiry_pnl, p.now_pnl) for p in pts] == list(
        zip(pay["S"], pay["expiryPnl"], pay["nowPnl"], strict=True)
    )


def _bump(g: Greeks, f: str) -> Greeks:
    """``g`` with field ``f`` scaled by (1 + SENSITIVITY)."""
    return dataclasses.replace(g, **{f: getattr(g, f) * (1 + SENSITIVITY)})


SENSITIVITY_CASES: list[tuple[str, dict[str, Any]]] = [
    *((_case_id(c), c) for c in PRESET_CASES),
    ("custom", GOLDEN["custom"]),
    ("customAlive", GOLDEN["customAlive"]),
]


@pytest.mark.parametrize(
    "case", [c for _, c in SENSITIVITY_CASES], ids=[i for i, _ in SENSITIVITY_CASES]
)
def test_tolerance_detects_a_one_ppm_error(case: dict[str, Any]) -> None:
    """Regression test: the tolerance must stay meaningful for every greek, at any spot level.

    The earlier absolute floor ATOL·max(1, S) was 6.3e-9 for every field at SPX spot. That
    allowed errors of 3.5 % in a calendar's aggregate speed, 10 % in a risk reversal's
    reported color and 17 % in one leg's speed. One aggregate speed and one reported color
    were even smaller than the floor, so their checks were vacuous. With gross-scaled
    tolerances, a 1-ppm error in ANY non-zero greek (aggregate raw, aggregate reported, or
    per leg, at spot and at 0.97·spot) must fail the check, and must fail on that field.
    """
    legs = [_leg(d) for d in case["legs"]]
    for market_key, analysis_key in (("market", "analysis"), ("shiftedMarket", "shiftedAnalysis")):
        expected = case[analysis_key]
        good = analyze_position(legs, _market(case[market_key]))
        _check_analysis(good, expected, "probe")  # sanity: the unbumped analysis passes
        for f in FIELDS:
            for which, bad in (
                ("raw", dataclasses.replace(good, raw=_bump(good.raw, f))),
                ("reported", dataclasses.replace(good, reported=_bump(good.reported, f))),
            ):
                if getattr(getattr(good, which), f) == 0.0:
                    continue  # a relative bump of 0 is still 0
                with pytest.raises(AssertionError, match=f"probe {which} {f}:"):
                    _check_analysis(bad, expected, "probe")
            for i in range(len(expected["legs"])):
                la = good.legs[i]
                if getattr(la.unit, f) == 0.0:
                    continue
                bad_legs = list(good.legs)
                bad_legs[i] = dataclasses.replace(la, unit=_bump(la.unit, f))
                bad = dataclasses.replace(good, legs=tuple(bad_legs))
                with pytest.raises(AssertionError, match=f"probe leg {i} unit {f}:"):
                    _check_analysis(bad, expected, "probe")
