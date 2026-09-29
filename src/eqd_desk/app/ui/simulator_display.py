"""What the simulator page SHOWS: every label, number and message of its panels as plain
strings with a tone, string-identical to the React ``SimulatorView``.

Pure (no Streamlit): the panels (:mod:`eqd_desk.app.ui.simulator_panels`) render these, and
``tests/ui/test_sim_session_parity.py`` checks them against the text the real React component
rendered for the same seeded session. Numbers are formatted by :mod:`eqd_desk.app.ui.format`
(JavaScript rounding), so a value prints exactly as in the React app.

The last section lists where the page deliberately departs from the React text (a zero
never shows a minus sign or a colour, the P&L badge can read "flat", the replay caption
groups its day count, the book table carries units). Those are small functions the panels
apply on top of the React strings, so the parity test keeps checking the strings beneath.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final, Literal

import pandas as pd

from eqd_desk.app.ui.format import (
    EM_DASH,
    MINUS,
    fmt_money,
    fmt_num,
    fmt_pct,
    fmt_signed_money,
    fmt_signed_pct,
    js_number,
    js_round,
    sign_class,
    to_locale,
)
from eqd_desk.app.ui.sim_session import (
    COSTS,
    DELTA_WARN,
    HEDGE_TENOR,
    JOINT_MIN_GAMMA,
    JOINT_MIN_VEGA,
    VEGA_WARN,
    CumAttribution,
    HistPoint,
    Mode,
    QuotePreview,
    SimState,
    TicketPreview,
    plan_quantity,
)
from eqd_desk.app.ui.theme import Tone
from eqd_desk.app.ui.units import greek_unit
from eqd_desk.content.simulator import (
    ATTRIBUTION_TERMS,
    FLATTEN_DELTA_HELP_TEMPLATE,
    FLATTEN_INSTRUMENTS_TEMPLATE,
    FLATTEN_OPTION_HELP_TEMPLATE,
    HEDGE_UNIT,
    REPLAY_CAPTION_TEMPLATE,
    RFQ_VERDICT_HINTS,
    TICK_THETA_CAPTION_TEMPLATE,
    joint_hedge_role,
)
from eqd_desk.engine.sim import (
    RFQ,
    Book,
    BookGreeks,
    HedgePlan,
    JointHedge,
    JointLeg,
    MarketState,
    RiskImpact,
    RiskVerdict,
    Severity,
)

WARN_MARK: Final = "⚠"
"""Appended to a scorecard greek above its warning level."""

BUY_ARROW: Final = "▲"
"""An RFQ chip's marker when the client buys."""
SELL_ARROW: Final = "▼"
"""An RFQ chip's marker when the client sells."""

VERDICT_ARROWS: Final[dict[RiskVerdict, str]] = {"hedges": "↓", "adds": "↑", "neutral": ""}
"""Risk flag of an RFQ: winning it cuts (↓) or adds (↑) risk."""


@dataclass(frozen=True, slots=True)
class StatLine:
    """One "label · value" line of a panel; ``tone`` colours the value (``None`` = plain)."""

    label: str
    text: str
    tone: Tone | None = None


# ------------------------------------------------------------------ market panel


def market_stats(
    state: SimState, mode: Mode, realised: float | None, replay_max: int | None
) -> list[StatLine]:
    """Spot, ATM implied vol, realised vol (green when above implied: long gamma wins) and
    the skew slope, or in Replay the day of the episode."""
    m = state.market
    rv_tone: Tone = "pos" if realised is not None and realised > m.atm_vol else "neg"
    last = (
        StatLine("Replay day", f"{state.day} / {replay_max if replay_max is not None else '∞'}")
        if mode == "historical"
        else StatLine("Skew slope", fmt_num(m.skew_slope if m.skew_slope is not None else 0.0, 3))
    )
    return [
        StatLine("Spot", fmt_money(m.spot)),
        StatLine("ATM vol (implied)", fmt_pct(m.atm_vol), "accent"),
        StatLine("Realised vol", fmt_pct(realised) if realised is not None else EM_DASH, rv_tone),
        last,
    ]


def replay_caption(count: int) -> str:
    """ "Undisclosed slice of real S&P 500 / VIX history (2010 days on file)."."""
    return REPLAY_CAPTION_TEMPLATE.format(count=count)


