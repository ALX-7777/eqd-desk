"""The Python exotics reproduce the TypeScript engine (golden values exported by
``web/scripts/golden/exotics.golden.ts``).

Closed forms (barriers, digitals, variance swaps) match to ~1e-10 relative. The seeded
Monte Carlo (autocallable, GBM paths) consumes the SAME draws as the TypeScript, so it
matches to the same tolerance, with every autocall / capital-loss count identical.

Bump greeks divide price differences by the bump size (by its square for gamma), which
amplifies the last-ulp differences between the two maths libraries. Their tolerance is
therefore the price noise ``eps`` propagated through each stencil (see
:func:`_greek_atol`).
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from eqd_desk.engine import BsmInputs, OptionType
from eqd_desk.engine import price as vanilla_price
from eqd_desk.engine.exotics import (
    AutocallInputs,
    AutocallResult,
    BarrierInputs,
    DigitalInputs,
    ExoticGreeks,
    PriceFn,
    VarSwapInputs,
    VolFn,
    asset_or_nothing_price,
    autocall_greeks,
    barrier_greeks,
    barrier_price,
    call_spread_replication,
    cash_or_nothing_price,
    digital_greeks,
    make_normal,
    mulberry32,
    numeric_greeks,
    price_autocall,
    price_autocall_loop,
    price_variance_swap,
    simulate_obs_path,
    simulate_obs_paths,
)
from tests.parity.golden_io import assert_close, load_golden

GOLDEN = load_golden("exotics")


def _f(x: float | str) -> float:
    """Golden numbers; non-finite values are stored as strings ("NaN", "Infinity")."""
    return float(x)


def _greek_atol(name: str, eps: float, S: float, T: float) -> float:
    """Absolute tolerance of a bump greek given an absolute price noise ``eps``.

    Mirrors the stencils of ``numeric_greeks``: first differences divide by 2h, gamma's
    second difference (1, −2, 1) by h², and the reported units divide vega/rho by 100 and
    theta by 365.
    """
    h_s = 1e-4 * S
    h_t = min(1e-5, T / 2)
    return {
        "price": eps,
        "delta": eps / h_s,
        "gamma": 4 * eps / (h_s * h_s),
        "vega": eps / 1e-4 / 100,
        "theta": eps / h_t / 365 if h_t > 0 else 0.0,
        "rho": eps / 1e-6 / 100,
    }[name]


def _assert_greeks(
    got: ExoticGreeks, want: dict[str, Any], *, eps: float, S: float, T: float, label: str
) -> None:
    got_d = got.as_dict()
    assert set(got_d) == set(want)
    for name, expected in want.items():
        assert_close(
            got_d[name],
            _f(expected),
            atol=_greek_atol(name, eps, S, T),
            label=f"{name} {label}",
        )


# --- barriers --------------------------------------------------------------------------


def _barrier(d: dict[str, Any]) -> BarrierInputs:
    return BarrierInputs(
        S=d["S"], K=d["K"], T=d["T"], r=d["r"], q=d["q"], sigma=d["sigma"],
        type=d["type"], H=d["H"], kind=d["kind"],
    )  # fmt: skip


def test_barrier_price_grid() -> None:
    """Every kind × call/put × K on both sides of H × spots straddling / at the barrier."""
    g = GOLDEN["barrier"]
    for row in g["grid"]:
        i = _barrier({**g["base"], **row})
        assert_close(barrier_price(i), _f(row["price"]), atol=1e-13 * i.S, label=str(row))


def test_barrier_price_market_edges() -> None:
    """T and σ floors, negative carry, high vol; σ = 0 edges are NaN in both engines."""
    n_nan = 0
    for row in GOLDEN["barrier"]["edges"]:
        got = barrier_price(_barrier(row))
        n_nan += math.isnan(got)
        assert_close(got, _f(row["price"]), atol=1e-13 * row["S"], label=str(row))
    assert n_nan > 0  # the degenerate-vol NaN branch is really exercised


def test_barrier_greeks() -> None:
    for row in GOLDEN["barrier"]["greeks"]:
        i = _barrier(row["inputs"])
        _assert_greeks(
            barrier_greeks(i), row["greeks"], eps=1e-13 * i.S, S=i.S, T=i.T, label=str(i)
        )


# --- digitals --------------------------------------------------------------------------


def _digital(d: dict[str, Any]) -> DigitalInputs:
    return DigitalInputs(
        S=d["S"], K=d["K"], T=d["T"], r=d["r"], q=d["q"], sigma=d["sigma"],
        type=d["type"], cash=d["cash"],
    )  # fmt: skip


def test_digital_prices() -> None:
    for row in GOLDEN["digital"]["prices"]:
        i = _digital(row["inputs"])
        assert_close(cash_or_nothing_price(i), _f(row["cash"]), label=f"cash {i}")
        assert_close(
            asset_or_nothing_price(i), _f(row["asset"]), atol=1e-13 * i.S, label=f"asset {i}"
        )


def test_digital_greeks() -> None:
    for row in GOLDEN["digital"]["greeks"]:
        i = _digital(row["inputs"])
        _assert_greeks(
            digital_greeks(i), row["greeks"], eps=1e-13 * i.S, S=i.S, T=i.T, label=str(i)
        )


def test_call_spread_replication() -> None:
    for row in GOLDEN["digital"]["replication"]:
        i = _digital(row["inputs"])
        w = max(row["width"], 1e-9)
        # (Q/Δ)·(C(K−Δ/2) − C(K+Δ/2)): vanilla-price noise is amplified by 1/Δ.
        assert_close(
            call_spread_replication(i, row["width"]),
            _f(row["price"]),
            atol=1e-13 * i.S / w,
            label=f"w={row['width']} {i}",
        )


# --- variance swap ---------------------------------------------------------------------


def _linear_skew(K: float) -> float:
    return max(0.05, 0.2 - 0.0015 * (K - 100))


def _smile(K: float) -> float:
    k = math.log(K / 100)
    return 0.2 - 0.12 * k + 0.25 * k * k


def _spx_skew(K: float) -> float:
    k = math.log(K / 6312.45)
    return max(0.05, 0.146 - 0.15 * k + 0.3 * k * k)


SMILES: dict[str, VolFn] = {
    "flat15": lambda _K: 0.15,
    "flat20": lambda _K: 0.2,
    "flat30": lambda _K: 0.3,
    "linearSkew": _linear_skew,
    "smile": _smile,
    "spxSkew": _spx_skew,
}


def test_variance_swap() -> None:
    for row in GOLDEN["varswap"]:
        c = row["inputs"]
        res = price_variance_swap(
            VarSwapInputs(
                S=c["S"], T=c["T"], r=c["r"], q=c["q"], vol_for=SMILES[c["smile"]],
                lo_mult=c.get("loMult", 0.3), hi_mult=c.get("hiMult", 3.0),
                n_strikes=c.get("nStrikes", 400),
            )
        )  # fmt: skip
        label = str(c)
        assert_close(res.fair_variance, row["fairVariance"], label=f"fairVariance {label}")
        assert_close(res.fair_vol, row["fairVol"], label=f"fairVol {label}")
        assert_close(res.forward, row["forward"], label=f"forward {label}")
        assert_close(res.atm_vol, row["atmVol"], label=f"atmVol {label}")
        assert len(res.strip) == row["stripLength"]
        for pt in row["strip"]:
            got = res.strip[pt["j"]]
            assert got.type == pt["type"]
            assert_close(got.K, pt["K"], label=f"K[{pt['j']}] {label}")
            assert_close(got.weight, pt["weight"], label=f"weight[{pt['j']}] {label}")
            assert_close(
                got.option_price, pt["optionPrice"], atol=1e-13 * c["S"], label=f"px {label}"
            )
            assert_close(got.contribution, pt["contribution"], atol=1e-13, label=f"contrib {label}")


# --- autocallable ----------------------------------------------------------------------


def _autocall(d: dict[str, Any]) -> AutocallInputs:
    return AutocallInputs(
        S=d["S"], S0=d["S0"], sigma=d["sigma"], r=d["r"], q=d["q"],
        maturity=d["maturity"], n_obs=d["nObs"], coupon_rate=d["couponRate"],
        autocall_barrier=d["autocallBarrier"], coupon_barrier=d["couponBarrier"],
        protection_barrier=d["protectionBarrier"], memory=d["memory"],
        notional=d["notional"],
    )  # fmt: skip


def _assert_autocall(got: AutocallResult, want: dict[str, Any], label: str) -> None:
    # Same draws ⇒ same paths: the counts are EXACT (they are multiples of 1/paths).
    assert got.prob_autocall == want["probAutocall"], label
    assert got.prob_capital_loss == want["probCapitalLoss"], label
    assert_close(got.price, want["price"], label=f"price {label}")
    assert_close(got.expected_life, want["expectedLife"], label=f"life {label}")
    # stderr = √(E[pv²] − E[pv]²)/√n: the subtraction cancels a few digits.
    assert_close(got.stderr, want["stderr"], rtol=1e-8, label=f"stderr {label}")


def _call_args(row: dict[str, Any]) -> dict[str, int]:
    """paths/seed as keyword arguments (``null`` in the golden = library default)."""
    return {k: row[k] for k in ("paths", "seed") if row[k] is not None}


def test_autocall_prices_vectorised() -> None:
    for row in GOLDEN["autocall"]["prices"]:
        i = _autocall(row["inputs"])
        got = price_autocall(i, **_call_args(row))
        _assert_autocall(got, row["result"], f"{row['name']} seed={row['seed']}")


def test_autocall_prices_reference_loop() -> None:
    """The literal loop port reproduces the TypeScript too (small-path rows only)."""
    for row in GOLDEN["autocall"]["prices"]:
        if row["paths"] is None:
            continue
        i = _autocall(row["inputs"])
        got = price_autocall_loop(i, **_call_args(row))
        _assert_autocall(got, row["result"], f"loop {row['name']} seed={row['seed']}")


def test_autocall_greeks() -> None:
    for row in GOLDEN["autocall"]["greeks"]:
        i = _autocall(row["inputs"])
        got = autocall_greeks(i, **_call_args(row))
        # Price noise: summation order (numpy pairwise vs JS sequential) over the paths.
        _assert_greeks(
            got, row["greeks"], eps=1e-12 * i.notional, S=i.S, T=i.maturity, label=row["name"]
        )


# --- GBM observation paths & the numeric-greeks stencil -------------------------------


@pytest.mark.parametrize("vectorised", [False, True])
def test_simulate_obs_paths(vectorised: bool) -> None:
    for c in GOLDEN["mc"]:
        args = (c["S0"], c["r"], c["q"], c["sigma"], c["dt"], c["nSteps"])
        want = np.array(c["paths"], dtype=np.float64)
        if vectorised:
            got = simulate_obs_paths(*args, c["nPaths"], c["seed"])
        else:
            normal = make_normal(mulberry32(c["seed"]))
            got = np.array([simulate_obs_path(*args, normal) for _ in range(c["nPaths"])])
        np.testing.assert_allclose(got, want, rtol=1e-12, atol=0)


def _vanilla_px(K: float, q: float, option_type: OptionType) -> PriceFn:
    def px(S: float, sigma: float, T: float, r: float) -> float:
        return vanilla_price(BsmInputs(S=S, K=K, T=T, r=r, q=q, sigma=sigma), option_type)

    return px


def test_numeric_greeks_of_a_vanilla() -> None:
    for row in GOLDEN["numericGreeks"]:
        px = _vanilla_px(row["K"], row["q"], row["type"])
        got = numeric_greeks(px, row["S"], row["sigma"], row["T"], row["r"])
        _assert_greeks(
            got, row["greeks"], eps=1e-13 * row["S"], S=row["S"], T=row["T"], label=str(row)
        )


# --- inputs Python rejects -------------------------------------------------------------
#
# The TypeScript validates none of these; the golden records what it does instead, as
# {"value": ...} or {"throws": "..."}. Python raises ValueError on all of them (a deliberate
# divergence). Beyond checking that, these tests pin the account of the TS behaviour given
# in each pricer's ``Raises`` notes, so the docstrings cannot drift from the truth.

TINY = 1e-300
"""A level just above 0: where Python's pricers reach the limit the TS returns AT 0."""


