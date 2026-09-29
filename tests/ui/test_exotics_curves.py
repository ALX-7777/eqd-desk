"""The exotics page's pure numbers (:mod:`eqd_desk.app.ui.exotics_curves`): seeds and
slider bounds equal the React views', every chart sweep equals direct engine calls at the
React sweep points, and the default readouts print exactly what the React app prints."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from eqd_desk.app.ui import exotics_curves as ec
from eqd_desk.app.ui.bounds import Bounds, listed_strike_step
from eqd_desk.app.ui.charts import sweep_x
from eqd_desk.app.ui.format import fmt_money, fmt_num, fmt_pct, fmt_signed_pct
from eqd_desk.content import EXOTIC_METRICS, ExoticKind, ExoticMetric
from eqd_desk.data import MarketSnapshot, load_snapshot
from eqd_desk.engine import BsmInputs, OptionType, analyze_option
from eqd_desk.engine.exotics import (
    BARRIER_KINDS,
    AutocallInputs,
    BarrierInputs,
    BarrierKind,
    DigitalInputs,
    VarSwapInputs,
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
    price_variance_swap,
)
from eqd_desk.engine.presets import round_to


@pytest.fixture(scope="module")
def snap() -> MarketSnapshot:
    return load_snapshot()


@pytest.fixture(scope="module")
def barrier(snap: MarketSnapshot) -> BarrierInputs:
    return ec.barrier_seed(snap)


@pytest.fixture(scope="module")
def digital(snap: MarketSnapshot) -> DigitalInputs:
    return ec.digital_seed(snap)


@pytest.fixture(scope="module")
def note(snap: MarketSnapshot) -> AutocallInputs:
    return ec.autocall_seed(snap)


# ------------------------------------------------------------------ grid & seeds


def test_strike_grid_follows_react_rounding() -> None:
    # the seeds use the shared listed grid and the engine's JS-exact rounding
    assert listed_strike_step(6312.45) == 25.0
    assert listed_strike_step(500.0) == 5.0
    assert round_to(6312.45, 25) == 6300.0
    assert round_to(5681.205, 25) == 5675.0
    assert round_to(12.5, 25) == 25.0  # Math.round ties toward +inf
    assert round_to(-12.5, 25) == 0.0


def test_seeds_are_the_react_defaults(snap: MarketSnapshot) -> None:
    b = ec.barrier_seed(snap)
    assert (b.S, b.K, b.H, b.T, b.type, b.kind) == (snap.spot, 6300, 5675, 0.5, "call", "down-out")
    assert (b.r, b.q, b.sigma) == (snap.r, snap.q, snap.atm_vol_30d)
    d = ec.digital_seed(snap)
    assert (d.S, d.K, d.T, d.type, d.cash) == (snap.spot, 6300, 0.25, "call", 100)
    assert ec.digital_width_seed(snap.spot) == 125
    a = ec.autocall_seed(snap)
    assert (a.S, a.S0, a.maturity, a.n_obs, a.coupon_rate) == (snap.spot, snap.spot, 3, 6, 0.04)
    assert (a.autocall_barrier, a.coupon_barrier, a.protection_barrier) == (1.0, 0.7, 0.65)
    assert (a.memory, a.notional, a.sigma) == (True, 100, snap.atm_vol_30d)
    v = ec.varswap_seed(snap)
    assert (v.T, v.atm_vol, v.slope, v.curv) == (30 / 365, 0.146, -0.48, 0.62)
    assert (v.lo_mult, v.hi_mult, v.n_strikes) == (0.3, 3.0, 400)  # the engine's defaults
    assert ec.DEFAULT_METRIC["barrier"] == "gamma"
    assert ec.DEFAULT_METRIC["digital"] == "price"
    assert ec.DEFAULT_METRIC["autocall"] == "delta"


def test_slider_bounds_are_the_react_bounds(snap: MarketSnapshot) -> None:
    b = ec.barrier_bounds(snap.spot)
    assert b["S"] == b["K"] == Bounds(3775, 8825, 5)
    assert b["H"] == Bounds(3150, 9475, 5)
    assert b["T"] == Bounds(0.02, 2, 0.01)
    assert b["sigma"] == Bounds(0.05, 0.8, 0.0025)
    d = ec.digital_bounds(snap.spot)
    assert d["T"] == Bounds(0.005, 1.5, 0.005)
    assert d["cash"] == Bounds(10, 500, 10)
    assert d["width"] == Bounds(5, 625, 5)
    a = ec.autocall_bounds(snap.spot)
    assert a["S"] == Bounds(2525, 9469, snap.spot / 200)
    assert a["n_obs"] == Bounds(1, 24, 1)
    assert a["protection_barrier"] == Bounds(0.3, 1, 0.01)
    v = ec.varswap_bounds()
    assert v["T"] == Bounds(7 / 365, 1, 1 / 365)
    assert v["slope"] == Bounds(-1.2, 0.2, 0.01)
    for bounds in (*b.values(), *d.values(), *a.values(), *v.values()):
        assert bounds.lo < bounds.hi
        assert bounds.step > 0


def test_every_seed_lies_inside_its_slider(snap: MarketSnapshot) -> None:
    b, bb = ec.barrier_seed(snap), ec.barrier_bounds(snap.spot)
    d, db = ec.digital_seed(snap), ec.digital_bounds(snap.spot)
    a, ab = ec.autocall_seed(snap), ec.autocall_bounds(snap.spot)
    v, vb = ec.varswap_seed(snap), ec.varswap_bounds()
    pairs = [
        *((getattr(b, k), bb[k]) for k in ("S", "K", "H", "T", "sigma", "r", "q")),
        *((getattr(d, k), db[k]) for k in ("S", "K", "T", "sigma", "r", "q", "cash")),
        (ec.digital_width_seed(snap.spot), db["width"]),
        *((getattr(a, k), ab[k]) for k in ab),
        (v.T, vb["T"]),
        (v.atm_vol, vb["atm_vol"]),
        (v.slope, vb["slope"]),
        (v.curv, vb["curv"]),
        (v.lo_mult, vb["lo_mult"]),
        (v.hi_mult, vb["hi_mult"]),
        (v.n_strikes, vb["n_strikes"]),
    ]
    for value, bounds in pairs:
        assert bounds.lo <= value <= bounds.hi


# ------------------------------------------------------------------ default readouts = React


def test_barrier_default_readout_is_the_react_one(barrier: BarrierInputs) -> None:
    data = ec.barrier_data(barrier, "gamma", barrier.S)
    g, p = data.greeks, data.parity
    assert fmt_money(g.price) == "306.96"
    assert fmt_money(p.vanilla) == "312.24"
    assert ec.pct_of_vanilla(g.price, p.vanilla) == 98
    shown = [fmt_num(getattr(g, k)) for k in ec.PRICED_READOUT_KEYS]
    assert shown == ["0.60471", "0.00050065", "14.923", "-0.86011", "16.676"]


def test_digital_default_readout_is_the_react_one(
    snap: MarketSnapshot, digital: DigitalInputs
) -> None:
    width = ec.digital_width_seed(snap.spot)
    data = ec.digital_data(digital, width, "price", snap.spot)
    assert fmt_money(data.greeks.price) == "53.14"
    assert ec.digital_detail(data.spread, digital.cash, width) == "spread 53.14 · size 0.800×"
    shown = [fmt_num(getattr(data.greeks, k)) for k in ec.PRICED_READOUT_KEYS]
    assert shown == ["0.085277", "-3.08e-5", "-0.44756", "-0.0021791", "1.2129"]


def test_autocall_default_readout_is_the_react_one(note: AutocallInputs) -> None:
    data = ec.autocall_data(note)
    res, g = data.result, data.greeks
    assert fmt_money(res.price) == "103.20"
    assert ec.mc_badge(res.stderr) == "MC ±0.060"
    assert ec.autocall_detail(res.price, note.notional) == "103.2% of par"
    assert ec.autocall_value_label(note.notional) == "Note value (par 100)"
    assert fmt_pct(res.prob_autocall, 1) == "80.8%"
    assert fmt_pct(res.prob_capital_loss, 1) == "2.1%"
    assert fmt_num(res.expected_life, 3) == "1.24"
    shown = [fmt_num(getattr(g, k)) for k in ec.AUTOCALL_READOUT_KEYS]
    assert shown == ["-0.0010395", "-0.18708", "0.0050268", "-1.2357"]


def test_varswap_default_readout_is_the_react_one(snap: MarketSnapshot) -> None:
    data = ec.varswap_data(ec.varswap_seed(snap), S=snap.spot, r=snap.r, q=snap.q)
    assert fmt_pct(data.fair_vol) == "17.16%"
    assert fmt_num(data.fair_variance, 5) == "0.029432"
    assert fmt_pct(data.atm_vol) == "14.60%"
    assert fmt_signed_pct(data.convexity_premium) == "+2.56%"
    assert fmt_money(data.forward) == "6,328.03"


# ------------------------------------------------------------------ barrier


@pytest.mark.parametrize("metric", ["price", "delta", "gamma", "vega", "theta", "rho"])
def test_barrier_curve_is_the_engine_at_the_react_sweep(
    snap: MarketSnapshot, barrier: BarrierInputs, metric: ExoticMetric
) -> None:
    curve = ec.barrier_curve(barrier, metric, snap.spot)
    xs = sweep_x(snap.spot * 0.55, snap.spot * 1.45, 120)
    assert list(curve["S"]) == xs
    for n in (0, 37, 60, 97, 120):
        x = xs[n]
        assert curve["barrier"][n] == getattr(barrier_greeks(replace(barrier, S=x)), metric)
        vanilla = analyze_option(
            BsmInputs(S=x, K=barrier.K, T=barrier.T, r=barrier.r, q=barrier.q, sigma=barrier.sigma),
            "call",
        ).reported
        assert curve["vanilla"][n] == getattr(vanilla, metric)


def test_barrier_gamma_blows_up_next_to_the_barrier(
    snap: MarketSnapshot, barrier: BarrierInputs
) -> None:
    """The chart's lesson: a knock-out's gamma swings far beyond the vanilla's near H."""
    curve = ec.barrier_curve(barrier, "gamma", snap.spot)
    near = curve[(curve["S"] > barrier.H) & (curve["S"] < barrier.H * 1.02)]
    assert near["barrier"].abs().max() > 0.1 * curve["vanilla"].abs().max()
    assert near["barrier"].min() < 0 < curve["vanilla"].min() + 1e-12


