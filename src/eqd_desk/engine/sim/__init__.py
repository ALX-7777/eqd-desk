"""Public surface for the Phase 4 trading simulator.

The market-making loop, one module per step::

    market   simulated spot + ATM-vol path (GBM + leverage), the skew surface, realised vol
    rfq      client requests (single vanillas and preset structures)
    quote    your two-way price and whether the client trades on it
    book     positions, hedges, cash; mark-to-market value and net greeks
    pnl      per-step P&L explain (second-order Taylor + residual)
    replay   step along a real historical spot/VIX window instead of simulating
    advisor  ranked hedging advice with concrete hedge plans

Example::

    from eqd_desk.engine.rng import Mulberry32, NormalSampler
    from eqd_desk.engine.sim import (
        DEFAULT_SIM_PARAMS,
        MarketState,
        add_fill,
        attribute,
        empty_book,
        evaluate_quote,
        gbm_leverage_process,
        generate_rfq,
        rfq_fair,
    )

    m = MarketState(t=0, spot=6312.45, atm_vol=0.146, r=0.043, q=0.013, skew_slope=-0.48)
    rfq = generate_rfq(m.spot, 25, Mulberry32(0x2BAD), id=1)
    fair = rfq_fair(rfq, m)
    fill = evaluate_quote(rfq, fair.net, fair.gross, 0.05, 0.08, z=0.7)
    book = add_fill(empty_book(), fill, rfq, m)
    after = gbm_leverage_process.step(m, DEFAULT_SIM_PARAMS, NormalSampler(Mulberry32(1))).state
    attribute(book, m, after)  # delta/gamma/theta/vega/vanna/volga + residual
"""

from __future__ import annotations

from eqd_desk.engine.sim.advisor import (
    Advice,
    AdviceAction,
    HedgePlan,
    Instrument,
    JointHedge,
    JointLeg,
    RiskImpact,
    RiskVerdict,
    Severity,
    TradeSide,
    advise_book,
    joint_hedge,
    rfq_risk_impact,
)
from eqd_desk.engine.sim.book import (
    MIN_REMAINING_T,
    ZERO_COSTS,
    Book,
    BookGreeks,
    BookTrade,
    CostModel,
    OptionOrder,
    RfqFair,
    add_fill,
    book_greeks,
    book_greeks_raw,
    book_value,
    empty_book,
    flatten_gamma,
    flatten_vega,
    hedge_to_flat,
    hedge_trade,
    marked_legs,
    rfq_fair,
    trade_option,
    trade_structure,
)
from eqd_desk.engine.sim.market import (
    DEFAULT_SIM_PARAMS,
    VOL_CAP,
    VOL_FLOOR,
    GbmLeverageProcess,
    MarketProcess,
    MarketSimulator,
    MarketState,
    NormalFn,
    SimParams,
    StepResult,
    gbm_leverage_process,
    realised_vol,
    vol_for_strike,
)
from eqd_desk.engine.sim.pnl import PnlAttribution, attribute
from eqd_desk.engine.sim.quote import FillResult, YourSide, evaluate_quote
from eqd_desk.engine.sim.replay import (
    REPLAY_VOL_FLOOR,
    HistoryPoint,
    ReplayBase,
    ReplayWindow,
    pick_window,
    replay_state,
    window_steps,
)
from eqd_desk.engine.sim.rfq import (
    RFQ,
    ClientSide,
    RfqLeg,
    StructKind,
    UniformFn,
    generate_rfq,
    single_option_rfq,
)

__all__ = [
    "DEFAULT_SIM_PARAMS",
    "MIN_REMAINING_T",
    "REPLAY_VOL_FLOOR",
    "RFQ",
    "VOL_CAP",
    "VOL_FLOOR",
    "ZERO_COSTS",
    "Advice",
    "AdviceAction",
    "Book",
    "BookGreeks",
    "BookTrade",
    "ClientSide",
    "CostModel",
    "FillResult",
    "GbmLeverageProcess",
    "HedgePlan",
    "HistoryPoint",
    "Instrument",
    "JointHedge",
    "JointLeg",
    "MarketProcess",
    "MarketSimulator",
    "MarketState",
    "NormalFn",
    "OptionOrder",
    "PnlAttribution",
    "ReplayBase",
    "ReplayWindow",
    "RfqFair",
    "RfqLeg",
    "RiskImpact",
    "RiskVerdict",
    "Severity",
    "SimParams",
    "StepResult",
    "StructKind",
    "TradeSide",
    "UniformFn",
    "YourSide",
    "add_fill",
    "advise_book",
    "attribute",
    "book_greeks",
    "book_greeks_raw",
    "book_value",
    "empty_book",
    "evaluate_quote",
    "flatten_gamma",
    "flatten_vega",
    "gbm_leverage_process",
    "generate_rfq",
    "hedge_to_flat",
    "hedge_trade",
    "joint_hedge",
    "marked_legs",
    "pick_window",
    "realised_vol",
    "replay_state",
    "rfq_fair",
    "rfq_risk_impact",
    "single_option_rfq",
    "trade_option",
    "trade_structure",
    "vol_for_strike",
    "window_steps",
]
