"""The Python trading simulator reproduces the TypeScript engine (golden values exported by
``web/scripts/golden/sim.golden.ts``).

Covered: the skew surface, single GBM + leverage steps with fixed normals, seeded
:class:`MarketSimulator` paths and realised vol, seeded RFQ streams and their net/gross
fair, the quote/fill grid, P&L attribution over hand-picked moves (gaps, an expiry
crossing, no move), historical-replay windows, the desk advisor on crafted books (every
branch, the full advice TEXT, hedge plans, the joint hedge and RFQ risk impact), and whole
SEEDED DESK SESSIONS: a scripted trader running the SimulatorView loop (market steps,
per-step P&L explain, RFQ arrival/expiry, quoting with a lean, fills, a hedging schedule
that uses every book operation and the advisor's plans). :func:`_run_session` is a line-by-
line mirror of ``runSession`` in the exporter and consumes every random stream in the same
order, so paths, RFQs, fills, book state, greeks and advice must all line up.

Tolerances: pure IEEE arithmetic (RFQ geometry, the quote grid, replay states, the
synthetic series) is compared EXACTLY. Anything through exp/log/sqrt uses
:func:`~tests.parity.golden_io.assert_close`, with the absolute floor scaled by the size of
the numbers that cancel (see :func:`_session_atol`). Advice text must match character for
character.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Sequence
from functools import cache
from typing import Any

import pytest

from eqd_desk.engine.presets import PresetParams, build_preset, round_to
from eqd_desk.engine.rng import Mulberry32, NormalSampler
from eqd_desk.engine.sim import (
    DEFAULT_SIM_PARAMS,
    RFQ,
    ZERO_COSTS,
    Advice,
    Book,
    BookTrade,
    CostModel,
    HistoryPoint,
    JointHedge,
    MarketSimulator,
    MarketState,
    OptionOrder,
    ReplayBase,
    RfqLeg,
    RiskImpact,
    SimParams,
    add_fill,
    advise_book,
    attribute,
    book_greeks,
    book_value,
    empty_book,
    evaluate_quote,
    flatten_gamma,
    flatten_vega,
    gbm_leverage_process,
    generate_rfq,
    hedge_to_flat,
    hedge_trade,
    joint_hedge,
    marked_legs,
    pick_window,
    realised_vol,
    replay_state,
    rfq_fair,
    rfq_risk_impact,
    single_option_rfq,
    trade_option,
    trade_structure,
    vol_for_strike,
    window_steps,
)
from eqd_desk.engine.strategy import LegSide
from tests.parity.golden_io import ATOL, RTOL, assert_close, load_golden

GOLDEN = load_golden("sim")

# ---------------------------------------------------------------------------- decoding


def _num(x: Any) -> float:
    """A golden number (non-finite values are exported as strings)."""
    return float(x)


def _market(d: dict[str, Any]) -> MarketState:
    """TS ``MarketState`` (optional skew fields may be absent) → :class:`MarketState`."""
    return MarketState(
        t=d["t"],
        spot=d["spot"],
        atm_vol=d["atmVol"],
        r=d["r"],
        q=d["q"],
        skew_slope=d.get("skewSlope"),
        skew_curv=d.get("skewCurv"),
    )


def _params(d: dict[str, float]) -> SimParams:
    return SimParams(
        drift=d["drift"],
        leverage=d["leverage"],
        vol_mean_rev=d["volMeanRev"],
        base_vol=d["baseVol"],
        vol_of_vol=d["volOfVol"],
        dt=d["dt"],
    )


def _costs(d: dict[str, float]) -> CostModel:
    return CostModel(
        underlying_half_spread=d["underlyingHalfSpread"],
        option_half_spread=d["optionHalfSpread"],
    )


def _replay_base(d: dict[str, float]) -> ReplayBase:
    return ReplayBase(
        r=d["r"], q=d["q"], skew_slope=d["skewSlope"], skew_curv=d["skewCurv"], dt=d["dt"]
    )


def _rfq(a: list[Any]) -> RFQ:
    """Compact RFQ ``[id, label, clientSide, size, bornDay, [[type, side, ratio, K, T]]]``."""
    rid, label, client_side, size, born_day, legs = a
    return RFQ(
        id=rid,
        label=label,
        legs=tuple(RfqLeg(type=t, side=s, ratio=ratio, K=K, T=T) for t, s, ratio, K, T in legs),
        size=size,
        client_side=client_side,
        born_day=born_day,
    )


def _book(d: dict[str, Any]) -> Book:
    trades = tuple(
        BookTrade(id=i, type=t, side=s, quantity=qty, K=K, expiry_time=exp, traded_price=px)
        for i, t, s, qty, K, exp, px in d["trades"]
    )
    return Book(
        trades=trades,
        underlying_qty=d["underlyingQty"],
        cash=d["cash"],
        realized_edge=d["realizedEdge"],
        total_costs=d["totalCosts"],
        next_id=d["nextId"],
    )


# ---------------------------------------------------------------------------- encoding
# Python objects → the same JSON-like shape the TS exporter wrote (camelCase keys; optional
# fields that TS leaves ``undefined`` are omitted), so one comparator checks everything.


def _rfq_out(r: RFQ) -> list[Any]:
    legs = [[leg.type, leg.side, leg.ratio, leg.K, leg.T] for leg in r.legs]
    return [r.id, r.label, r.client_side, r.size, r.born_day, legs]


def _trade_out(t: BookTrade) -> list[Any]:
    return [t.id, t.type, t.side, t.quantity, t.K, t.expiry_time, t.traded_price]


def _book_out(b: Book) -> dict[str, Any]:
    return {
        "trades": [_trade_out(t) for t in b.trades],
        "underlyingQty": b.underlying_qty,
        "cash": b.cash,
        "realizedEdge": b.realized_edge,
        "totalCosts": b.total_costs,
        "nextId": b.next_id,
    }


def _market_out(m: MarketState) -> dict[str, Any]:
    out: dict[str, Any] = {"t": m.t, "spot": m.spot, "atmVol": m.atm_vol, "r": m.r, "q": m.q}
    if m.skew_slope is not None:
        out["skewSlope"] = m.skew_slope
    if m.skew_curv is not None:
        out["skewCurv"] = m.skew_curv
    return out


def _optional(d: dict[str, Any], **fields: Any) -> dict[str, Any]:
    """Add the fields that are not ``None`` (TS omits ``undefined`` keys from JSON)."""
    d.update({k: v for k, v in fields.items() if v is not None})
    return d


def _advice_out(a: Advice) -> dict[str, Any]:
    out: dict[str, Any] = {
        "severity": a.severity,
        "title": a.title,
        "detail": a.detail,
        "action": a.action,
    }
    if a.plan is not None:
        p = a.plan
        plan = {
            "instrument": p.instrument,
            "side": p.side,
            "quantity": p.quantity,
            "rationale": p.rationale,
        }
        out["plan"] = _optional(plan, optionType=p.option_type, K=p.K, tenorDays=p.tenor_days)
    return out


def _joint_legs_out(j: JointHedge) -> list[dict[str, Any]]:
    return [
        _optional(
            {"instrument": leg.instrument, "side": leg.side, "quantity": leg.quantity},
            optionType=leg.option_type,
            K=leg.K,
            tenorDays=leg.tenor_days,
        )
        for leg in j.legs
    ]


def _joint_out(j: JointHedge) -> dict[str, Any]:
    return {"feasible": j.feasible, "legs": _joint_legs_out(j), "rationale": j.rationale}


def _impact_out(i: RiskImpact) -> dict[str, Any]:
    return {
        "dDelta": i.d_delta,
        "dVega": i.d_vega,
        "dGamma": i.d_gamma,
        "verdict": i.verdict,
        "note": i.note,
    }


# ---------------------------------------------------------------------------- comparator


def _assert_same(actual: Any, expected: Any, *, atol: float, label: str) -> None:
    """Recursive comparison of a Python-built tree with a golden tree: strings, booleans
    and ``None`` exactly; numbers with :func:`assert_close` (``RTOL`` and ``atol``)."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{label}: expected an object, got {actual!r}"
        assert set(actual) == set(expected), f"{label}: keys {set(actual)} != {set(expected)}"
        for k, v in expected.items():
            _assert_same(actual[k], v, atol=atol, label=f"{label}.{k}")
    elif isinstance(expected, list):
        assert isinstance(actual, list | tuple), f"{label}: expected a list, got {actual!r}"
        assert len(actual) == len(expected), f"{label}: length {len(actual)} != {len(expected)}"
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _assert_same(a, e, atol=atol, label=f"{label}[{i}]")
    elif isinstance(expected, bool) or expected is None:
        assert actual is expected, f"{label}: {actual!r} != {expected!r}"
    elif isinstance(expected, int | float):
        assert isinstance(actual, int | float), f"{label}: {actual!r} is not a number"
        assert not isinstance(actual, bool), f"{label}: {actual!r} is a bool"
        assert_close(actual, expected, atol=atol, label=label)
    elif isinstance(expected, str) and isinstance(actual, float):
        assert_close(actual, _num(expected), atol=atol, label=label)  # "NaN" / "Infinity"
    else:
        assert actual == expected, f"{label}: {actual!r} != {expected!r}"