@pytest.mark.parametrize("kind", BARRIER_KINDS)
@pytest.mark.parametrize("option", ["call", "put"])
def test_knock_in_plus_knock_out_is_the_vanilla(
    barrier: BarrierInputs, kind: BarrierKind, option: OptionType
) -> None:
    i = replace(barrier, kind=kind, type=option, H=5675 if kind.startswith("down") else 7000)
    p = ec.barrier_parity(i)
    assert p.out_kind.endswith("out")
    assert p.in_kind.endswith("in")
    assert p.out_kind.split("-")[0] == p.in_kind.split("-")[0] == kind.split("-")[0]
    assert p.knock_out == barrier_price(replace(i, kind=p.out_kind))
    assert p.knock_in == barrier_price(replace(i, kind=p.in_kind))
    assert p.vanilla == analyze_option(ec.vanilla_inputs(i), option).reported.price
    assert p.total == pytest.approx(p.vanilla, rel=1e-9, abs=1e-9)


def test_barrier_complement_is_an_involution() -> None:
    for kind in BARRIER_KINDS:
        other = ec.BARRIER_COMPLEMENT[kind]
        assert other != kind
        assert ec.BARRIER_COMPLEMENT[other] == kind
    assert list(ec.BARRIER_KIND_LABELS) == ["down-out", "down-in", "up-out", "up-in"]


