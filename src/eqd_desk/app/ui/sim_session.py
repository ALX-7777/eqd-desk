"""The trading simulator's session: the state machine of the React ``SimulatorView``.

Pure Python (no Streamlit): the page keeps one :class:`SimSession` in Session State and
calls its methods from widget callbacks; this module owns every rule of the desk loop and is
unit-tested on its own.

What it ports (``web/src/components/SimulatorView.tsx``)
-------------------------------------------------------
- ``initialState`` / ``initialMarket``: the seed market (or day 0 of a replay window), an
  empty book, no RFQs.
- ``advance`` (Tick / Auto): the market steps (GBM + leverage, or the next replay day), the
  held book's P&L over the step is explained and accumulated, stale RFQs expire, and on Auto a
  client may send a new one.
- RFQ flow: request a quote, select, quote a two-way with a spread and a lean (fill or miss
  against the client's noisy valuation), pass.
- Hedging: flatten delta (future), vega and gamma (a 60-day ATM call), the trade ticket
  (option / preset structure / future), the advisor's combined hedge.
- Reset and the Simulated / Replay switch, the replay window and the episode end.

Random numbers
--------------
Five seeded streams, the React component's refs, consumed in EXACTLY the React order so a
seeded session reproduces the React app action for action (checked against the real
component by ``tests/ui/test_sim_session_parity.py``):

============= ======================== ===========================================
stream        seed                     drawn by
============= ======================== ===========================================
market        ``0x9A17 + n·101``       each simulated step (two normals)
rfq           ``0x2BAD`` (never reset) every new RFQ (:func:`generate_rfq`)
noise         ``0x51DE + n·211``       each quote (the client's valuation, one normal)
arrival       ``0xA771 + n·307``       each Auto step with room in the queue
replay pick   ``0x7E1A`` (never reset) each reset into Replay (the window start)
============= ======================== ===========================================

``n`` is the number of resets so far (0 for the first session). RFQ ids restart at 1 on reset.

The React dev build double-invokes state updaters (``<StrictMode>``) and so consumes these
streams twice per action; this module follows the production build (one draw per action).

Example::

    from eqd_desk.app.ui.sim_session import SimSession, desk_config
    from eqd_desk.data import load_history, load_snapshot

    desk = SimSession(desk_config(load_snapshot()), load_history().series)
    desk.request_rfq()
    desk.quote(spread=0.05, lean=0.0)  # fill or miss
    desk.tick()
    desk.state.day, desk.state.fill
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Final, Literal

from eqd_desk.app.ui.format import fmt_money, js_round
from eqd_desk.content.simulator import FILL_MESSAGE_TEMPLATE, MISS_MESSAGE_TEMPLATE
from eqd_desk.data import MarketSnapshot
from eqd_desk.engine.bsm import price as vanilla_price
from eqd_desk.engine.presets import PresetName, PresetParams, build_preset, round_to
from eqd_desk.engine.rng import Mulberry32, NormalSampler
from eqd_desk.engine.sim import (
    DEFAULT_SIM_PARAMS,
    RFQ,
    Book,
    CostModel,
    HedgePlan,
    HistoryPoint,
    JointHedge,
    MarketState,
    OptionOrder,
    PnlAttribution,
    ReplayBase,
    ReplayWindow,
    SimParams,
    add_fill,
    attribute,
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
    pick_window,
    replay_state,
    rfq_fair,
    trade_option,
    trade_structure,
    vol_for_strike,
    window_steps,
)
from eqd_desk.engine.strategy import LegSide
from eqd_desk.engine.types import BsmInputs, OptionType

Mode = Literal["simulated", "historical"]
"""Market mode: a simulated GBM + leverage path, or a replay of real history."""

TicketKind = Literal["option", "structure", "future"]
"""What the trade ticket sends to the market."""

# ------------------------------------------------------------------ desk constants

NOISE_FRAC: Final = 0.08
"""Std-dev of the client's valuation noise, as a fraction of the package's gross premium."""

COSTS: Final = CostModel(underlying_half_spread=0.0001, option_half_spread=0.01)
"""What crossing the market costs: 1 bp of spot on the future, 1% of premium on an option."""

HEDGE_TENOR: Final = 60 / 365
"""Tenor (years) of the ATM call used by the flatten-vega / flatten-gamma buttons."""

DEFAULT_WINDOW_LEN: Final = 120
"""Default replay window, in trading days."""

MAX_QUEUE: Final = 4
"""Most client RFQs that can be live at once."""

EXPIRE_DAYS: Final = 4
"""An RFQ older than this many days is withdrawn by the client."""

RFQ_ARRIVAL_PROB: Final = 0.4
"""Chance a new client RFQ arrives on each Auto day (when the queue has room)."""

SEED_MARKET: Final = 0x9A17
SEED_RFQ: Final = 0x2BAD
SEED_NOISE: Final = 0x51DE
SEED_ARRIVAL: Final = 0xA771
SEED_REPLAY: Final = 0x7E1A
"""Seeds of the five random streams (see the module docstring)."""

RESEED_MARKET: Final = 101
RESEED_NOISE: Final = 211
RESEED_ARRIVAL: Final = 307
"""Per-reset seed strides: reset ``n`` seeds a stream with ``seed + n·stride``."""

DELTA_WARN: Final = 40.0
"""|Net delta| (index units) above which the scorecard flags directional risk."""

VEGA_WARN: Final = 1500.0
"""|Net vega| (per vol point) above which the scorecard flags vol risk."""

JOINT_MIN_VEGA: Final = 80.0
"""The combined hedge is only offered when |vega| (per vol point) exceeds this …"""

JOINT_MIN_GAMMA: Final = 1e-6
"""… and |raw gamma| exceeds this (both greeks meaningfully exposed)."""


# ------------------------------------------------------------------ configuration


@dataclass(frozen=True, slots=True)
class DeskConfig:
    """Everything the session takes from the seed snapshot (fixed for the app's life)."""

    initial_market: MarketState
    """Day 0 of a simulated session: the snapshot's spot, ATM vol, r, q and skew."""
    params: SimParams
    """The simulated process (default params with the long-run vol at the snapshot's ATM)."""
    replay_base: ReplayBase
    """What a replay takes from the snapshot (r, q, skew) and the step (one trading day)."""
    strike_step: float
    """Listed strike grid (25 points for an index above 2,000)."""
    currency: str
    """Premium currency (P&L unit)."""


def desk_config(snap: MarketSnapshot) -> DeskConfig:
    """The desk configuration of a snapshot (React: module constants of SimulatorView)."""
    params = replace(DEFAULT_SIM_PARAMS, base_vol=snap.atm_vol_30d)
    return DeskConfig(
        initial_market=MarketState(
            t=0.0,
            spot=snap.spot,
            atm_vol=snap.atm_vol_30d,
            r=snap.r,
            q=snap.q,
            skew_slope=snap.skew.slope,
            skew_curv=snap.skew.curv,
        ),
        params=params,
        replay_base=ReplayBase(
            r=snap.r, q=snap.q, skew_slope=snap.skew.slope, skew_curv=snap.skew.curv, dt=params.dt
        ),
        strike_step=25.0 if snap.spot >= 2000 else 5.0,
        currency=snap.currency,
    )


# ------------------------------------------------------------------ state


@dataclass(frozen=True, slots=True)
class CumAttribution:
    """The P&L explain accumulated over the session (premium currency)."""

    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    vanna: float = 0.0
    volga: float = 0.0
    residual: float = 0.0

    def plus(self, att: PnlAttribution) -> CumAttribution:
        """This explain plus one step's."""
        return CumAttribution(
            delta=self.delta + att.delta,
            gamma=self.gamma + att.gamma,
            theta=self.theta + att.theta,
            vega=self.vega + att.vega,
            vanna=self.vanna + att.vanna,
            volga=self.volga + att.volga,
            residual=self.residual + att.residual,
        )

    def as_dict(self) -> dict[str, float]:
        """``{"delta": …, …, "residual": …}`` in the chart's order."""
        return {
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "vanna": self.vanna,
            "volga": self.volga,
            "residual": self.residual,
        }

    @property
    def total(self) -> float:
        """Sum of every term (the P&L explained, residual included)."""
        return sum(self.as_dict().values())


@dataclass(frozen=True, slots=True)
class HistPoint:
    """One day of the session's path (the P&L and spot & vol charts)."""

    day: int
    spot: float
    vol: float
    """ATM implied vol (decimal)."""
    pnl: float
    """Mark-to-market P&L of the book held over the step, at the day's close."""


@dataclass(frozen=True, slots=True)
class FillNote:
    """The result line of the last quote."""

    msg: str
    won: bool


@dataclass(frozen=True, slots=True)
class SimState:
    """The desk at one instant (React ``SimState``). Frozen: every action returns a new one."""

    market: MarketState
    book: Book
    queue: tuple[RFQ, ...]
    """Live client RFQs, oldest first."""
    selected_id: int | None
    """The RFQ in the quote box."""
    fill: FillNote | None
    history: tuple[HistPoint, ...]
    cum_attr: CumAttribution
    day: int
    quotes: int
    """Quotes shown (fills + misses)."""
    fills: int

    @property
    def selected(self) -> RFQ | None:
        """The selected RFQ, if it is still live."""
        return next((r for r in self.queue if r.id == self.selected_id), None)


def initial_market(cfg: DeskConfig, mode: Mode, window: ReplayWindow | None) -> MarketState:
    """Day 0: the replay window's first day, or the snapshot market."""
    if mode == "historical" and window is not None:
        return replay_state(window, 0, cfg.replay_base)
    return cfg.initial_market


def initial_state(cfg: DeskConfig, mode: Mode, window: ReplayWindow | None) -> SimState:
    """A fresh session: day 0, empty book, no RFQs, a one-point history."""
    market = initial_market(cfg, mode, window)
    return SimState(
        market=market,
        book=empty_book(),
        queue=(),
        selected_id=None,
        fill=None,
        history=(HistPoint(day=0, spot=market.spot, vol=market.atm_vol, pnl=0.0),),
        cum_attr=CumAttribution(),
        day=0,
        quotes=0,
        fills=0,
    )


# ------------------------------------------------------------------ trade ticket


@dataclass(frozen=True, slots=True)
class Ticket:
    """The trade ticket's fields (React ``tk*`` / ``st*`` state)."""

    kind: TicketKind = "option"
    side: LegSide = "long"
    """``"long"`` = buy, ``"short"`` = sell (for a structure: buy / sell the preset)."""
    option_type: OptionType = "call"
    K: float = 0.0
    """Option strike (index points)."""
    days: float = 60
    """Option / structure tenor in calendar days."""
    size: float = 10
    """Contracts (option), structures, or future units."""
    preset: PresetName = "straddle"
    width_pct: float = 0.05
    """Structure wing width as a fraction of spot."""


def default_ticket(cfg: DeskConfig) -> Ticket:
    """The ticket as the page opens: buy 10 ATM 60-day calls."""
    return Ticket(K=round_to(cfg.initial_market.spot, cfg.strike_step))


def _flip(side: LegSide) -> LegSide:
    return "short" if side == "long" else "long"


def structure_orders(ticket: Ticket, market: MarketState, strike_step: float) -> list[OptionOrder]:
    """The ticket's preset structure as market orders: legs from the preset builder around
    spot (tenor ``days``, wings ``width_pct``), each leg quantity × ``size``; selling the
    structure flips every leg."""
    legs = build_preset(
        ticket.preset,
        PresetParams(
            S=market.spot,
            base_t=ticket.days / 365,
            width_pct=ticket.width_pct,
            strike_step=strike_step,
            vol_for=lambda _k, _t: 0.0,
        ),
    )
    return [
        OptionOrder(
            type=leg.type,
            side=leg.side if ticket.side == "long" else _flip(leg.side),
            quantity=leg.quantity * ticket.size,
            K=leg.K,
            T=leg.T,
        )
        for leg in legs
    ]


def order_fair(order: OptionOrder, market: MarketState) -> float:
    """Per-contract fair of an order on the current surface."""
    return vanilla_price(
        BsmInputs(
            S=market.spot,
            K=order.K,
            T=order.T,
            r=market.r,
            q=market.q,
            sigma=vol_for_strike(market, order.K, order.T),
        ),
        order.type,
    )


@dataclass(frozen=True, slots=True)
class TicketPreview:
    """What the ticket shows above "Execute @ market"."""

    label: Literal["price", "net", "spot"]
    """``price`` (option fair), ``net`` (structure net premium, debit +) or ``spot``."""
    value: float
    cost: float
    """Half-spread cost of executing (always ≥ 0)."""


def ticket_preview(ticket: Ticket, market: MarketState, strike_step: float) -> TicketPreview:
    """Fair value and execution cost of the ticket at the current market."""
    if ticket.kind == "structure":
        orders = structure_orders(ticket, market, strike_step)
        net = 0.0
        cost = 0.0
        for o in orders:
            fair = order_fair(o, market)
            net += (1 if o.side == "long" else -1) * fair * o.quantity
            cost += abs(fair) * o.quantity * COSTS.option_half_spread
        return TicketPreview("net", net, cost)
    if ticket.kind == "option":
        fair = order_fair(
            OptionOrder(
                type=ticket.option_type,
                side=ticket.side,
                quantity=ticket.size,
                K=ticket.K,
                T=ticket.days / 365,
            ),
            market,
        )
        return TicketPreview("price", fair, ticket.size * abs(fair) * COSTS.option_half_spread)
    return TicketPreview(
        "spot", market.spot, ticket.size * market.spot * COSTS.underlying_half_spread
    )


def plan_quantity(quantity: float) -> int:
    """An advisor quantity as a tradeable size: rounded, at least 1."""
    return max(1, js_round(quantity))


def ticket_from_plan(ticket: Ticket, plan: HedgePlan) -> Ticket:
    """Load an advisor hedge plan into the ticket (you review the size, then execute):
    the future for delta, else the option with its type, strike and tenor."""
    side: LegSide = "long" if plan.side == "buy" else "short"
    qty = plan_quantity(plan.quantity)
    if plan.instrument == "future":
        return replace(ticket, kind="future", side=side, size=qty)
    return replace(
        ticket,
        kind="option",
        option_type=plan.option_type or "call",
        side=side,
        K=plan.K if plan.K is not None else ticket.K,
        days=plan.tenor_days if plan.tenor_days is not None else ticket.days,
        size=qty,
    )


def joint_orders(jh: JointHedge, market: MarketState, strike_step: float) -> list[OptionOrder]:
    """The option legs of a combined hedge as orders (rounded sizes, at least 1)."""
    return [
        OptionOrder(
            type=leg.option_type or "call",
            side="long" if leg.side == "buy" else "short",
            quantity=plan_quantity(leg.quantity),
            K=leg.K if leg.K is not None else round_to(market.spot, strike_step),
            T=(leg.tenor_days if leg.tenor_days is not None else 30) / 365,
        )
        for leg in jh.legs
        if leg.instrument == "option"
    ]


# ------------------------------------------------------------------ quoting


@dataclass(frozen=True, slots=True)
class QuotePreview:
    """Your two-way on the selected RFQ (net package prices)."""

    mid: float
    bid: float
    ask: float


def quote_preview(net: float, gross: float, spread: float, lean: float) -> QuotePreview:
    """Bid / ask around ``net + lean·gross`` with a full width of ``spread·gross``."""
    mid = net + lean * gross
    half = (spread / 2) * gross
    return QuotePreview(mid=mid, bid=mid - half, ask=mid + half)


def js_number(x: float) -> str:
    """JavaScript ``String(x)`` for the sizes and strikes the messages print (an integral
    value prints without ``.0``)."""
    if math.isfinite(x) and x == math.floor(x) and abs(x) < 1e21:
        return str(int(x))
    return repr(x)


def fill_message(side: str, rfq: RFQ, price: float, edge: float) -> str:
    """``"Filled — you SELL 100× Put @ 273.87 · edge 684.66"``."""
    return FILL_MESSAGE_TEMPLATE.format(
        side=side.upper(),
        size=js_number(rfq.size),
        label=rfq.label,
        price=fmt_money(price),
        edge=fmt_money(edge),
    )


def miss_message(rfq: RFQ) -> str:
    """``"Missed Put — client traded elsewhere"``."""
    return MISS_MESSAGE_TEMPLATE.format(label=rfq.label)


# ------------------------------------------------------------------ the session


@dataclass(slots=True)
class SimSession:
    """One trader's desk: the current :class:`SimState` plus the React component's refs
    (the seeded streams, the RFQ id counter, the replay window, the reset count) and the
    Auto switch. Methods mutate the session in place; :attr:`state` is replaced, never
    mutated, so the previous state stays valid."""

    cfg: DeskConfig
    series: Sequence[HistoryPoint]
    """The replay history (real daily ^GSPC / ^VIX)."""
    mode: Mode = "simulated"
    playing: bool = False
    """Auto on (the market steps on a timer)."""
    reset_count: int = 0
    next_rfq_id: int = 1
    window: ReplayWindow | None = None
    state: SimState = field(init=False)
    market_normal: NormalSampler = field(init=False)
    rfq_uniform: Mulberry32 = field(init=False)
    noise_normal: NormalSampler = field(init=False)
    arrival: Mulberry32 = field(init=False)
    replay_pick: Mulberry32 = field(init=False)

    def __post_init__(self) -> None:
        self.market_normal = NormalSampler(Mulberry32(SEED_MARKET))
        self.rfq_uniform = Mulberry32(SEED_RFQ)
        self.noise_normal = NormalSampler(Mulberry32(SEED_NOISE))
        self.arrival = Mulberry32(SEED_ARRIVAL)
        self.replay_pick = Mulberry32(SEED_REPLAY)
        self.state = initial_state(self.cfg, self.mode, self.window)

    # -------------------------------------------------------------- episode

    @property
    def replay_max(self) -> int | None:
        """Last day of the replay window (``None``: a simulated market never ends)."""
        return window_steps(self.window) if self.window is not None else None

    @property
    def at_end(self) -> bool:
        """The replay episode has reached its last day (Tick and Auto are disabled)."""
        rmax = self.replay_max
        return self.mode == "historical" and rmax is not None and self.state.day >= rmax

    def _sync_pause(self) -> None:
        """Auto pauses by itself at the end of a replay episode."""
        if self.playing and self.at_end:
            self.playing = False

    # -------------------------------------------------------------- the clock

    def _next_market(self) -> MarketState:
        s = self.state
        if self.mode == "historical" and self.window is not None:
            return replay_state(self.window, s.day + 1, self.cfg.replay_base)
        return gbm_leverage_process.step(s.market, self.cfg.params, self.market_normal).state

    def advance(self, spawn: bool) -> bool:
        """Step the market one day (React ``advance``); ``spawn``: a client may send a new RFQ
        (Auto). Returns False (and changes nothing) at the end of a replay episode.

        Order of events: the market moves; the book held over the step is explained
        (:func:`~eqd_desk.engine.sim.attribute`) and marked; RFQs older than
        :data:`EXPIRE_DAYS` are withdrawn; with ``spawn`` and room in the queue, one arrival
        draw decides whether a new RFQ comes in; the selection falls back to the oldest RFQ.
        """
        s = self.state
        rmax = self.replay_max
        if self.mode == "historical" and rmax is not None and s.day >= rmax:
            return False
        nxt = self._next_market()
        att = attribute(s.book, s.market, nxt)
        day = s.day + 1
        pnl = book_value(s.book, nxt)
        queue = [r for r in s.queue if day - r.born_day <= EXPIRE_DAYS]
        if spawn and len(queue) < MAX_QUEUE and self.arrival() < RFQ_ARRIVAL_PROB:
            queue.append(
                generate_rfq(nxt.spot, self.cfg.strike_step, self.rfq_uniform, self._new_id(), day)
            )
        selected = s.selected_id
        if selected is not None and not any(r.id == selected for r in queue):
            selected = None
        if selected is None and queue:
            selected = queue[0].id
        self.state = replace(
            s,
            market=nxt,
            cum_attr=s.cum_attr.plus(att),
            day=day,
            queue=tuple(queue),
            selected_id=selected,
            history=(*s.history, HistPoint(day=day, spot=nxt.spot, vol=nxt.atm_vol, pnl=pnl)),
        )
        self._sync_pause()
        return True

    def tick(self) -> bool:
        """The Tick button: one day, no new client flow."""
        return self.advance(spawn=False)

    def auto_tick(self) -> bool:
        """One Auto step: a day with client arrivals; pauses Auto at the end of an episode.
        A no-op when Auto is off."""
        if not self.playing:
            return False
        moved = self.advance(spawn=True)
        self._sync_pause()
        return moved

    def set_playing(self, on: bool) -> None:
        """Switch Auto on or off (it cannot start at the end of an episode)."""
        self.playing = on and not self.at_end

    def _new_id(self) -> int:
        rid = self.next_rfq_id
        self.next_rfq_id += 1
        return rid

    # -------------------------------------------------------------- client flow

    def request_rfq(self) -> RFQ | None:
        """ "Request a quote": a new client RFQ at the current spot (``None`` when the queue is
        full). It is selected if nothing is; the last fill message is cleared."""
        s = self.state
        if len(s.queue) >= MAX_QUEUE:
            return None
        rfq = generate_rfq(
            s.market.spot, self.cfg.strike_step, self.rfq_uniform, self._new_id(), s.day
        )
        self.state = replace(
            s,
            queue=(*s.queue, rfq),
            selected_id=s.selected_id if s.selected_id is not None else rfq.id,
            fill=None,
        )
        return rfq

    def select_rfq(self, rfq_id: int) -> None:
        """Put an RFQ in the quote box."""
        self.state = replace(self.state, selected_id=rfq_id)

    def quote(self, spread: float, lean: float) -> bool | None:
        """Show your two-way on the selected RFQ (full width ``spread``·gross, mid shifted by
        ``lean``·gross). The client trades if your price beats their noisy valuation: the fill
        goes in the book at the traded price (edge vs fair captured). Either way the RFQ leaves
        the queue and the quote counts. Returns whether it filled (``None``: nothing selected).
        """
        s = self.state
        rfq = s.selected
        if rfq is None:
            return None
        fair = rfq_fair(rfq, s.market)
        fill = evaluate_quote(
            rfq, fair.net, fair.gross, spread, NOISE_FRAC, self.noise_normal(), lean
        )
        queue = tuple(r for r in s.queue if r.id != rfq.id)
        selected = queue[0].id if queue else None
        if fill.filled and fill.you_side is not None:
            self.state = replace(
                s,
                book=add_fill(s.book, fill, rfq, s.market),
                queue=queue,
                selected_id=selected,
                quotes=s.quotes + 1,
                fills=s.fills + 1,
                fill=FillNote(fill_message(fill.you_side, rfq, fill.price, fill.edge), won=True),
            )
            return True
        self.state = replace(
            s,
            queue=queue,
            selected_id=selected,
            quotes=s.quotes + 1,
            fill=FillNote(miss_message(rfq), won=False),
        )
        return False

    def pass_rfq(self) -> None:
        """Pass on the selected RFQ (no quote, no stats); the next one is selected."""
        s = self.state
        queue = tuple(r for r in s.queue if r.id != s.selected_id)
        self.state = replace(s, queue=queue, selected_id=queue[0].id if queue else None, fill=None)

    # -------------------------------------------------------------- hedging

    def _set_book(self, book: Book) -> None:
        self.state = replace(self.state, book=book)

    def flatten_delta(self) -> None:
        """Trade the future to make net delta zero (crosses 1 bp)."""
        self._set_book(hedge_to_flat(self.state.book, self.state.market, COSTS))

    def flatten_vega(self) -> None:
        """Trade a 60-day ATM call to make net vega zero (crosses 1% of premium)."""
        s = self.state
        self._set_book(flatten_vega(s.book, s.market, HEDGE_TENOR, COSTS))

    def flatten_gamma(self) -> None:
        """Trade a 60-day ATM call to make net gamma zero (crosses 1% of premium)."""
        s = self.state
        self._set_book(flatten_gamma(s.book, s.market, HEDGE_TENOR, COSTS))

    def execute_ticket(self, ticket: Ticket) -> None:
        """ "Execute @ market": the future, the preset structure or the single option."""
        s = self.state
        if ticket.kind == "future":
            dq = ticket.size if ticket.side == "long" else -ticket.size
            self._set_book(hedge_trade(s.book, dq, s.market, COSTS))
        elif ticket.kind == "structure":
            orders = structure_orders(ticket, s.market, self.cfg.strike_step)
            self._set_book(trade_structure(s.book, orders, s.market, COSTS))
        else:
            order = OptionOrder(
                type=ticket.option_type,
                side=ticket.side,
                quantity=ticket.size,
                K=ticket.K,
                T=ticket.days / 365,
            )
            self._set_book(trade_option(s.book, order, s.market, COSTS))

    def joint(self) -> JointHedge:
        """The advisor's combined hedge for the current book."""
        s = self.state
        return joint_hedge(s.book, s.market, self.cfg.strike_step)

    def execute_joint(self, jh: JointHedge | None = None) -> None:
        """Execute the combined hedge: the two option legs first, then the future flattens
        whatever delta is left (so it goes LAST and adds nothing else)."""
        s = self.state
        plan = jh if jh is not None else self.joint()
        orders = joint_orders(plan, s.market, self.cfg.strike_step)
        book = trade_structure(s.book, orders, s.market, COSTS)
        self._set_book(hedge_to_flat(book, s.market, COSTS))

    # -------------------------------------------------------------- session

    def reset(self, replay_len: int = DEFAULT_WINDOW_LEN, mode: Mode | None = None) -> None:
        """A fresh session (Reset, or a mode switch): new market / noise / arrival seeds, RFQ
        ids from 1, Auto off, and in Replay a new window of ``replay_len`` days."""
        m = self.mode if mode is None else mode
        self.reset_count += 1
        n = self.reset_count
        self.market_normal = NormalSampler(Mulberry32(SEED_MARKET + n * RESEED_MARKET))
        self.noise_normal = NormalSampler(Mulberry32(SEED_NOISE + n * RESEED_NOISE))
        self.arrival = Mulberry32(SEED_ARRIVAL + n * RESEED_ARRIVAL)
        self.next_rfq_id = 1
        self.playing = False
        self.window = (
            pick_window(self.series, replay_len, self.replay_pick()) if m == "historical" else None
        )
        self.state = initial_state(self.cfg, m, self.window)

    def switch_mode(self, mode: Mode, replay_len: int = DEFAULT_WINDOW_LEN) -> None:
        """Simulated ↔ Replay (always starts a fresh session)."""
        self.mode = mode
        self.reset(replay_len, mode)


__all__ = [
    "COSTS",
    "DEFAULT_WINDOW_LEN",
    "DELTA_WARN",
    "EXPIRE_DAYS",
    "HEDGE_TENOR",
    "JOINT_MIN_GAMMA",
    "JOINT_MIN_VEGA",
    "MAX_QUEUE",
    "NOISE_FRAC",
    "RFQ_ARRIVAL_PROB",
    "VEGA_WARN",
    "CumAttribution",
    "DeskConfig",
    "FillNote",
    "HistPoint",
    "Mode",
    "QuotePreview",
    "SimSession",
    "SimState",
    "Ticket",
    "TicketKind",
    "TicketPreview",
    "default_ticket",
    "desk_config",
    "fill_message",
    "initial_market",
    "initial_state",
    "joint_orders",
    "js_number",
    "miss_message",
    "order_fair",
    "plan_quantity",
    "quote_preview",
    "structure_orders",
    "ticket_from_plan",
    "ticket_preview",
]
