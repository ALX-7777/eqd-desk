"""The Python simulator session reproduces the REAL React ``SimulatorView``, action by action.

The golden (``tests/parity/golden/simsession.json``) is exported by
``web/scripts/golden/simsession.golden.ts``, which renders the React component in jsdom and
drives a scripted desk session through its own buttons, sliders and inputs (Tick, Auto on
fake timers, RFQ requests, spread / lean, Quote / Pass, the flatten buttons, every ticket
kind, the advisor's plans and combined hedge, Reset, Replay, the episode end). After every
action it recorded the component's internal state (read from its React fiber, full float
precision) and the text on screen.

Here :class:`_Driver` replays the same actions on a :class:`SimSession` (same seeds, same
draw order) and every step must match:

- the STATE: day, stats, selection, the RFQ queue, the fill line, the market, the book
  (cash, hedge, edge, costs, trades), the cumulative P&L explain and the whole history;
- the SCREEN: every label, number and tone the panels show, built by
  :mod:`eqd_desk.app.ui.simulator_display` (so the Streamlit page shows the React strings,
  apart from the few deliberate fixes that module's last section applies on top of them at
  render time, such as no minus sign or red on a zero; those are tested on their own in
  ``test_simulator_display.py``).

Tolerances: integers, labels and messages exactly; floats through exp/log with a relative
1e-9 and a money floor of 1e-6 (books reach ~1e6 in cash, so cancellation leaves ~1e-10).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace
from functools import cache
from typing import Any

import pytest

from eqd_desk.app.ui.format import fmt_signed_money, js_number, js_round, sign_class
from eqd_desk.app.ui.sim_session import (
    MAX_QUEUE,
    SimSession,
    Ticket,
    default_ticket,
    desk_config,
    quote_preview,
    ticket_from_plan,
    ticket_preview,
)
from eqd_desk.app.ui.simulator_display import (
    bid_ask_text,
    blotter_rows,
    book_rows,
    days_text,
    edge_costs_text,
    impact_text,
    joint_leg_line,
    lean_text,
    market_stats,
    plan_line,
    pnl_caption,
    pnl_tag,
    positions_heading,
    replay_caption,
    rfq_chip,
    rfq_detail,
    scorecard,
    show_joint,
    speed_text,
    spread_text,
    ticket_preview_text,
)
from eqd_desk.content.simulator import (
    ADVISOR_SUBTITLE,
    EMPTY_BOOK_HINT,
    EMPTY_QUEUE_HINT,
    EPISODE_ENDED_MESSAGE,
    JOINT_HEDGE_SUBTITLE,
    JOINT_HEDGE_TITLE,
    REPLAY_LENGTH_HINT,
)
from eqd_desk.data import load_history, load_snapshot
from eqd_desk.engine.presets import PRESETS
from eqd_desk.engine.sim import (
    RFQ,
    BookTrade,
    advise_book,
    book_greeks,
    book_value,
    realised_vol,
    rfq_fair,
    rfq_risk_impact,
)
from tests.parity.golden_io import load_golden

RTOL = 1e-9
ATOL = 1e-6
"""Float tolerance of the session comparison (see the module docstring)."""

KIND_LABELS = {"option": "Option", "structure": "Structure", "future": "Future"}
PRESET_BY_LABEL = {p.label: p.name for p in PRESETS}
PRESET_LABELS = {p.name: p.label for p in PRESETS}
JOINT_ICON = "⚖︎ "
"""The React UI prefixes the combined-hedge title with this glyph (the Streamlit page uses a
Material icon instead)."""


@cache
def _steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = load_golden("simsession")["steps"]
    return steps


# ------------------------------------------------------------------ the driver


class _Driver:
    """The Python page's state (session + widget values) driven like the React component."""

    def __init__(self) -> None:
        snap = load_snapshot()
        self.cfg = desk_config(snap)
        self.history_count = len(load_history().series)
        self.desk = SimSession(self.cfg, load_history().series)
        self.spread = 0.05
        self.lean = 0.0
        self.speed = 650.0
        self.replay_len = 120
        self.ticket: Ticket = default_ticket(self.cfg)
        self.advisor_open = False

    # -------------------------------------------------------------- derived

    def realised(self) -> float | None:
        return realised_vol([h.spot for h in self.desk.state.history], self.cfg.params.dt)

    def advice_plans(self) -> list[Any]:
        s = self.desk.state
        advice = advise_book(s.book, s.market, self.realised(), self.cfg.strike_step)
        return [a.plan for a in advice if a.plan is not None]

    # -------------------------------------------------------------- actions

    def apply(self, action: dict[str, Any], resolved: dict[str, Any] | None) -> tuple[bool, Any]:
        desk = self.desk
        s = desk.state
        kind = action["kind"]
        if kind == "tick":
            return (desk.tick() if not desk.at_end else False), None
        if kind == "auto":
            if desk.at_end:
                return False, None
            desk.set_playing(True)
            ran = 0
            for _ in range(action["ticks"]):
                if not desk.playing:
                    break
                desk.auto_tick()
                ran += 1
            desk.set_playing(False)
            return True, {"ran": ran}
        if kind == "request":
            return desk.request_rfq() is not None, None
        if kind == "select":
            if action["index"] >= len(s.queue):
                return False, None
            desk.select_rfq(s.queue[action["index"]].id)
            return True, None
        if kind in ("spread", "lean"):
            if s.selected is None:
                return False, None
            assert resolved is not None
            if kind == "spread":
                self.spread = resolved["value"]
            else:
                self.lean = resolved["value"]
            return True, {"value": resolved["value"]}
        if kind == "quote":
            return desk.quote(self.spread, self.lean) is not None, None
        if kind == "pass":
            if s.selected is None:
                return False, None
            desk.pass_rfq()
            return True, None
        if kind == "flattenDelta":
            desk.flatten_delta()
            return True, None
        if kind == "flattenVega":
            desk.flatten_vega()
            return True, None
        if kind == "flattenGamma":
            desk.flatten_gamma()
            return True, None
        if kind == "ticket":
            self._apply_ticket(action["tk"], resolved or {})
            return True, resolved
        if kind == "execute":
            desk.execute_ticket(self.ticket)
            return True, None
        if kind == "advisor":
            self.advisor_open = True
            return True, None
        if kind == "loadPlan":
            if not self.advisor_open:
                return False, None
            plans = self.advice_plans()
            self.advisor_open = False
            if action["index"] >= len(plans):
                return False, None
            self.ticket = ticket_from_plan(self.ticket, plans[action["index"]])
            return True, None
        if kind == "executeJoint":
            if not self.advisor_open:
                return False, None
            jh = desk.joint()
            if not show_joint(jh, book_greeks(s.book, s.market)):
                return False, None
            desk.execute_joint(jh)
            self.advisor_open = False
            return True, None
        if kind == "closeAdvisor":
            was = self.advisor_open
            self.advisor_open = False
            return was, None
        if kind == "reset":
            desk.reset(self.replay_len)
            return True, None
        if kind == "mode":
            desk.switch_mode(action["value"], self.replay_len)
            return True, None
        if kind == "replayLen":
            if desk.mode != "historical":
                return False, None
            assert resolved is not None
            self.replay_len = int(resolved["value"])
            return True, {"value": resolved["value"]}
        if kind == "speed":
            assert resolved is not None
            self.speed = float(resolved["value"])
            return True, {"value": resolved["value"]}
        raise AssertionError(f"unknown action {kind}")

    def _apply_ticket(self, tk: dict[str, Any], resolved: dict[str, Any]) -> None:
        t = self.ticket
        if "kind" in tk:
            t = replace(t, kind=tk["kind"])
        if "preset" in tk:
            t = replace(t, preset=PRESET_BY_LABEL[tk["preset"]])
        if "side" in tk:
            t = replace(t, side=tk["side"])
        if "type" in tk:
            t = replace(t, option_type=tk["type"])
        if "K" in resolved:
            t = replace(t, K=float(resolved["K"]))
        if "widthPct" in resolved:
            t = replace(t, width_pct=float(resolved["widthPct"]))
        if "days" in resolved:
            t = replace(t, days=float(resolved["days"]))
        if "size" in resolved:
            t = replace(t, size=float(resolved["size"]))
        self.ticket = t

    # -------------------------------------------------------------- observation

    def dom(self) -> dict[str, Any]:
        """What the page shows, in the golden's shape (see ``observeDom`` in the exporter)."""
        desk, cfg = self.desk, self.cfg
        s = desk.state
        greeks = book_greeks(s.book, s.market)
        pnl = book_value(s.book, s.market)
        rv = self.realised()
        historical = desk.mode == "historical"
        sel = s.selected
        quote_box: dict[str, Any] | None = None
        if sel is not None:
            fair = rfq_fair(sel, s.market)
            impact = rfq_risk_impact(sel, s.book, s.market)
            bid, ask = bid_ask_text(quote_preview(fair.net, fair.gross, self.spread, self.lean))
            quote_box = {
                "detail": rfq_detail(sel, fair.net),
                "impact": {"verdict": impact.verdict, "text": impact_text(impact)},
                "fields": [
                    ["Your spread", spread_text(self.spread)],
                    ["Lean (skew your price)", lean_text(self.lean)],
                ],
                "bid": bid,
                "ask": ask,
            }
        chips = []
        for r in s.queue:
            chip = rfq_chip(
                r, rfq_fair(r, s.market).net, rfq_risk_impact(r, s.book, s.market).verdict
            )
            chips.append(
                {
                    "active": r.id == s.selected_id,
                    "text": [chip.arrow, chip.text, chip.flag, chip.net],
                    "flagTitle": chip.hint,
                }
            )
        t = self.ticket
        active = [KIND_LABELS[t.kind]]
        inputs: list[list[str]]
        if t.kind == "option":
            active += [
                "Buy" if t.side == "long" else "Sell",
                "Call" if t.option_type == "call" else "Put",
            ]
            inputs = [
                ["Strike", js_number(t.K)],
                ["Exp (d)", js_number(t.days)],
                ["Size", js_number(t.size)],
            ]
        elif t.kind == "structure":
            active += [PRESET_LABELS[t.preset], "Buy" if t.side == "long" else "Sell"]
            inputs = [
                ["Wing %", str(js_round(t.width_pct * 100))],
                ["Exp (d)", js_number(t.days)],
                ["Size", js_number(t.size)],
            ]
        else:
            active += ["Buy" if t.side == "long" else "Sell"]
            inputs = [["Size", js_number(t.size)]]
        blotter = blotter_rows(s.book, s.market)
        advisor: dict[str, Any] | None = None
        if self.advisor_open:
            advice = advise_book(s.book, s.market, rv, cfg.strike_step)
            jh = desk.joint()
            advisor = {
                "subtitle": ADVISOR_SUBTITLE,
                "items": [
                    {
                        "severity": a.severity,
                        "title": a.title,
                        "detail": a.detail,
                        "plan": {"line": list(plan_line(a.plan)), "why": a.plan.rationale}
                        if a.plan is not None
                        else None,
                    }
                    for a in advice
                ],
                "joint": {
                    "head": [JOINT_ICON + JOINT_HEDGE_TITLE, JOINT_HEDGE_SUBTITLE],
                    "legs": [list(joint_leg_line(leg)) for leg in jh.legs],
                    "why": jh.rationale,
                }
                if show_joint(jh, greeks)
                else None,
            }
        return {
            "market": [
                [x.label, x.text, x.tone or ""]
                for x in market_stats(s, desk.mode, rv, desk.replay_max)
            ],
            "marketFields": ([["Replay length", days_text(self.replay_len)]] if historical else [])
            + [["Auto speed", speed_text(self.speed)]],
            "marketCaptions": [replay_caption(self.history_count), REPLAY_LENGTH_HINT]
            if historical
            else [],
            "episodeEnded": EPISODE_ENDED_MESSAGE if desk.at_end else None,
            "tickDisabled": desk.at_end,
            "autoDisabled": desk.at_end,
            "scorecard": [[x.label, x.text, x.tone or ""] for x in scorecard(s, greeks, pnl)],
            "rfqTag": f"{len(s.queue)} live",
            "emptyQueue": EMPTY_QUEUE_HINT if not s.queue else None,
            "chips": chips,
            "quoteBox": quote_box,
            "requestDisabled": len(s.queue) >= MAX_QUEUE,
            "fill": {"won": s.fill.won, "text": s.fill.msg} if s.fill is not None else None,
            "pnl": {
                "tag": pnl_tag(pnl),
                "main": fmt_signed_money(pnl),
                "mainTone": sign_class(pnl),
                "sub": [pnl_caption(cfg.currency), edge_costs_text(s.book)],
            },
            "book": [
                [x.label, x.text, x.tone or ""] for x in book_rows(greeks, s.book.underlying_qty)
            ],
            "positionsHead": positions_heading(s.book),
            "blotter": [[r.qty, r.instrument, r.note] for r in blotter],
            "blotterTones": [r.tone for r in blotter],
            "emptyBook": EMPTY_BOOK_HINT
            if not s.book.trades and s.book.underlying_qty == 0
            else None,
            "ticket": {
                "active": active,
                "inputs": inputs,
                "preview": list(ticket_preview_text(ticket_preview(t, s.market, cfg.strike_step))),
            },
            "advisor": advisor,
        }