def test_direction_and_knock_compose_every_barrier_kind() -> None:
    """The kind is picked as a direction and a knock: the two segment pairs reach every
    engine kind, and back."""
    assert list(ec.BARRIER_DIRECTION_LABELS.values()) == ["Down", "Up"]
    assert list(ec.BARRIER_KNOCK_LABELS.values()) == ["Out", "In"]
    composed = {
        ec.barrier_kind(d, k) for d in ec.BARRIER_DIRECTION_LABELS for k in ec.BARRIER_KNOCK_LABELS
    }
    assert composed == set(BARRIER_KINDS) == set(ec.BARRIER_KIND_LABELS)
    for kind in BARRIER_KINDS:
        direction, knock = ec.barrier_sides(kind)
        assert ec.barrier_kind(direction, knock) == kind
        assert ec.BARRIER_KIND_LABELS[kind] == f"{ec.BARRIER_DIRECTION_LABELS[direction]}-{knock}"
    assert ec.barrier_sides("down-out") == ("down", "out")
    assert ec.barrier_sides("up-in") == ("up", "in")


@pytest.mark.parametrize("kind", BARRIER_KINDS)
@pytest.mark.parametrize("option", ["call", "put"])
def test_barrier_status_matches_the_engine(
    barrier: BarrierInputs, kind: BarrierKind, option: OptionType
) -> None:
    """Breached / struck beyond ⇔ the engine prices the knock-out at exactly 0 and the
    knock-in at the vanilla."""
    direction, knock = ec.barrier_sides(kind)
    out_kind = kind if knock == "out" else ec.BARRIER_COMPLEMENT[kind]
    in_kind = ec.BARRIER_COMPLEMENT[out_kind]
    grid = [4500.0, 5675.0, 6000.0, 6312.45, 6600.0, 7025.0, 8000.0]
    for H in grid:
        for K in (5500.0, 6300.0, 7200.0):
            i = replace(barrier, type=option, kind=kind, H=H, K=K)
            status = ec.barrier_status(i)
            breached = ec.barrier_breached(i.S, H, direction)
            assert (status == "breached") == breached
            knock_out = barrier_price(replace(i, kind=out_kind))
            knock_in = barrier_price(replace(i, kind=in_kind))
            vanilla = analyze_option(ec.vanilla_inputs(i), option).reported.price
            dead = status != "live"
            assert (knock_out == 0.0) == dead, (H, K, status, knock_out)
            if dead:
                assert knock_in == pytest.approx(vanilla, rel=1e-9)