NOTIONAL_ATOL = 1e-14
"""Absolute floor per unit of gross notional (see :func:`_book_atol`). Measured worst case
over the golden sessions: ~1.9e-10 needed on a ~6.6e7 notional (SPX), i.e. ~3e-18 per
unit, so this keeps ~800x (or more) headroom while staying within a few tens of ulp of the
notional (and far below a cent)."""


def _book_atol(book: Book, spot: float) -> float:
    """Absolute floor for book-level numbers. Book value, P&L terms and the residual are
    small differences of big numbers (cash, hedge notional, many option legs), so the last-
    ulp exp/log noise is absolute, of order ulp × the gross notional. Scale the floor by
    the gross notional (|cash| + |hedge|·S + Σ contracts·S). Values that do not cancel are
    held to ``RTOL`` anyway."""
    gross = abs(book.cash) + abs(book.underlying_qty) * spot
    gross += sum(t.quantity for t in book.trades) * spot
    return NOTIONAL_ATOL * max(1.0, gross)


# ---------------------------------------------------------------------------- building blocks


def test_constants() -> None:
    c = GOLDEN["constants"]
    assert _params(c["defaultSimParams"]) == DEFAULT_SIM_PARAMS
    assert _costs(c["zeroCosts"]) == ZERO_COSTS