def days_text(days: float) -> str:
    """The replay-length display: ``"120 days"``."""
    return f"{js_number(days)} days"


def speed_text(ms: float) -> str:
    """The auto-speed display: ``"650 ms/day"``."""
    return f"{js_number(ms)} ms/day"


# ------------------------------------------------------------------ scorecard


def fill_rate(state: SimState) -> float:
    """Fills per quote shown (0 before the first quote)."""
    return state.fills / state.quotes if state.quotes > 0 else 0.0


def warned(value: float, limit: float) -> bool:
    """Whether a net greek is above its scorecard warning level."""
    return abs(value) > limit


def scorecard(state: SimState, greeks: BookGreeks, pnl: float) -> list[StatLine]:
    """P&L, edge captured, costs paid, fill rate, net delta and net vega (flagged ⚠ above
    40 delta / 1,500 vega)."""
    book = state.book
    delta = greeks.reported.delta
    vega = greeks.reported.vega
    dw, vw = warned(delta, DELTA_WARN), warned(vega, VEGA_WARN)
    return [
        StatLine("P&L", fmt_signed_money(pnl), sign_class(pnl)),
        StatLine("Edge captured", fmt_money(book.realized_edge), "pos"),
        StatLine("Costs paid", f"{MINUS}{fmt_money(book.total_costs)}", "neg"),
        StatLine("Fill rate", f"{fmt_pct(fill_rate(state), 0)} ({state.fills}/{state.quotes})"),
        StatLine(
            "Net Δ",
            f"{fmt_num(delta)} {WARN_MARK}" if dw else fmt_num(delta),
            "neg" if dw else "dim",
        ),
        StatLine(
            "Net vega",
            f"{fmt_num(vega)} {WARN_MARK}" if vw else fmt_num(vega),
            "neg" if vw else "dim",
        ),
    ]


# ------------------------------------------------------------------ RFQ queue and quote box


@dataclass(frozen=True, slots=True)
class RfqChip:
    """One RFQ of the queue: the client's side, the package, the risk flag and the net fair."""

    arrow: str
    """▲ client buys / ▼ client sells."""
    text: str
    """``"100× Put"``."""
    flag: str
    """↓ winning it cuts your risk, ↑ adds risk, empty when neutral."""
    net: str
    """Net fair of one package."""
    hint: str
    """Tooltip of the flag."""
    verdict: RiskVerdict


def rfq_chip(rfq: RFQ, net: float, verdict: RiskVerdict) -> RfqChip:
    """The queue line of an RFQ."""
    return RfqChip(
        arrow=BUY_ARROW if rfq.client_side == "buy" else SELL_ARROW,
        text=f"{js_number(rfq.size)}× {rfq.label}",
        flag=VERDICT_ARROWS[verdict],
        net=fmt_money(net),
        hint=RFQ_VERDICT_HINTS[verdict] if verdict != "neutral" else "",
        verdict=verdict,
    )


def rfq_legs(rfq: RFQ) -> str:
    """The package as the client would hold it if they buy: ``"+1 C6400 −1 C6600"``."""
    return " ".join(
        f"{'+' if leg.side == 'long' else MINUS}{js_number(leg.ratio)} "
        f"{'C' if leg.type == 'call' else 'P'}{js_round(leg.K)}"
        for leg in rfq.legs
    )


def rfq_detail(rfq: RFQ, net: float) -> str:
    """``"CLIENT BUYS · +1 P6150 · net 273.87"``."""
    return f"CLIENT {rfq.client_side.upper()}S · {rfq_legs(rfq)} · net {fmt_money(net)}"


def impact_text(impact: RiskImpact) -> str:
    """The risk note under the RFQ detail, with its ↓ / ↑ flag."""
    arrow = VERDICT_ARROWS[impact.verdict]
    return f"{arrow} {impact.note}" if arrow else impact.note


def spread_text(spread: float) -> str:
    """The spread display: ``"5.00%"`` (of the package's gross premium)."""
    return fmt_pct(spread)


def lean_text(lean: float) -> str:
    """The lean display: ``"+0.75%"`` / ``"-1.00%"``."""
    return fmt_signed_pct(lean)


def bid_ask_text(q: QuotePreview) -> tuple[str, str]:
    """``("bid 267.02", "ask 280.71")``."""
    return f"bid {fmt_money(q.bid)}", f"ask {fmt_money(q.ask)}"