def test_barrier_breached_is_the_engine_test() -> None:
    assert ec.barrier_breached(6312.45, 6312.45, "down")  # touching counts
    assert ec.barrier_breached(6312.45, 6312.45, "up")
    assert ec.barrier_breached(6312.45, 7025.0, "down")
    assert not ec.barrier_breached(6312.45, 5675.0, "down")
    assert ec.barrier_breached(6312.45, 5675.0, "up")
    assert not ec.barrier_breached(6312.45, 7025.0, "up")


def test_switching_side_mirrors_the_barrier_through_spot(snap: MarketSnapshot) -> None:
    b = ec.barrier_bounds(snap.spot)["H"]
    step = listed_strike_step(snap.spot)
    S = snap.spot
    # the seed's down barrier, 10% below, flips to ~the same log-distance above, and back
    up = ec.reflected_barrier(S, 5675.0, "up", b, step)
    assert up == 7025.0
    assert up == round_to(S * S / 5675.0, step)
    assert ec.reflected_barrier(S, up, "down", b, step) == 5675.0
    # already on the right side: untouched (a breached down barrier switched to up is valid)
    assert ec.reflected_barrier(S, 7025.0, "up", b, step) == 7025.0
    assert ec.reflected_barrier(S, 5675.0, "down", b, step) == 5675.0
    assert ec.reflected_barrier(S, 6600.0, "up", b, step) == 6600.0
    # a barrier AT spot moves to the next grid level beyond it
    assert ec.reflected_barrier(6300.0, 6300.0, "up", b, step) == 6325.0
    assert ec.reflected_barrier(6300.0, 6300.0, "down", b, step) == 6275.0
    # far away: clamped to the slider, still beyond spot
    lo_spot = ec.barrier_bounds(snap.spot)["S"].lo
    far = ec.reflected_barrier(lo_spot, b.hi, "down", b, step)
    assert far == b.lo < lo_spot
    directions: tuple[ec.BarrierDirection, ...] = ("down", "up")
    for S_ in sweep_x(lo_spot, ec.barrier_bounds(snap.spot)["S"].hi, 40):
        for H in sweep_x(b.lo, b.hi, 40):
            for direction in directions:
                h = ec.reflected_barrier(S_, H, direction, b, step)
                assert b.lo <= h <= b.hi
                assert not ec.barrier_breached(S_, h, direction)