VOL_GRID: list[dict[str, Any]] = GOLDEN["volGrid"]


@pytest.mark.parametrize("case", VOL_GRID, ids=[f"market{i}" for i in range(len(VOL_GRID))])
def test_vol_for_strike_grid(case: dict[str, Any]) -> None:
    m = _market(case["market"])
    for K, row in zip(case["Ks"], case["vols"], strict=True):
        for T, want in zip(case["Ts"], row, strict=True):
            assert_close(vol_for_strike(m, K, T), want, label=f"K={K} T={T}")


def test_gbm_leverage_step_cases() -> None:
    g = GOLDEN["stepCases"]
    states = [_market(s) for s in g["states"]]
    params = [_params(p) for p in g["params"]]
    for si, pi, zi, *want in g["results"]:
        z1, z2 = g["zs"][zi]
        draws: Iterator[float] = iter([z1, z2])  # the step consumes exactly two normals
        res = gbm_leverage_process.step(states[si], params[pi], draws.__next__)
        s = res.state
        got = [
            s.t,
            s.spot,
            s.atm_vol,
            s.r,
            s.q,
            s.skew_slope,
            s.skew_curv,
            res.dS,
            res.d_vol,
            res.spot_return,
        ]
        _assert_same(got, want, atol=ATOL, label=f"state{si} params{pi} z{zi}")


SIM_PATHS: list[dict[str, Any]] = GOLDEN["simPaths"]


@pytest.mark.parametrize("case", SIM_PATHS, ids=[c["label"] for c in SIM_PATHS])
def test_market_simulator_paths(case: dict[str, Any]) -> None:
    """Seeded paths (two normals per step from NormalSampler(Mulberry32(seed)))."""
    initial = _market(case["initial"])
    if case["params"] is None:
        sim = MarketSimulator(initial)  # the defaults: DEFAULT_SIM_PARAMS, seed 0x5EED
    else:
        sim = MarketSimulator(initial, _params(case["params"]), case["seed"])
    spots = [sim.state.spot]
    for k, want in enumerate(case["rows"]):
        res = sim.next()
        spots.append(res.state.spot)
        got = [res.state.t, res.state.spot, res.state.atm_vol, res.dS, res.d_vol, res.spot_return]
        _assert_same(got, want, atol=ATOL * initial.spot, label=f"step {k + 1}")
    _assert_same(_market_out(sim.state), case["finalState"], atol=ATOL, label="final")
    _assert_same(realised_vol(spots, 1 / 252), case["realisedVol"], atol=ATOL, label="rv")


