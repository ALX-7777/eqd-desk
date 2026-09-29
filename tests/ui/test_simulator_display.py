"""The simulator's display strings (:mod:`eqd_desk.app.ui.simulator_display`).

The full session is compared with the React text in ``test_sim_session_parity.py``; these
pin each helper's format on hand-built inputs (signs, the U+2212 minus, warnings, flags,
the blotter window, the advisor lines), including the values of the React screenshots.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from eqd_desk.app.ui.format import MINUS
from eqd_desk.app.ui.sim_session import (
    DELTA_WARN,
    VEGA_WARN,
    CumAttribution,
    HistPoint,
    QuotePreview,
    SimSession,
    TicketPreview,
    desk_config,
)
from eqd_desk.app.ui.simulator_display import (
    BLOTTER_ROWS,
    StatLine,
    attribution_bars,
    bid_ask_text,
    blotter_rows,
    book_rows,
    book_units,
    days_text,
    edge_costs_text,
    fill_rate,
    flatten_instruments,
    grouped_replay_caption,
    history_frame,
    impact_text,
    joint_leg_line,
    lean_text,
    market_stats,
    plan_line,
    pnl_caption,
    pnl_tag,
    pnl_trend,
    positions_count,
    positions_heading,
    prints_zero,
    replay_caption,
    rfq_chip,
    rfq_detail,
    rfq_legs,
    scorecard,
    settled,
    settled_value,
    show_joint,
    speed_text,
    spread_text,
    tick_theta_caption,
    ticket_cost_view,
    ticket_preview_text,
    warned,
)
from eqd_desk.content.simulator import ATTRIBUTION_TERMS, RFQ_VERDICT_HINTS
from eqd_desk.data import load_history, load_snapshot
from eqd_desk.engine.sim import (
    RFQ,
    BookGreeks,
    BookTrade,
    HedgePlan,
    JointHedge,
    JointLeg,
    RfqLeg,
    RiskImpact,
    book_greeks,
    empty_book,
)
from eqd_desk.engine.strategy import LegSide
from eqd_desk.engine.types import OptionType, RawGreeks, ReportedGreeks

SNAP = load_snapshot()
CFG = desk_config(SNAP)


def fresh() -> SimSession:
    return SimSession(CFG, load_history().series)


def greeks(delta: float = 0.0, vega: float = 0.0, gamma: float = 0.0) -> BookGreeks:
    """Book greeks with the given REPORTED delta / vega and RAW gamma."""
    zero = dict.fromkeys(
        (
            "price",
            "delta",
            "gamma",
            "vega",
            "theta",
            "rho",
            "vanna",
            "volga",
            "charm",
            "speed",
            "color",
        ),
        0.0,
    )
    raw = RawGreeks(**{**zero, "gamma": gamma})
    rep = ReportedGreeks(**{**zero, "delta": delta, "vega": vega, "gamma": gamma})
    return BookGreeks(raw=raw, reported=rep)


# ------------------------------------------------------------------ market & scorecard


def test_market_stats_at_the_seed() -> None:
    desk = fresh()
    assert market_stats(desk.state, "simulated", None, None) == [
        StatLine("Spot", "6,312.45"),
        StatLine("ATM vol (implied)", "14.60%", "accent"),
        StatLine("Realised vol", "—", "neg"),
        StatLine("Skew slope", "-0.480"),
    ]  # react_ref/4a_simulator.png


def test_market_stats_realised_tone_and_replay_day() -> None:
    desk = fresh()
    above = market_stats(desk.state, "simulated", 0.20, None)[2]
    below = market_stats(desk.state, "simulated", 0.10, None)[2]
    assert (above.text, above.tone) == ("20.00%", "pos")
    assert (below.text, below.tone) == ("10.00%", "neg")
    desk.switch_mode("historical", 120)
    assert market_stats(desk.state, "historical", None, desk.replay_max)[3] == StatLine(
        "Replay day", "0 / 120"
    )  # react_ref/4b_simulator_replay.png


def test_small_market_texts() -> None:
    assert (
        replay_caption(2010)
        == "Undisclosed slice of real S&P 500 / VIX history (2010 days on file)."
    )
    assert days_text(120) == "120 days"
    assert speed_text(650) == "650 ms/day"
    assert spread_text(0.05) == "5.00%"
    assert (lean_text(0.0), lean_text(0.0075), lean_text(-0.01)) == ("+0.00%", "+0.75%", "-1.00%")


def test_scorecard_at_the_seed() -> None:
    desk = fresh()
    s = desk.state
    assert scorecard(s, book_greeks(s.book, s.market), 0.0) == [
        StatLine("P&L", "+0.00", "zero"),
        StatLine("Edge captured", "0.00", "pos"),
        StatLine("Costs paid", f"{MINUS}0.00", "neg"),
        StatLine("Fill rate", "0% (0/0)"),
        StatLine("Net Δ", "0", "dim"),
        StatLine("Net vega", "0", "dim"),
    ]  # react_ref/4a_simulator.png


def test_scorecard_flags_large_delta_and_vega() -> None:
    s = replace(fresh().state, quotes=3, fills=1)
    lines = scorecard(s, greeks(delta=29.845, vega=-2105.9), 17959.06)
    assert lines[0] == StatLine("P&L", "+17,959.06", "pos")
    assert lines[3].text == "33% (1/3)"
    assert lines[4] == StatLine("Net Δ", "29.845", "dim")  # below 40: no warning
    assert lines[5] == StatLine("Net vega", "-2105.9 ⚠", "neg")  # react_ref/4d
    assert scorecard(s, greeks(delta=-41), -5.0)[4] == StatLine("Net Δ", "-41.000 ⚠", "neg")
    assert scorecard(s, greeks(), -5.0)[0] == StatLine("P&L", "-5.00", "neg")
    assert warned(DELTA_WARN + 0.1, DELTA_WARN)
    assert not warned(-VEGA_WARN, VEGA_WARN)


def test_fill_rate() -> None:
    s = fresh().state
    assert fill_rate(s) == 0.0
    assert fill_rate(replace(s, quotes=4, fills=3)) == 0.75


# ------------------------------------------------------------------ RFQs


def _rfq(side: str = "buy", legs: tuple[RfqLeg, ...] | None = None, size: float = 100) -> RFQ:
    return RFQ(
        id=1,
        label="Put",
        legs=legs or (RfqLeg("put", "long", 1, 6150, 1),),
        size=size,
        client_side=side,  # type: ignore[arg-type]
    )


def test_rfq_chip_and_detail_of_the_reference_screenshot() -> None:
    chip = rfq_chip(_rfq(), 273.86532123775714, "neutral")
    assert (chip.arrow, chip.text, chip.flag, chip.net, chip.hint) == (
        "▲",
        "100× Put",
        "",
        "273.87",
        "",
    )
    assert rfq_detail(_rfq(), 273.86532123775714) == "CLIENT BUYS · +1 P6150 · net 273.87"  # 4c


def test_rfq_chip_flags() -> None:
    hedges = rfq_chip(_rfq("sell"), 10.0, "hedges")
    adds = rfq_chip(_rfq("sell"), 10.0, "adds")
    assert (hedges.arrow, hedges.flag, hedges.hint) == ("▼", "↓", RFQ_VERDICT_HINTS["hedges"])
    assert (adds.flag, adds.hint) == ("↑", RFQ_VERDICT_HINTS["adds"])


def test_rfq_legs_print_ratios_signs_and_rounded_strikes() -> None:
    fly = (
        RfqLeg("call", "long", 1, 6025, 0.25),
        RfqLeg("call", "short", 2, 6312.5, 0.25),
        RfqLeg("call", "long", 1, 6600, 0.25),
    )
    assert rfq_legs(_rfq(legs=fly)) == f"+1 C6025 {MINUS}2 C6313 +1 C6600"
    assert rfq_detail(_rfq("sell", fly, 25), -1.5).startswith("CLIENT SELLS · ")


def test_impact_text_prefixes_the_flag() -> None:
    def impact(verdict: str) -> RiskImpact:
        return RiskImpact(d_delta=0, d_vega=0, d_gamma=0, verdict=verdict, note="note")  # type: ignore[arg-type]

    assert impact_text(impact("hedges")) == "↓ note"
    assert impact_text(impact("adds")) == "↑ note"
    assert impact_text(impact("neutral")) == "note"


def test_bid_ask_text() -> None:
    assert bid_ask_text(QuotePreview(mid=273.87, bid=267.02, ask=280.71)) == (
        "bid 267.02",
        "ask 280.71",
    )


# ------------------------------------------------------------------ P&L


def test_pnl_texts() -> None:
    assert (pnl_tag(0.0), pnl_tag(-0.01)) == ("up", "down")
    assert pnl_caption("USD") == "mark-to-market P&L (USD)"
    book = replace(empty_book(), realized_edge=684.66, total_costs=1234.5)
    assert edge_costs_text(book) == "edge 684.66 · costs 1,234.50"


def test_history_frame_and_attribution_bars() -> None:
    frame = history_frame((HistPoint(0, 100.0, 0.2, 0.0), HistPoint(1, 101.0, 0.19, 5.0)))
    assert list(frame.columns) == ["day", "spot", "vol", "pnl"]
    assert frame["pnl"].tolist() == [0.0, 5.0]
    labels, values = attribution_bars(CumAttribution(1, 2, 3, 4, 5, 6, 7))
    assert labels == [t.label for t in ATTRIBUTION_TERMS]
    assert labels == ["Delta", "Gamma", "Theta", "Vega", "Vanna", "Volga", "Residual"]
    assert values == [1, 2, 3, 4, 5, 6, 7]


# ------------------------------------------------------------------ book


def test_book_rows() -> None:
    rows = book_rows(greeks(delta=29.845, vega=-2105.9, gamma=-0.067598), 0.0)
    assert [r.label for r in rows] == ["Delta", "Gamma", "Vega", "Theta", "Hedge (underlying)"]
    assert rows[0] == StatLine("Delta", "29.845", "pos")
    assert rows[2] == StatLine("Vega", "-2105.9", "neg")
    assert rows[3] == StatLine("Theta", "0", "zero")
    assert rows[4] == StatLine("Hedge (underlying)", "0", "zero")
    assert book_rows(greeks(), -12.3456)[4] == StatLine("Hedge (underlying)", "-12.3", "neg")


def _trade(i: int, side: LegSide = "short", kind: OptionType = "put") -> BookTrade:
    return BookTrade(
        id=i, type=kind, side=side, quantity=100, K=6150, expiry_time=1.0, traded_price=1.0
    )


def test_blotter_lists_the_hedge_then_the_latest_trades() -> None:
    trades = tuple(_trade(i, "long" if i % 2 else "short") for i in range(1, 12))
    book = replace(empty_book(), trades=trades, underlying_qty=-30.44)
    m = replace(CFG.initial_market, t=8 / 365)
    rows = blotter_rows(book, m)
    assert len(rows) == 1 + BLOTTER_ROWS
    assert (rows[0].qty, rows[0].instrument, rows[0].note, rows[0].tone) == (
        f"{MINUS}30",
        "FUTURE",
        "Δ-hedge",
        "neg",
    )
    assert [r.qty for r in rows[1:3]] == [f"{MINUS}100", "+100"]  # trades 4 (short), 5 (long)
    assert rows[1].instrument == "P 6,150.00"
    assert rows[1].note == "357d"  # round((1 − 8/365)·365)
    assert positions_count(book) == 12
    assert positions_heading(book) == "Positions (12)"
    expired = blotter_rows(replace(book, underlying_qty=0.0), replace(m, t=2.0))
    assert expired[0].note == "0d"
    assert positions_count(empty_book()) == 0


def test_ticket_preview_text() -> None:
    assert ticket_preview_text(TicketPreview("price", 174.27, 17.427)) == (
        "price 174.27",
        f"cost {MINUS}17.43",
    )  # react_ref/4a_simulator.png
    assert ticket_preview_text(TicketPreview("net", -3.0, 0.0))[0] == "net -3.00"


# ------------------------------------------------------------------ advisor


def test_plan_lines() -> None:
    fut = HedgePlan(instrument="future", side="sell", quantity=29.8, rationale="")
    opt = HedgePlan(
        instrument="option",
        side="buy",
        quantity=1217.6,
        rationale="",
        option_type="call",
        K=6200,
        tenor_days=60,
    )
    assert plan_line(fut) == ("SELL", "30 × FUTURE")  # react_ref/4d
    assert plan_line(opt) == ("BUY", "1,218 × Call 6200 · 60d")


def test_joint_leg_lines_and_roles() -> None:
    gamma = JointLeg(
        instrument="option", side="buy", quantity=16.6, option_type="call", K=6200, tenor_days=21
    )
    vega = JointLeg(
        instrument="option", side="sell", quantity=0.2, option_type="call", K=6200, tenor_days=180
    )
    fut = JointLeg(instrument="future", side="buy", quantity=3.4)
    assert joint_leg_line(gamma) == ("BUY", "17 × Call 6200 · 21d", "gamma")
    assert joint_leg_line(vega) == ("SELL", "0 × Call 6200 · 180d", "vega")
    assert joint_leg_line(fut) == ("BUY", "3 × FUTURE", "cleans up Δ (last)")


@pytest.mark.parametrize(
    ("feasible", "vega", "gamma", "shown"),
    [
        (True, 100.0, 1e-5, True),
        (True, -100.0, -1e-5, True),
        (False, 100.0, 1e-5, False),
        (True, 80.0, 1e-5, False),
        (True, 100.0, 1e-6, False),
    ],
)
def test_show_joint_needs_both_gamma_and_vega(
    feasible: bool, vega: float, gamma: float, shown: bool
) -> None:
    jh = JointHedge(feasible=feasible, legs=(), rationale="")
    assert show_joint(jh, greeks(vega=vega, gamma=gamma)) is shown


# ------------------------------------------------------------------ departures from React


@pytest.mark.parametrize(
    ("text", "zero"),
    [
        ("0", True),
        ("0.00", True),
        (f"{MINUS}0.00", True),
        ("-0.000", True),
        ("+0.00", True),
        ("0%", True),
        ("0.01", False),
        (f"{MINUS}17.43", False),
        ("6,312.45", False),
        ("0% (0/0)", False),
        ("-1.36e-13", False),
        ("—", False),
    ],
)
def test_prints_zero(text: str, zero: bool) -> None:
    assert prints_zero(text) is zero


def test_settled_value_takes_the_sign_and_colour_off_a_zero() -> None:
    assert settled_value(f"{MINUS}0.00", "neg") == ("0.00", "zero")
    assert settled_value("0.00", "pos") == ("0.00", "zero")
    assert settled_value("+0.00", "zero") == ("+0.00", "zero")  # a P&L keeps its "+"
    assert settled_value("—", "neg") == ("—", "zero")  # missing: grey, not red
    assert settled_value(f"{MINUS}17.43", "neg") == (f"{MINUS}17.43", "neg")
    assert settled_value("0% (0/0)", None) == ("0% (0/0)", None)


def test_the_seed_desk_shows_no_red_or_signed_zero() -> None:
    """React shows "Costs paid −0.00" in red, a green "0.00" edge and a red dash for the
    realised vol on a fresh desk; the page shows them grey and unsigned."""
    s = fresh().state
    card = [settled(ln) for ln in scorecard(s, book_greeks(s.book, s.market), 0.0)]
    assert card[:3] == [
        StatLine("P&L", "+0.00", "zero"),
        StatLine("Edge captured", "0.00", "zero"),
        StatLine("Costs paid", "0.00", "zero"),
    ]
    market = [settled(ln) for ln in market_stats(s, "simulated", None, None)]
    assert market[2] == StatLine("Realised vol", "—", "zero")
    # a real value is untouched
    assert settled(StatLine("Costs paid", f"{MINUS}17.43", "neg")).tone == "neg"


def test_pnl_trend_is_flat_while_the_pnl_prints_as_zero() -> None:
    assert [pnl_trend(x) for x in (0.0, 0.004, -0.004, 0.005, -0.01)] == [
        "flat",
        "flat",
        "flat",
        "up",
        "down",
    ]
    assert pnl_tag(0.0) == "up"  # React


def test_ticket_cost_view() -> None:
    assert ticket_cost_view(TicketPreview("price", 174.27, 17.427)) == (f"cost {MINUS}17.43", "neg")
    # a far out-of-the-money option: price 0.00, cost 0.00 (React: "cost −0.00" in red)
    assert ticket_cost_view(TicketPreview("price", 1e-9, 1e-11)) == ("cost 0.00", "zero")
    assert ticket_cost_view(TicketPreview("price", 0.0, 0.0)) == ("cost 0.00", "zero")


def test_grouped_replay_caption_does_not_read_as_a_year() -> None:
    assert grouped_replay_caption(2010) == (
        "Undisclosed slice of real S&P 500 / VIX history (2,010 days on file)."
    )
    assert replay_caption(2010).endswith("(2010 days on file).")  # React


def test_book_units_follow_the_book_rows_and_the_currency() -> None:
    rows = book_rows(greeks(), 0.0)
    units = book_units("USD")
    assert len(units) == len(rows)
    assert units == [
        "per $1 spot",
        "Δdelta per $1 spot",
        "per 1 vol pt",
        "per day",
        "index units",
    ]
    assert book_units("EUR")[0] == "per €1 spot"


def test_tick_theta_caption() -> None:
    assert tick_theta_caption(1 / 252) == (
        "Theta is per calendar day; a Tick is one trading day (1/252 y ≈ 1.45 calendar days), "
        "so a Tick's theta P&L ≈ 1.45 × Theta."
    )


def test_a_ticks_theta_pnl_is_365_dt_times_the_book_theta() -> None:
    """What the caption claims, on the engine: one Tick's theta term of the P&L explain is
    the book's (per calendar day) Theta × 365·dt, 1.45 with dt = 1/252."""
    desk = fresh()
    desk.request_rfq()
    desk.quote(0.05, 0.0)
    s = desk.state
    theta_per_day = book_greeks(s.book, s.market).reported.theta
    assert theta_per_day != 0
    desk.tick()
    dt = desk.cfg.params.dt
    assert dt == pytest.approx(1 / 252)
    assert desk.state.cum_attr.theta == pytest.approx(theta_per_day * 365 * dt, rel=1e-12)
    assert 365 * dt == pytest.approx(1.448, abs=1e-3)


def test_flatten_instruments_names_the_hedge_of_each_button() -> None:
    assert flatten_instruments() == "Δ trades the index future; vega and Γ trade a 60-day ATM call."