def test_metric_chips_offer_only_what_each_view_reports() -> None:
    assert ec.METRIC_CHIPS["barrier"] == ec.METRIC_CHIPS["digital"] == EXOTIC_METRICS
    assert ec.METRIC_CHIPS["autocall"] == ("price", "delta", "vega", "theta", "rho")
    assert "gamma" not in ec.METRIC_CHIPS["autocall"]  # MC gamma is not reported
    assert set(ec.METRIC_CHIPS["autocall"]) == {"price", *ec.AUTOCALL_READOUT_KEYS}
    assert ec.METRIC_CHIPS["varswap"] == ()
    priced: tuple[ExoticKind, ...] = ("barrier", "digital", "autocall")
    for kind in priced:
        assert ec.DEFAULT_METRIC[kind] in ec.METRIC_CHIPS[kind]


def test_pct_of_vanilla_rounds_like_react() -> None:
    assert ec.pct_of_vanilla(306.96, 312.24) == 98
    assert ec.pct_of_vanilla(1.0, 0.0) == 0
    assert ec.pct_of_vanilla(0.125, 1.0) == 13  # 12.5 → 13 (ties up)


# ------------------------------------------------------------------ digital


@pytest.mark.parametrize("metric", ["price", "delta", "gamma"])
def test_digital_curve_is_the_engine_at_the_react_sweep(
    snap: MarketSnapshot, digital: DigitalInputs, metric: ExoticMetric
) -> None:
    curve = ec.digital_curve(digital, 125.0, metric, snap.spot)
    xs = sweep_x(snap.spot * 0.7, snap.spot * 1.3, 140)
    assert list(curve["S"]) == xs
    for n in (0, 55, 70, 88, 140):
        d = replace(digital, S=xs[n])
        assert curve["digital"][n] == cash_or_nothing_price(d)
        assert curve["spread"][n] == call_spread_replication(d, 125.0)
        assert curve["greek"][n] == getattr(digital_greeks(d), metric)


def test_the_call_spread_converges_to_the_digital(snap: MarketSnapshot) -> None:
    near_expiry = replace(ec.digital_seed(snap), T=0.02)
    widths = ec.width_grid(ec.digital_bounds(snap.spot)["width"])
    assert widths[0] == 5
    assert widths[-1] == 625
    assert len(widths) == 125  # every slider position
    conv = ec.spread_convergence(near_expiry, widths)
    assert list(conv["width"]) == widths
    assert list(conv["size"]) == [near_expiry.cash / w for w in widths]
    assert set(conv["digital"]) == {cash_or_nothing_price(near_expiry)}
    errors = (conv["spread"] - conv["digital"]).abs()
    assert errors.iloc[0] < 0.01 < errors.iloc[-1]
    assert errors.is_monotonic_increasing  # the tighter the spread, the closer
    for n in (0, 60, 124):
        assert conv["spread"][n] == call_spread_replication(near_expiry, widths[n])


def test_cash_payout_is_the_react_digital(snap: MarketSnapshot, digital: DigitalInputs) -> None:
    """The payout defaults to cash, and cash is exactly the React (engine) digital."""
    assert list(ec.DIGITAL_PAYOUT_LABELS) == list(ec.DIGITAL_PAYOUT_NAMES) == ["cash", "asset"]
    # short segments (they sit side by side in the narrow controls column), full names in
    # the legend and the tooltip
    assert list(ec.DIGITAL_PAYOUT_LABELS.values()) == ["Cash", "Asset"]
    assert list(ec.DIGITAL_PAYOUT_NAMES.values()) == ["Cash-or-nothing", "Asset-or-nothing"]
    assert ec.digital_price(digital) == cash_or_nothing_price(digital)
    assert ec.payout_greeks(digital) == digital_greeks(digital)
    assert ec.replication_price(digital, 125.0) == call_spread_replication(digital, 125.0)
    assert ec.payout_amount(digital, "cash") == digital.cash
    data = ec.digital_data(digital, 125.0, "gamma", snap.spot, "cash")
    assert data.decomposition is None
    assert data.greeks == digital_greeks(digital)