def test_realised_vol_cases() -> None:
    for c in GOLDEN["realisedVol"]:
        _assert_same(realised_vol(c["spots"], c["dt"]), c["vol"], atol=ATOL, label=str(c))


RFQ_STREAMS: list[dict[str, Any]] = GOLDEN["rfqStreams"]


@pytest.mark.parametrize("case", RFQ_STREAMS, ids=[f"seed{c['seed']}" for c in RFQ_STREAMS])
def test_rfq_streams(case: dict[str, Any]) -> None:
    """Seeded RFQ streams: the geometry is pure arithmetic, so it must match EXACTLY."""
    rng = Mulberry32(case["seed"])
    rfqs = [
        generate_rfq(case["spot"], case["strikeStep"], rng, k + 1, case["day"])
        for k in range(case["n"])
    ]
    assert [_rfq_out(r) for r in rfqs] == case["rfqs"]
    if case["fair"] is not None:
        m = _market(case["market"])
        for r, (net, gross) in zip(rfqs, case["fair"], strict=True):
            f = rfq_fair(r, m)
            atol = ATOL * m.spot
            assert_close(f.net, net, atol=atol, label=f"rfq {r.id} net")
            assert_close(f.gross, gross, atol=atol, label=f"rfq {r.id} gross")


def test_quote_grid() -> None:
    """evaluate_quote is pure arithmetic: bit-identical to the TS engine."""
    g = GOLDEN["quoteGrid"]
    rfqs = {r.id: r for r in (_rfq(a) for a in g["rfqs"])}
    assert rfqs[1] == single_option_rfq("call", 100, 0.25, 10, "buy", 1)
    assert rfqs[2] == single_option_rfq("put", 95, 0.5, 25, "sell", 2, 4)
    for rid, net, gross, spread, z, lean, *want in g["cases"]:
        if lean is None:  # the default lean
            f = evaluate_quote(rfqs[rid], net, gross, spread, 0.1, z)
        else:
            f = evaluate_quote(rfqs[rid], net, gross, spread, 0.1, z, lean)
        got = [f.filled, f.you_side, f.price, f.edge, f.bid, f.ask, f.fair_value]
        assert got == want, (rid, net, gross, spread, z, lean)


ATTRIBUTION: list[dict[str, Any]] = GOLDEN["attribution"]


@pytest.mark.parametrize("case", ATTRIBUTION, ids=[f"move{i}" for i in range(len(ATTRIBUTION))])
def test_attribution_cases(case: dict[str, Any]) -> None:
    book = _book(case["book"])
    before, after = _market(case["before"]), _market(case["after"])
    a = attribute(book, before, after)
    got = {f: getattr(a, f) for f in case["att"]}
    atol = _book_atol(book, before.spot)
    _assert_same(got, case["att"], atol=atol, label="attribution")


# ---------------------------------------------------------------------------- replay


def synthetic_series(seed: int, n: int) -> list[HistoryPoint]:
    """Same generator (same operation order, pure IEEE arithmetic) as ``syntheticSeries``
    in the exporter: a multiplicative random walk for spot with a leverage-linked VIX."""
    u = Mulberry32(seed)
    spot = 4200.0
    vix = 17.0
    out: list[HistoryPoint] = []
    for k in range(n):
        out.append(HistoryPoint(date=f"d{k}", spot=spot, vix=vix))
        a = u()
        b = u()
        spot = spot * (1 + 0.03 * (a - 0.5))
        vix = min(80.0, max(9.0, vix + 4 * (b - 0.5) - 40 * 0.03 * (a - 0.5)))
    return out


def _point_out(p: HistoryPoint) -> dict[str, Any]:
    return {"date": p.date, "spot": p.spot, "vix": p.vix}