# ------------------------------------------------------------------ comparison helpers


def _close(got: float | None, want: float | None, label: str) -> None:
    if want is None or got is None:
        assert got == want, label
        return
    assert math.isclose(got, want, rel_tol=RTOL, abs_tol=ATOL), f"{label}: {got!r} vs {want!r}"


def _rfq_row(r: RFQ) -> list[Any]:
    return [
        r.id,
        r.label,
        r.client_side,
        r.size,
        r.born_day,
        [[g.type, g.side, g.ratio, g.K, g.T] for g in r.legs],
    ]


def _assert_rfq(got: RFQ, want: Sequence[Any], label: str) -> None:
    g = _rfq_row(got)
    assert g[:5] == want[:5], label
    assert len(g[5]) == len(want[5]), label
    for gl, wl in zip(g[5], want[5], strict=True):
        assert gl[:2] == wl[:2], label
        for a, b, name in zip(gl[2:], wl[2:], ("ratio", "K", "T"), strict=True):
            _close(a, b, f"{label}.{name}")


def _assert_trade(got: BookTrade, want: Sequence[Any], label: str) -> None:
    assert [got.id, got.type, got.side] == list(want[:3]), label
    for a, b, name in zip(
        (got.quantity, got.K, got.expiry_time, got.traded_price),
        want[3:],
        ("quantity", "K", "expiry", "traded_price"),
        strict=True,
    ):
        _close(a, b, f"{label}.{name}")