@pytest.mark.parametrize("option", ["call", "put"])
def test_asset_or_nothing_is_the_engine(
    snap: MarketSnapshot, digital: DigitalInputs, option: OptionType
) -> None:
    i = replace(digital, type=option, cash=250.0)  # Q plays no part in the asset payout
    assert ec.digital_price(i, "asset") == asset_or_nothing_price(i)

    def px(S: float, sigma: float, T: float, r: float) -> float:
        return asset_or_nothing_price(replace(i, S=S, sigma=sigma, T=T, r=r))

    assert ec.payout_greeks(i, "asset") == numeric_greeks(px, i.S, i.sigma, i.T, i.r)
    assert ec.payout_amount(i, "asset") == i.K
    curve = ec.digital_curve(i, 125.0, "delta", snap.spot, "asset")
    xs = sweep_x(snap.spot * 0.7, snap.spot * 1.3, 140)
    for n in (0, 70, 140):
        p = replace(i, S=xs[n])
        assert curve["digital"][n] == asset_or_nothing_price(p)
        assert curve["spread"][n] == ec.replication_price(p, 125.0, "asset")
        assert curve["greek"][n] == ec.payout_greeks(p, "asset").delta


@pytest.mark.parametrize("option", ["call", "put"])
def test_asset_or_nothing_is_a_vanilla_plus_k_cash_digitals(
    digital: DigitalInputs, option: OptionType
) -> None:
    """AoN call = vanilla call + K·digital; AoN put = K·digital − vanilla put (exact)."""
    i = replace(digital, type=option)
    d = ec.asset_decomposition(i)
    vanilla = analyze_option(ec.vanilla_inputs(i), option).reported.price
    assert d.vanilla == pytest.approx(vanilla, rel=1e-12)
    assert d.k_digitals == cash_or_nothing_price(replace(i, cash=i.K))
    assert d.sign == (1 if option == "call" else -1)
    assert d.total == pytest.approx(asset_or_nothing_price(i), rel=1e-12)


@pytest.mark.parametrize("option", ["call", "put"])
def test_the_asset_replication_converges_to_the_asset_digital(
    snap: MarketSnapshot, option: OptionType
) -> None:
    near_expiry = replace(ec.digital_seed(snap), type=option, T=0.02)
    widths = ec.width_grid(ec.digital_bounds(snap.spot)["width"])
    conv = ec.spread_convergence(near_expiry, widths, "asset")
    assert set(conv["digital"]) == {asset_or_nothing_price(near_expiry)}
    assert list(conv["size"]) == [near_expiry.K / w for w in widths]  # K/Δ spreads
    errors = (conv["spread"] - conv["digital"]).abs()
    assert errors.iloc[0] < 0.5 < errors.iloc[-1]
    assert errors.is_monotonic_increasing
    spreads = call_spread_replication(replace(near_expiry, cash=near_expiry.K), 125.0)
    vanilla = analyze_option(ec.vanilla_inputs(near_expiry), option).reported.price
    expected = vanilla + spreads if option == "call" else spreads - vanilla
    assert ec.replication_price(near_expiry, 125.0, "asset") == pytest.approx(expected, 1e-12)


def test_digital_labels_and_recipes(digital: DigitalInputs) -> None:
    assert ec.digital_series_labels("call", "cash") == ("Call spread", "Digital")
    assert ec.digital_series_labels("put", "cash") == ("Put spread", "Digital")
    assert ec.digital_series_labels("call", "asset") == (
        "Vanilla + call spreads",
        "Asset-or-nothing",
    )
    assert ec.replication_recipe(digital, 125.0, "cash") == "0.800× call spreads"
    assert ec.replication_recipe(digital, 125.0, "asset") == "50.4× call spreads + 1 vanilla call"
    put = replace(digital, type="put")
    assert ec.replication_recipe(put, 125.0, "asset") == "50.4× put spreads − 1 vanilla put"
    assert ec.digital_detail(53.14, 6300.0, 125.0, label="replication") == (
        "replication 53.14 · size 50.4×"
    )


# ------------------------------------------------------------------ autocallable