def test_replay_windows() -> None:
    """Window picking and replay states are pure arithmetic: exact."""
    g = GOLDEN["replay"]
    series = synthetic_series(g["seed"], g["n"])
    assert [_point_out(p) for p in series[:3]] == g["first"]
    assert _point_out(series[-1]) == g["last"]
    base = _replay_base(g["base"])
    for w in g["windows"]:
        win = pick_window(series, w["length"], w["u"])
        where = f"length={w['length']} u={w['u']}"
        assert (win.start_index, len(win.points), window_steps(win)) == (
            w["startIndex"],
            w["nPoints"],
            w["steps"],
        ), where
        for s in w["states"]:
            got = _market_out(replay_state(win, s["i"], base))
            assert got == s["state"], f"{where} i={s['i']}"


# ---------------------------------------------------------------------------- advisor

ADVISOR: list[dict[str, Any]] = GOLDEN["advisor"]


def _probe_rfqs(m: MarketState) -> list[RFQ]:
    """The exporter's probe RFQs, strikes scaled to the market (``K·spot/100``)."""
    straddle = (
        RfqLeg(type="call", side="long", ratio=1, K=100, T=0.5),
        RfqLeg(type="put", side="long", ratio=1, K=100, T=0.5),
    )
    rr = (
        RfqLeg(type="put", side="short", ratio=1, K=90, T=0.5),
        RfqLeg(type="call", side="long", ratio=2, K=110, T=0.5),
    )
    probes = [
        single_option_rfq("call", 100, 0.25, 20, "buy", 1),
        single_option_rfq("call", 100, 0.25, 20, "sell", 2),
        RFQ(id=3, label="Straddle", legs=straddle, size=50, client_side="sell", born_day=0),
        RFQ(id=4, label="Straddle", legs=straddle, size=50, client_side="buy", born_day=0),
        single_option_rfq("call", 100, 5 / 365, 2, "buy", 5),
        RFQ(id=6, label="Risk reversal", legs=rr, size=10, client_side="sell", born_day=1),
    ]
    return [
        RFQ(
            id=r.id,
            label=r.label,
            legs=tuple(
                RfqLeg(
                    type=leg.type, side=leg.side, ratio=leg.ratio, K=(leg.K * m.spot) / 100, T=leg.T
                )
                for leg in r.legs
            ),
            size=r.size,
            client_side=r.client_side,
            born_day=r.born_day,
        )
        for r in probes
    ]


@pytest.mark.parametrize("case", ADVISOR, ids=[c["label"] for c in ADVISOR])
def test_advisor_cases(case: dict[str, Any]) -> None:
    """Full advice (severity, title, detail TEXT, action, hedge plan), the joint hedge and
    the RFQ risk impact, on crafted books covering every branch."""
    book = _book(case["book"])
    m = _market(case["market"])
    step = case["step"]
    atol = _book_atol(book, m.spot)
    if step is None:
        advice, joint = advise_book(book, m, case["rv"]), joint_hedge(book, m)
    else:
        advice, joint = advise_book(book, m, case["rv"], step), joint_hedge(book, m, step)
    _assert_same([_advice_out(a) for a in advice], case["advice"], atol=atol, label="advice")
    _assert_same(_joint_out(joint), case["joint"], atol=atol, label="joint")
    if case["impacts"] is not None:
        impacts = [_impact_out(rfq_risk_impact(r, book, m)) for r in _probe_rfqs(m)]
        _assert_same(impacts, case["impacts"], atol=atol, label="impacts")


# ---------------------------------------------------------------------------- sessions

SESSION = GOLDEN["session"]
CONST = SESSION["constants"]
NOISE_FRAC: float = CONST["NOISE_FRAC"]
HEDGE_TENOR: float = CONST["HEDGE_TENOR"]
MAX_QUEUE: int = CONST["MAX_QUEUE"]
EXPIRE_DAYS: int = CONST["EXPIRE_DAYS"]
RFQ_ARRIVAL_PROB: float = CONST["RFQ_ARRIVAL_PROB"]
SPREADS: list[float] = CONST["SPREADS"]
STRUCTURE_CYCLE: list[Any] = CONST["STRUCTURE_CYCLE"]
SNAP_EVERY: int = CONST["SNAP_EVERY"]
SESSIONS: dict[str, dict[str, Any]] = {s["cfg"]["name"]: s for s in SESSION["sessions"]}


def test_session_constants_are_the_ui_values() -> None:
    """The scripted desk uses the SimulatorView constants."""
    assert (NOISE_FRAC, HEDGE_TENOR, MAX_QUEUE, EXPIRE_DAYS, RFQ_ARRIVAL_PROB) == (
        0.08,
        60 / 365,
        4,
        4,
        0.4,
    )