def _assert_state(d: _Driver, want: dict[str, Any], label: str) -> None:
    s = d.desk.state
    assert [s.day, s.quotes, s.fills, s.selected_id] == [
        want["day"],
        want["quotes"],
        want["fills"],
        want["selectedId"],
    ], label
    m = s.market
    for a, b, name in zip(
        (m.t, m.spot, m.atm_vol, m.r, m.q, m.skew_slope, m.skew_curv),
        want["market"],
        ("t", "spot", "atmVol", "r", "q", "skewSlope", "skewCurv"),
        strict=True,
    ):
        _close(a, b, f"{label} market.{name}")
    assert len(s.queue) == len(want["queue"]), label
    for i, (r, w) in enumerate(zip(s.queue, want["queue"], strict=True)):
        _assert_rfq(r, w, f"{label} queue[{i}]")
    want_fill = want["fill"]
    got_fill = {"msg": s.fill.msg, "won": s.fill.won} if s.fill else None
    assert got_fill == want_fill, label
    for a, b, name in zip(
        s.cum_attr.as_dict().values(), want["cumAttr"], s.cum_attr.as_dict(), strict=True
    ):
        _close(a, b, f"{label} cumAttr.{name}")
    b = s.book
    for a, w, name in zip(
        (b.cash, b.underlying_qty, b.realized_edge, b.total_costs),
        want["book"][:4],
        ("cash", "underlying", "edge", "costs"),
        strict=True,
    ):
        _close(a, w, f"{label} book.{name}")
    assert [b.next_id, len(b.trades)] == want["book"][4:], label
    if want["trades"] is not None:
        assert len(b.trades) == len(want["trades"]), label
        for i, (t, w) in enumerate(zip(b.trades, want["trades"], strict=True)):
            _assert_trade(t, w, f"{label} trade[{i}]")
    if want["history"] is not None:
        assert len(s.history) == len(want["history"]), label
        for h, w in zip(s.history, want["history"], strict=True):
            assert h.day == w[0], label
            _close(h.spot, w[1], f"{label} history.spot")
            _close(h.vol, w[2], f"{label} history.vol")
            _close(h.pnl, w[3], f"{label} history.pnl")
    win = d.desk.window
    assert (win.start_index if win is not None else None) == want["replayStart"], label