def test_sample_paths_are_the_react_paths(note: AutocallInputs) -> None:
    """The React ``paths`` memo, draw for draw: one normal stream, path after path."""
    paths = ec.sample_paths(note)
    steps, n_paths = ec.SAMPLE_STEPS, ec.SAMPLE_PATHS
    normal = make_normal(mulberry32(0xC0FFEE))
    dt = note.maturity / steps
    drift = (note.r - note.q - 0.5 * note.sigma * note.sigma) * dt
    vol = note.sigma * math.sqrt(dt)
    assert list(paths.columns) == ["t", *(f"p{p}" for p in range(n_paths))]
    assert list(paths["t"]) == [(k / steps) * note.maturity for k in range(steps + 1)]
    for p in range(n_paths):
        s = [note.S]
        for k in range(1, steps + 1):
            s.append(s[k - 1] * math.exp(drift + vol * normal()))
        assert list(paths[f"p{p}"]) == pytest.approx(s, rel=1e-13)


def test_autocall_levels_and_dates(note: AutocallInputs) -> None:
    lv = ec.autocall_levels(note)
    assert (lv.autocall, lv.coupon, lv.protection) == (
        1.0 * note.S0,
        0.7 * note.S0,
        0.65 * note.S0,
    )
    assert ec.observation_times(note) == [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]


def test_autocall_data_is_the_engine_with_the_react_path_counts(note: AutocallInputs) -> None:
    i = replace(note, memory=False, n_obs=4, S=note.S * 0.9)
    data = ec.autocall_data(i)
    assert data.result == price_autocall(i, 12_000)
    assert data.greeks == autocall_greeks(i, 16_000)
    assert data.paths.equals(ec.sample_paths(i))


def test_autocall_displays() -> None:
    assert ec.autocall_spot_display(6312.45, 6312.45) == "6,312.45 · 100%"
    assert ec.autocall_spot_display(5050.0, 6312.45) == "5,050.00 · 80%"
    assert ec.maturity_display(3.0) == "3 y"
    assert ec.maturity_display(2.5) == "2.5 y"
    assert ec.autocall_value_label(250.0) == "Note value (par 250)"


# ------------------------------------------------------------------ variance swap


def test_smile_is_the_react_vol_function() -> None:
    f = 6328.0
    vol_for = ec.smile(0.146, -0.48, 0.62, f)
    assert vol_for(f) == 0.146
    k = math.log(5000 / f)
    assert vol_for(5000) == 0.146 - 0.48 * k + 0.62 * k**2
    assert ec.smile(0.05, 0.2, 0.0, f)(0.3 * f) == ec.VARSWAP_VOL_FLOOR


def test_varswap_data_is_the_engine(snap: MarketSnapshot) -> None:
    c = replace(ec.varswap_seed(snap), T=0.25, slope=-0.7, lo_mult=0.5, n_strikes=200)
    data = ec.varswap_data(c, S=snap.spot, r=snap.r, q=snap.q)
    F = snap.spot * math.exp((snap.r - snap.q) * c.T)

    def vol_for(K: float) -> float:
        return max(0.03, c.atm_vol + c.slope * math.log(K / F) + c.curv * math.log(K / F) ** 2)

    direct = price_variance_swap(
        VarSwapInputs(
            S=snap.spot, T=c.T, r=snap.r, q=snap.q, vol_for=vol_for, lo_mult=0.5, n_strikes=200
        )
    )
    assert data.fair_variance == direct.fair_variance
    assert data.fair_vol == direct.fair_vol
    assert data.atm_vol == direct.atm_vol == c.atm_vol
    assert data.forward == direct.forward
    assert data.convexity_premium == direct.fair_vol - direct.atm_vol
    # the plotted strip: every third strike, with the smile at that strike
    every_third = direct.strip[::3]
    assert list(data.strip["K"]) == [p.K for p in every_third]
    assert list(data.strip["contribution"]) == [p.contribution for p in every_third]
    assert list(data.strip["vol"]) == [vol_for(p.K) for p in every_third]


