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
    days_text,
    edge_costs_text,
    fill_rate,
    history_frame,
    impact_text,
    joint_leg_line,
    lean_text,
    market_stats,
    plan_line,
    pnl_caption,
    pnl_tag,
    positions_count,
    positions_heading,
    replay_caption,
    rfq_chip,
    rfq_detail,
    rfq_legs,
    scorecard,
    show_joint,
    speed_text,
    spread_text,
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