def _assert_dom(got: dict[str, Any], want: dict[str, Any], label: str) -> None:
    for key, value in got.items():
        assert value == want[key], f"{label} dom.{key}:\n  python {value!r}\n  react  {want[key]!r}"
    assert "▶▶ Auto" == want["autoButton"], label  # Auto is always off between actions


# ------------------------------------------------------------------ tests


def test_golden_covers_the_whole_desk_loop() -> None:
    """The scripted session exercises every action, fills AND misses, a full queue, the
    advisor's plans and combined hedge, a replay window and its episode end."""
    steps = _steps()
    applied = {s["action"]["kind"] for s in steps if s["applied"]}
    assert applied >= {
        "tick", "auto", "request", "select", "spread", "lean", "quote", "pass",
        "flattenDelta", "flattenVega", "flattenGamma", "ticket", "execute", "advisor",
        "loadPlan", "executeJoint", "closeAdvisor", "reset", "mode", "replayLen", "speed",
    }  # fmt: skip
    fills = [s["dom"]["fill"] for s in steps if s["action"]["kind"] == "quote" and s["applied"]]
    assert any(f["won"] for f in fills)
    assert any(not f["won"] for f in fills)
    assert any(s["dom"]["requestDisabled"] for s in steps)
    assert any(s["dom"]["episodeEnded"] for s in steps)
    assert any(s["dom"]["advisor"] and s["dom"]["advisor"]["joint"] for s in steps)