# ------------------------------------------------------------------ P&L panel


def pnl_tag(pnl: float) -> Literal["up", "down"]:
    """The P&L panel's tag."""
    return "up" if pnl >= 0 else "down"


def pnl_caption(currency: str) -> str:
    """``"mark-to-market P&L (USD)"``."""
    return f"mark-to-market P&L ({currency})"


def edge_costs_text(book: Book) -> str:
    """``"edge 684.66 · costs 0.00"``."""
    return f"edge {fmt_money(book.realized_edge)} · costs {fmt_money(book.total_costs)}"


def history_frame(history: Sequence[HistPoint]) -> pd.DataFrame:
    """The session path as a frame: ``day``, ``spot``, ``vol`` (decimal), ``pnl``."""
    return pd.DataFrame(
        {
            "day": [h.day for h in history],
            "spot": [h.spot for h in history],
            "vol": [h.vol for h in history],
            "pnl": [h.pnl for h in history],
        }
    )


def attribution_bars(cum: CumAttribution) -> tuple[list[str], list[float]]:
    """Labels and values of the cumulative P&L explain, in the chart's order (delta, gamma,
    theta, vega, vanna, volga, residual)."""
    values = cum.as_dict()
    return [t.label for t in ATTRIBUTION_TERMS], [values[t.key] for t in ATTRIBUTION_TERMS]


# ------------------------------------------------------------------ book & hedging

BOOK_GREEKS: Final = ("delta", "gamma", "vega", "theta")
"""Net greeks shown in the book panel (desk units)."""


def book_rows(greeks: BookGreeks, underlying_qty: float) -> list[StatLine]:
    """Net delta, gamma, vega, theta (desk units) and the future hedge position."""
    rep = greeks.reported.as_dict()
    rows = [StatLine(k.capitalize(), fmt_num(rep[k]), sign_class(rep[k])) for k in BOOK_GREEKS]
    rows.append(
        StatLine("Hedge (underlying)", fmt_num(underlying_qty, 3), sign_class(underlying_qty))
    )
    return rows


def positions_count(book: Book) -> int:
    """Option trades, plus one line for the future hedge when there is one."""
    return len(book.trades) + (1 if book.underlying_qty != 0 else 0)


def positions_heading(book: Book) -> str:
    """``"Positions (3)"``."""
    return f"Positions ({positions_count(book)})"


@dataclass(frozen=True, slots=True)
class BlotterRow:
    """One position line: signed size, instrument, remaining days (or "Δ-hedge")."""

    qty: str
    instrument: str
    note: str
    tone: Tone


BLOTTER_ROWS: Final = 8
"""How many of the latest option trades the blotter lists."""


def blotter_rows(book: Book, market: MarketState, limit: int = BLOTTER_ROWS) -> list[BlotterRow]:
    """The future hedge (if any), then the latest ``limit`` option trades, oldest first."""
    rows: list[BlotterRow] = []
    if book.underlying_qty != 0:
        long = book.underlying_qty > 0
        rows.append(
            BlotterRow(
                qty=f"{'+' if long else MINUS}{fmt_num(abs(book.underlying_qty), 1)}",
                instrument="FUTURE",
                note="Δ-hedge",
                tone="pos" if long else "neg",
            )
        )
    for t in book.trades[-limit:] if limit > 0 else ():
        days = max(0, js_round((t.expiry_time - market.t) * 365))
        rows.append(
            BlotterRow(
                qty=f"{'+' if t.side == 'long' else MINUS}{fmt_num(t.quantity, 1)}",
                instrument=f"{'C' if t.type == 'call' else 'P'} {fmt_money(t.K)}",
                note=f"{days}d",
                tone="pos" if t.side == "long" else "neg",
            )
        )
    return rows


# ------------------------------------------------------------------ trade ticket


def ticket_preview_text(p: TicketPreview) -> tuple[str, str]:
    """``("price 174.27", "cost −17.43")`` (``net …`` for a structure, ``spot …`` for the
    future)."""
    return f"{p.label} {fmt_money(p.value)}", f"cost {MINUS}{fmt_money(p.cost)}"


# ------------------------------------------------------------------ advisor