def test_skew_effect_sweeps_the_slope_slider(snap: MarketSnapshot) -> None:
    c = ec.varswap_seed(snap)
    data = ec.varswap_data(c, S=snap.spot, r=snap.r, q=snap.q)
    slopes = ec.skew_slopes()
    assert slopes == sweep_x(-1.2, 0.2, 14)
    assert list(data.skew["slope"]) == slopes
    for n in (0, 7, 14):
        at = ec.varswap_data(replace(c, slope=slopes[n]), S=snap.spot, r=snap.r, q=snap.q)
        assert data.skew["fair_vol"][n] == at.fair_vol
        assert data.skew["atm_vol"][n] == at.atm_vol
    # on the equity-skew side, steeper (more negative) skew → richer variance
    equity_skew = data.skew[data.skew["slope"] <= -0.2]
    assert equity_skew["fair_vol"].is_monotonic_decreasing
    assert (data.skew["fair_vol"] >= data.skew["atm_vol"]).all()


def test_a_flat_smile_prices_variance_at_the_atm_vol(snap: MarketSnapshot) -> None:
    flat = replace(ec.varswap_seed(snap), slope=0.0, curv=0.0)
    data = ec.varswap_data(flat, S=snap.spot, r=snap.r, q=snap.q)
    assert data.fair_vol == pytest.approx(flat.atm_vol, abs=2e-4)


def test_the_skew_switch_flattens_the_smile(snap: MarketSnapshot) -> None:
    """Skew off = slope and curvature ignored (kept, not reset): the fair vol falls back to
    ATM and the convexity premium to ~0; the skew sweep then runs without curvature."""
    seed = ec.varswap_seed(snap)
    assert seed.skew
    assert (seed.smile_slope, seed.smile_curv) == (seed.slope, seed.curv)
    off = replace(seed, skew=False)
    assert (off.slope, off.curv) == (seed.slope, seed.curv)
    assert (off.smile_slope, off.smile_curv) == (0.0, 0.0)
    data = ec.varswap_data(off, S=snap.spot, r=snap.r, q=snap.q)
    flat = ec.varswap_data(replace(seed, slope=0.0, curv=0.0), S=snap.spot, r=snap.r, q=snap.q)
    assert data.fair_variance == flat.fair_variance
    assert abs(data.convexity_premium) < 2e-4
    assert set(data.strip["vol"]) == {seed.atm_vol}
    no_curv = replace(seed, curv=0.0)
    for n in (0, 7, 14):
        at = ec.varswap_data(
            replace(no_curv, slope=ec.skew_slopes()[n]), S=snap.spot, r=snap.r, q=snap.q
        )
        assert data.skew["fair_vol"][n] == at.fair_vol


def test_vol_axis_domain_only_widens_a_flat_smile() -> None:
    assert ec.vol_axis_domain([0.10, 0.18, 0.146]) is None  # a real smile: automatic axis
    lo, hi = ec.vol_axis_domain([0.146, 0.146, 0.1458]) or (0.0, 0.0)
    assert hi - lo == pytest.approx(ec.SMILE_MIN_SPAN)
    assert lo < 0.1458 < 0.146 < hi
    assert ec.vol_axis_domain([0.005, 0.006]) == (0.0, ec.SMILE_MIN_SPAN)  # floored at 0


def test_truncating_the_strip_loses_variance(snap: MarketSnapshot) -> None:
    """Strike truncation (a content risk point): a narrower strip misses wing variance."""
    full = ec.varswap_seed(snap)
    narrow = replace(full, lo_mult=0.9, hi_mult=1.1)
    fv_full = ec.varswap_data(full, S=snap.spot, r=snap.r, q=snap.q).fair_vol
    fv_narrow = ec.varswap_data(narrow, S=snap.spot, r=snap.r, q=snap.q).fair_vol
    assert fv_narrow < fv_full


# ------------------------------------------------------------------ display helpers


def test_display_helpers() -> None:
    assert ec.maturity_display(3.0) == "3 y"
    assert ec.maturity_display(2.5) == "2.5 y"
    assert ec.years_display(0.5) == "0.50 y"
    assert ec.metric_axis_title("price", "USD") == "Value (USD)"
    assert ec.metric_axis_title("gamma", "USD") == "Gamma (Δdelta per $1 spot)"
    assert ec.metric_axis_title("delta", "EUR") == "Delta (per €1 spot)"
    assert ec.metric_value(barrier_greeks(ec.barrier_seed(load_snapshot())), "rho") > 0