def _exec_qty(q: float) -> float:
    """``Math.max(1, Math.round(q))``: plan quantities are rounded before trading."""
    return max(1.0, round_to(q, 1))


def _flip(side: LegSide) -> LegSide:
    return "short" if side == "long" else "long"


def _zero_vol(_K: float, _T: float) -> float:
    return 0.0


@cache
def _run_session(name: str) -> dict[str, Any]:
    """Line-by-line mirror of ``runSession`` in ``web/scripts/golden/sim.golden.ts``."""
    cfg = SESSIONS[name]["cfg"]
    strike_step: float = cfg["strikeStep"]
    costs = _costs(cfg["costs"])
    params = _params(cfg["params"])
    seeds = cfg["seeds"]

    def atm(x: float) -> float:
        return round_to(x, strike_step)

    rfq_rng = Mulberry32(seeds["rfq"])
    noise = NormalSampler(Mulberry32(seeds["noise"]))
    arrival = Mulberry32(seeds["arrival"])

    sim: MarketSimulator | None = None
    replay_next: Callable[[int], MarketState] | None = None
    window: dict[str, Any] | None = None
    if cfg["mode"] == "simulated":
        sim = MarketSimulator(_market(cfg["market0"]), params, seeds["market"])
        market = sim.state
        n_steps = cfg["steps"]
    else:
        rp = cfg["replay"]
        base = _replay_base(rp["base"])
        win = pick_window(
            synthetic_series(rp["seriesSeed"], rp["seriesLen"]),
            rp["length"],
            Mulberry32(seeds["replay"])(),
        )
        window = {"startIndex": win.start_index, "points": [_point_out(p) for p in win.points]}
        market = replay_state(win, 0, base)
        n_steps = min(cfg["steps"], window_steps(win))

        def replay_next(day: int) -> MarketState:
            return replay_state(win, day, base)

    book = empty_book()
    queue: list[RFQ] = []
    next_rfq_id = 1
    spots = [market.spot]
    rows: list[list[Any]] = []
    quotes: list[list[Any]] = []
    actions: list[dict[str, Any]] = []
    snaps: list[dict[str, Any]] = []

    for day in range(1, n_steps + 1):
        # 1) the market moves; explain the P&L of the book held over the step
        if sim is not None:
            nxt = sim.next().state
        else:
            assert replay_next is not None
            nxt = replay_next(day)
        att = attribute(book, market, nxt)
        market = nxt
        spots.append(market.spot)

        # 2) client flow: expire stale RFQs; maybe a new one arrives; the trader asks for one
        queue = [r for r in queue if day - r.born_day <= EXPIRE_DAYS]
        if len(queue) < MAX_QUEUE and arrival() < RFQ_ARRIVAL_PROB:
            queue.append(generate_rfq(market.spot, strike_step, rfq_rng, next_rfq_id, day))
            next_rfq_id += 1
        if day % 9 == 0 and len(queue) < MAX_QUEUE:
            queue.append(generate_rfq(market.spot, strike_step, rfq_rng, next_rfq_id, day))
            next_rfq_id += 1

        # 3) quote the head of the queue (or pass on it), leaning on the risk-impact verdict
        if queue:
            rfq = queue.pop(0)
            if day % 7 == 6:
                quotes.append([day, _rfq_out(rfq), True])
            else:
                impact = rfq_risk_impact(rfq, book, market)
                fair = rfq_fair(rfq, market)
                spread = SPREADS[day % 3]
                toward = -1 if rfq.client_side == "buy" else 1
                lean = (
                    0.02 * toward
                    if impact.verdict == "hedges"
                    else -0.02 * toward
                    if impact.verdict == "adds"
                    else 0.0
                )
                z = noise()
                fill = evaluate_quote(rfq, fair.net, fair.gross, spread, NOISE_FRAC, z, lean)
                book = add_fill(book, fill, rfq, market)
                quotes.append(
                    [
                        day,
                        _rfq_out(rfq),
                        False,
                        impact.verdict,
                        impact.d_delta,
                        impact.d_vega,
                        impact.d_gamma,
                        fair.net,
                        fair.gross,
                        spread,
                        lean,
                        z,
                        fill.filled,
                        fill.you_side,
                        fill.price,
                        fill.edge,
                        fill.bid,
                        fill.ask,
                    ]
                )

        # 4) risk management: a fixed schedule
        r_vol = realised_vol(spots, params.dt)
        if day % 20 == 11:
            jh = joint_hedge(book, market, strike_step)
            if jh.feasible:
                orders = [
                    OptionOrder(
                        type=leg.option_type if leg.option_type is not None else "call",
                        side="long" if leg.side == "buy" else "short",
                        quantity=_exec_qty(leg.quantity),
                        K=leg.K if leg.K is not None else atm(market.spot),
                        T=(leg.tenor_days if leg.tenor_days is not None else 30) / 365,
                    )
                    for leg in jh.legs
                    if leg.instrument == "option"
                ]
                book = trade_structure(book, orders, market, costs)
                book = hedge_to_flat(book, market, costs)
            actions.append(
                {"day": day, "kind": "joint", "feasible": jh.feasible, "legs": _joint_legs_out(jh)}
            )
        elif day % 10 == 5:
            book = flatten_vega(book, market, HEDGE_TENOR, costs)
            actions.append({"day": day, "kind": "flattenVega"})
        elif day % 15 == 7:
            book = flatten_gamma(book, market, HEDGE_TENOR, costs)
            actions.append({"day": day, "kind": "flattenGamma"})
        elif day % 25 == 13:
            preset = STRUCTURE_CYCLE[(day // 25) % len(STRUCTURE_CYCLE)]
            buy = (day // 25) % 2 == 0
            legs = build_preset(
                preset,
                PresetParams(
                    S=market.spot,
                    base_t=30 / 365,
                    width_pct=0.04,
                    strike_step=strike_step,
                    vol_for=_zero_vol,
                ),
            )
            structure = [
                OptionOrder(
                    type=leg.type,
                    side=leg.side if buy else _flip(leg.side),
                    quantity=leg.quantity * 5,
                    K=leg.K,
                    T=leg.T,
                )
                for leg in legs
            ]
            book = trade_structure(book, structure, market, costs)
            actions.append(
                {
                    "day": day,
                    "kind": "structure",
                    "preset": preset,
                    "buy": buy,
                    "nOrders": len(structure),
                }
            )
        elif day % 30 == 17:
            # load the advisor's first concrete plan into the ticket and execute it
            advice = advise_book(book, market, r_vol, strike_step)
            with_plan = next((a for a in advice if a.plan is not None), None)
            plan = with_plan.plan if with_plan is not None else None
            if plan is not None:
                qty = _exec_qty(plan.quantity)
                side: LegSide = "long" if plan.side == "buy" else "short"
                if plan.instrument == "future":
                    book = hedge_trade(book, qty if side == "long" else -qty, market, costs)
                else:
                    order = OptionOrder(
                        type=plan.option_type if plan.option_type is not None else "call",
                        side=side,
                        quantity=qty,
                        K=plan.K if plan.K is not None else atm(market.spot),
                        T=(plan.tenor_days if plan.tenor_days is not None else 60) / 365,
                    )
                    book = trade_option(book, order, market, costs)
            plan_out = _advice_out(with_plan)["plan"] if with_plan is not None else None
            actions.append({"day": day, "kind": "plan", "plan": plan_out})
        if day % 3 == 0:
            book = hedge_to_flat(book, market, costs)

        # 5) record
        rows.append(
            [
                day,
                market.t,
                market.spot,
                market.atm_vol,
                r_vol,
                book_value(book, market),
                book.cash,
                book.underlying_qty,
                book.next_id,
                len(book.trades),
                att.total,
                att.delta,
                att.gamma,
                att.theta,
                att.vega,
                att.vanna,
                att.volga,
                att.residual,
            ]
        )
        if day % SNAP_EVERY == 0 or day == n_steps:
            g = book_greeks(book, market)
            snaps.append(
                {
                    "day": day,
                    "realizedEdge": book.realized_edge,
                    "totalCosts": book.total_costs,
                    "greeks": {"raw": g.raw.as_dict(), "reported": g.reported.as_dict()},
                    "advice": [
                        _advice_out(a) for a in advise_book(book, market, r_vol, strike_step)
                    ],
                    "joint": _joint_out(joint_hedge(book, market, strike_step)),
                }
            )

    return {
        "window": window,
        "nSteps": n_steps,
        "rows": rows,
        "quotes": quotes,
        "actions": actions,
        "snaps": snaps,
        "finalBook": _book_out(book),
        "finalMarket": _market_out(market),
        "finalMarked": [[leg.id, leg.T, leg.sigma] for leg in marked_legs(book, market)],
        "atol": _book_atol(book, market.spot),
    }


def _session_atol(name: str) -> float:
    """One absolute floor per session: the largest book of the session sets the scale."""
    return float(_run_session(name)["atol"])


def _cols(columns: Sequence[str], row: Sequence[Any]) -> dict[str, Any]:
    return dict(zip(columns, row, strict=True))


NAMES = list(SESSIONS)


@pytest.mark.parametrize("name", NAMES)
def test_session_market_path_book_and_pnl_explain(name: str) -> None:
    """Day by day: the market (simulated or replayed), realised vol, book value, cash,
    hedge, trade count and the full P&L explain (delta … volga + residual)."""
    got, want = _run_session(name), SESSIONS[name]
    assert got["nSteps"] == want["nSteps"]
    _assert_same(got["window"], want["window"], atol=0.0, label="window")
    columns = SESSION["rowColumns"]
    atol = _session_atol(name)
    assert len(got["rows"]) == len(want["rows"])
    for g_row, w_row in zip(got["rows"], want["rows"], strict=True):
        g, w = _cols(columns, g_row), _cols(columns, w_row)
        # the first divergence is reported with its day and column
        _assert_same(g, w, atol=atol, label=f"{name} day {w['day']}")


@pytest.mark.parametrize("name", NAMES)
def test_session_rfqs_quotes_and_fills(name: str) -> None:
    """Every RFQ that reached the head of the queue (same ids, structures, strikes), its
    risk impact, fair, spread, lean, client noise z, and the fill."""
    got, want = _run_session(name), SESSIONS[name]
    atol = _session_atol(name)
    assert len(got["quotes"]) == len(want["quotes"])
    columns = SESSION["quoteColumns"]
    for g_q, w_q in zip(got["quotes"], want["quotes"], strict=True):
        label = f"{name} quote day {w_q[0]}"
        # the RFQ itself is pure arithmetic: exact
        assert g_q[:3] == w_q[:3], label
        if not w_q[2]:
            _assert_same(_cols(columns, g_q), _cols(columns, w_q), atol=atol, label=label)
    fills = [q for q in want["quotes"] if not q[2] and q[12]]
    assert fills, "the session should fill some RFQs"


@pytest.mark.parametrize("name", NAMES)
def test_session_hedging_actions(name: str) -> None:
    """The hedging schedule: joint-hedge legs, vega/gamma flattening, structures and the
    advisor's executed plan."""
    got, want = _run_session(name), SESSIONS[name]
    _assert_same(got["actions"], want["actions"], atol=_session_atol(name), label="actions")


@pytest.mark.parametrize("name", NAMES)
def test_session_snapshots(name: str) -> None:
    """Periodic snapshots: book greeks (raw + reported), the advisor's full output and the
    joint hedge."""
    got, want = _run_session(name), SESSIONS[name]
    _assert_same(got["snaps"], want["snaps"], atol=_session_atol(name), label="snaps")


@pytest.mark.parametrize("name", NAMES)
def test_session_final_book(name: str) -> None:
    """The final book (every trade, hedge, cash, edge, costs), market and marked legs."""
    got, want = _run_session(name), SESSIONS[name]
    atol = _session_atol(name)
    _assert_same(got["finalBook"], want["finalBook"], atol=atol, label="finalBook")
    _assert_same(got["finalMarket"], want["finalMarket"], atol=ATOL, label="finalMarket")
    _assert_same(got["finalMarked"], want["finalMarked"], atol=ATOL, label="finalMarked")


def test_session_tolerance_is_meaningful() -> None:
    """The scaled absolute floors stay far below anything a trader would read (a cent),
    and the sessions are big enough to be a real test (trades, fills, hedges)."""
    for name in NAMES:
        atol = _session_atol(name)
        assert math.isfinite(atol)
        assert atol < 1e-5, name
        assert len(SESSIONS[name]["finalBook"]["trades"]) >= 20, name
    assert RTOL <= 1e-10