def _ts_value(outcome: dict[str, Any]) -> Any:
    """The recorded TS value (asserting the TS did not throw)."""
    assert "value" in outcome, outcome
    return outcome["value"]


def test_invalid_digital_levels() -> None:
    """Zero S or K: TS returns the correct limit (not garbage); NaN only if both are 0 or
    one is negative. Python rejects them, and just above 0 reproduces the TS limit."""
    for row in GOLDEN["invalidInputs"]["digital"]:
        i = _digital(row["inputs"])
        for pricer in (cash_or_nothing_price, asset_or_nothing_price):
            with pytest.raises(ValueError, match="digital"):
                pricer(i)
        ts_cash, ts_asset = _f(_ts_value(row["cash"])), _f(_ts_value(row["asset"]))
        if (i.S == 0) != (i.K == 0) and i.S >= 0 and i.K >= 0:
            near = replace(i, S=i.S or TINY, K=i.K or TINY)
            assert_close(cash_or_nothing_price(near), ts_cash, label=f"cash {i}")
            assert_close(asset_or_nothing_price(near), ts_asset, label=f"asset {i}")
        else:
            assert math.isnan(ts_cash), i
            assert math.isnan(ts_asset), i


def test_invalid_barrier_levels() -> None:
    """K = 0: the finite limit. S = 0: down = breached (out 0, in throws from the vanilla),
    up = NaN except a call with K > H (0). Negatives: NaN, 0, a throw or a finite number."""
    negatives: set[str] = set()
    for row in GOLDEN["invalidInputs"]["barrier"]:
        i = _barrier(row["inputs"])
        with pytest.raises(ValueError, match="barrier"):
            barrier_price(i)
        ts = row["price"]
        is_down = i.kind.startswith("down")
        is_out = i.kind.endswith("out")
        label = str(i)
        if i.S > 0 and i.K == 0:
            want = _f(_ts_value(ts))
            assert_close(barrier_price(replace(i, K=TINY)), want, atol=1e-13 * i.S, label=label)
        elif i.S == 0 and i.K > 0 and is_down:
            if is_out:
                assert _f(_ts_value(ts)) == 0.0, label
            else:
                assert "BSM: spot S must be > 0" in ts["throws"], label
        elif i.S == 0 and i.K > 0:
            got = _f(_ts_value(ts))
            if i.type == "call" and i.K > i.H:
                assert got == 0.0, label
            else:
                assert math.isnan(got), label
        elif i.S < 0 or i.K < 0:
            if "throws" in ts:
                negatives.add("throws")
            else:
                v = _f(ts["value"])
                negatives.add("nan" if math.isnan(v) else "zero" if v == 0 else "finite")
    assert negatives == {"nan", "zero", "throws", "finite"}