def test_session_matches_react_step_by_step() -> None:
    """Replay the golden's actions: state and screen must match after every one."""
    d = _Driver()
    steps = _steps()
    _assert_state(d, steps[0]["state"], "init")
    _assert_dom(d.dom(), steps[0]["dom"], "init")
    for i, step in enumerate(steps[1:], start=1):
        action = step["action"]
        label = f"step {i} ({action['kind']})"
        applied, resolved = d.apply(action, step.get("resolved"))
        assert applied == step["applied"], f"{label}: applied {applied} vs {step['applied']}"
        if action["kind"] == "auto" and applied:
            assert resolved == step["resolved"], label
        _assert_state(d, step["state"], label)
        _assert_dom(d.dom(), step["dom"], label)


@pytest.mark.parametrize("index", [0])
def test_first_rfq_matches_the_reference_screenshot(index: int) -> None:
    """The first requested RFQ of a fresh session is the one in react_ref/4c_sim_rfq.png:
    the client buys 100 of the 6150 put, net 273.87."""
    d = _Driver()
    rfq = d.desk.request_rfq()
    assert rfq is not None
    assert rfq.id == index + 1
    chip = rfq_chip(rfq, rfq_fair(rfq, d.desk.state.market).net, "neutral")
    assert (chip.arrow, chip.text, chip.net) == ("▲", "100× Put", "273.87")
    assert rfq_detail(rfq, rfq_fair(rfq, d.desk.state.market).net) == (
        "CLIENT BUYS · +1 P6150 · net 273.87"
    )