SEVERITY_TONES: Final[dict[Severity, Literal["red", "orange", "blue", "green"]]] = {
    "high": "red",
    "medium": "orange",
    "low": "blue",
    "ok": "green",
}
"""Colour of each advice severity (a Streamlit Markdown colour name)."""

SEVERITY_ICONS: Final[dict[Severity, str]] = {
    "high": ":material/error:",
    "medium": ":material/warning:",
    "low": ":material/info:",
    "ok": ":material/check_circle:",
}
"""Icon of each advice severity."""


def severity_marker(severity: Severity) -> str:
    """The advisor's severity marker as Markdown, the icon in the severity's colour
    (``":red[:material/error:]"``; React: a coloured dot)."""
    return f":{SEVERITY_TONES[severity]}[{SEVERITY_ICONS[severity]}]"


# ------------------------------------------------------------------ hedge buttons

FlattenTarget = Literal["delta", "vega", "gamma"]
"""The greek a flatten button brings to zero."""


def flatten_help(target: FlattenTarget) -> str:
    """Tooltip of a flatten button, with the desk's hedge instrument and cost filled in:
    the future at :data:`~eqd_desk.app.ui.sim_session.COSTS`' half-spread for delta
    (``"… (1 bp of spot)."``), a :data:`~eqd_desk.app.ui.sim_session.HEDGE_TENOR` ATM call
    at the option half-spread for vega and gamma (``"Trade a 60-day ATM call … (1% of
    premium)."``)."""
    if target == "delta":
        bp = js_number(round(COSTS.underlying_half_spread * 1e4, 6))
        return FLATTEN_DELTA_HELP_TEMPLATE.format(cost=f"{bp} bp")
    return FLATTEN_OPTION_HELP_TEMPLATE.format(
        days=js_round(HEDGE_TENOR * 365),
        greek=target,
        cost=fmt_pct(COSTS.option_half_spread, 0),
    )


def flatten_instruments() -> str:
    """Which instrument each hedge button trades (the buttons are labelled with the greek
    alone): ``"Δ trades the index future; vega and Γ trade a 60-day ATM call."``."""
    return FLATTEN_INSTRUMENTS_TEMPLATE.format(days=js_round(HEDGE_TENOR * 365))


def _instrument_text(
    instrument: str, option_type: str | None, K: float | None, tenor_days: int | None
) -> str:
    if instrument == "future":
        return "FUTURE"
    kind = "Put" if option_type == "put" else "Call"
    k = js_number(K) if K is not None else "undefined"
    d = str(tenor_days) if tenor_days is not None else "undefined"
    return f"{kind} {k} · {d}d"


def plan_line(plan: HedgePlan) -> tuple[str, str]:
    """``("SELL", "30 × FUTURE")`` / ``("BUY", "218 × Call 6200 · 60d")``."""
    qty = to_locale(float(plan_quantity(plan.quantity)), 0, 0)
    return (
        plan.side.upper(),
        f"{qty} × {_instrument_text(plan.instrument, plan.option_type, plan.K, plan.tenor_days)}",
    )


def joint_leg_line(leg: JointLeg) -> tuple[str, str, str]:
    """``("BUY", "17 × Call 6200 · 21d", "gamma")``: side, size × instrument, role."""
    qty = to_locale(float(max(0, js_round(leg.quantity))), 0, 0)
    text = f"{qty} × {_instrument_text(leg.instrument, leg.option_type, leg.K, leg.tenor_days)}"
    return leg.side.upper(), text, joint_hedge_role(leg.instrument, leg.tenor_days)


def show_joint(jh: JointHedge, greeks: BookGreeks) -> bool:
    """Offer the combined hedge only when it is feasible and BOTH vega and gamma are
    meaningfully exposed (otherwise a single-greek hedge is the right tool)."""
    return (
        jh.feasible
        and abs(greeks.reported.vega) > JOINT_MIN_VEGA
        and abs(greeks.raw.gamma) > JOINT_MIN_GAMMA
    )


# ------------------------------------------------------------------ departures from React
# Deliberate fixes the page applies on top of the React text above (React shows a red
# "−0.00", a red "—", an "up" badge at zero and "2010 days on file", which reads as a year).

_ZERO_TEXT: Final = re.compile(rf"[+\-{MINUS}]?0(?:\.0+)?%?")
"""A value that prints as zero: ``0``, ``0.00``, ``−0.00``, ``+0.000``, ``0%``."""