def test_invalid_varswap_inputs() -> None:
    """TS: T = 0 → NaN; T < 0 or n_strikes = 1 → the vanilla pricer throws; n_strikes ≤ 0
    → a silent fair variance of 0 with an empty strip."""
    for row in GOLDEN["invalidInputs"]["varswap"]:
        c = row["inputs"]
        n = c.get("nStrikes", 400)
        with pytest.raises(ValueError, match="varswap"):
            price_variance_swap(
                VarSwapInputs(
                    S=c["S"], T=c["T"], r=c["r"], q=c["q"], vol_for=lambda _K: 0.2,
                    n_strikes=n,
                )
            )  # fmt: skip
        ts = row["result"]
        if c["T"] == 0:
            assert math.isnan(_f(_ts_value(ts)["fairVariance"]))
        elif c["T"] < 0 or n == 1:
            assert ts["throws"].startswith("RangeError: BSM:"), c
        else:
            assert n <= 0
            assert _ts_value(ts) == {"fairVariance": 0, "stripLength": 0}


def test_invalid_autocall_inputs() -> None:
    """TS: 0 paths → NaN; n_obs = 0 → price 0; n_obs < 0 → throws; maturity = 0 →
    deterministic (stderr 0); maturity < 0 → NaN; S0 ≤ 0 → every path called on the first
    date (at maturity if n_obs = 1)."""
    for row in GOLDEN["invalidInputs"]["autocall"]:
        i = _autocall(row["inputs"])
        for pricer in (price_autocall, price_autocall_loop):
            with pytest.raises(ValueError, match="autocall"):
                pricer(i, row["paths"])
        label = f"{row['inputs']} paths={row['paths']}"
        if i.n_obs < 0:
            assert row["result"]["throws"] == "RangeError: Invalid array length", label
            continue
        ts = {k: _f(v) for k, v in _ts_value(row["result"]).items()}
        if row["paths"] == 0 or i.maturity < 0:
            assert math.isnan(ts["price"]), label
        elif i.n_obs == 0:
            assert ts["price"] == 0.0, label
        elif i.maturity == 0:
            assert math.isfinite(ts["price"]), label
            assert ts["stderr"] == 0.0, label
        else:
            assert i.S0 <= 0, label
            called = i.n_obs > 1
            assert ts["probAutocall"] == (1.0 if called else 0.0), label
            assert ts["expectedLife"] == (i.maturity / i.n_obs if called else i.maturity), label