def prints_zero(text: str) -> bool:
    """Whether a formatted value reads as zero (whatever its sign)."""
    return _ZERO_TEXT.fullmatch(text) is not None


def settled_value(text: str, tone: Tone | None) -> tuple[str, Tone | None]:
    """A value as the page shows it: one that prints as zero loses its minus sign and its
    colour (``−0.00`` in red → ``0.00`` in grey; a P&L keeps its ``+``, the React P&L
    convention), and a missing value (``—``) is grey, not red."""
    if text == EM_DASH:
        return text, "zero"
    if prints_zero(text):
        return text.lstrip("-" + MINUS), "zero"
    return text, tone


def settled(line: StatLine) -> StatLine:
    """``line`` with :func:`settled_value` applied (every stat table of the page)."""
    text, tone = settled_value(line.text, line.tone)
    return replace(line, text=text, tone=tone)


PnlTrend = Literal["up", "down", "flat"]
"""The P&L panel's badge."""


def pnl_trend(pnl: float) -> PnlTrend:
    """The P&L badge the page shows: React's :func:`pnl_tag`, but ``"flat"`` while the P&L
    prints as zero (React says "up" at +0.00)."""
    return "flat" if prints_zero(fmt_money(pnl)) else pnl_tag(pnl)


def ticket_cost_view(p: TicketPreview) -> tuple[str, Tone]:
    """The ticket's execution cost as the page shows it: React's ``cost −17.43`` in red, or
    ``cost 0.00`` in grey when the cost prints as zero (a far out-of-the-money option)."""
    _, text = ticket_preview_text(p)
    if prints_zero(fmt_money(p.cost)):
        return f"cost {fmt_money(abs(p.cost))}", "zero"
    return text, "neg"


def grouped_replay_caption(count: int) -> str:
    """:func:`replay_caption` with the day count grouped (``"(2,010 days on file)"``; React
    prints ``2010``, which reads as a year)."""
    return REPLAY_CAPTION_TEMPLATE.format(count=to_locale(float(count)))


def book_units(currency: str) -> list[str]:
    """The unit of each :func:`book_rows` line, in order: the desk unit of each greek
    (:func:`~eqd_desk.app.ui.units.greek_unit`: theta is per CALENDAR day) and the hedge's
    :data:`~eqd_desk.content.simulator.HEDGE_UNIT`. React prints the numbers alone."""
    return [*(greek_unit(k, currency) for k in BOOK_GREEKS), HEDGE_UNIT]


def tick_theta_caption(dt: float) -> str:
    """Why a Tick's theta P&L is bigger than the book's Theta: a Tick is one trading day
    (``dt`` years, 1/252) while theta is quoted per calendar day, so a Tick's theta term is
    ``365·dt`` (≈ 1.45) times Theta."""
    return TICK_THETA_CAPTION_TEMPLATE.format(
        dt=f"1/{js_round(1 / dt)}", days=to_locale(365 * dt, 2, 2)
    )


__all__ = [
    "BLOTTER_ROWS",
    "BOOK_GREEKS",
    "BUY_ARROW",
    "SELL_ARROW",
    "SEVERITY_ICONS",
    "SEVERITY_TONES",
    "VERDICT_ARROWS",
    "WARN_MARK",
    "BlotterRow",
    "FlattenTarget",
    "PnlTrend",
    "RfqChip",
    "StatLine",
    "attribution_bars",
    "bid_ask_text",
    "blotter_rows",
    "book_rows",
    "book_units",
    "days_text",
    "edge_costs_text",
    "fill_rate",
    "flatten_help",
    "flatten_instruments",
    "grouped_replay_caption",
    "history_frame",
    "impact_text",
    "joint_leg_line",
    "lean_text",
    "market_stats",
    "plan_line",
    "pnl_caption",
    "pnl_tag",
    "pnl_trend",
    "positions_count",
    "positions_heading",
    "prints_zero",
    "replay_caption",
    "rfq_chip",
    "rfq_detail",
    "rfq_legs",
    "scorecard",
    "settled",
    "settled_value",
    "severity_marker",
    "show_joint",
    "speed_text",
    "spread_text",
    "tick_theta_caption",
    "ticket_cost_view",
    "ticket_preview_text",
    "warned",
]
