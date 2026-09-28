/**
 * Golden values for the Phase 4 trading simulator (web/src/engine/sim): the skew surface,
 * single market steps with fixed normals, seeded MarketSimulator paths + realised vol,
 * seeded RFQ streams (+ their net/gross fair), the quote/fill grid, P&L attribution over
 * hand-picked moves (incl. gaps and an expiry crossing), historical-replay windows over a
 * synthetic series, the desk advisor (every branch, full text + hedge plans, joint hedge,
 * RFQ risk impact) on crafted books, and — the main event — whole SEEDED DESK SESSIONS.
 *
 * A session is a scripted trader running the SimulatorView loop: each day the market
 * steps (GBM + leverage, or a replay window), the held book's P&L is explained, stale RFQs
 * expire, clients may send new ones (seeded arrival), the trader quotes the head of the
 * queue (leaning on the advisor's risk-impact verdict) or passes, and runs a fixed hedging
 * schedule (delta to flat, vega/gamma flattening, the joint hedge, preset structures, the
 * advisor's plan). The Python parity test (tests/parity/test_sim_parity.py) replays the
 * SAME script, consuming every random stream in the same order, and must reproduce paths,
 * RFQs, fills, book state, greeks, P&L explain and advice.
 *
 * Kept compact: per-day records are positional arrays (column names in `rowColumns` /
 * `quoteColumns`), and the heavy snapshots (greeks, advice, joint hedge) are taken every
 * SNAP_EVERY days and on the last day.
 */
import {
  DEFAULT_SIM_PARAMS,
  MarketSimulator,
  ZERO_COSTS,
  addFill,
  adviseBook,
  attribute,
  bookGreeks,
  bookValue,
  emptyBook,
  evaluateQuote,
  flattenGamma,
  flattenVega,
  gbmLeverageProcess,
  generateRFQ,
  hedgeToFlat,
  hedgeTrade,
  jointHedge,
  markedLegs,
  pickWindow,
  realisedVol,
  replayState,
  rfqFair,
  rfqRiskImpact,
  singleOptionRfq,
  tradeOption,
  tradeStructure,
  volForStrike,
  windowSteps,
  type Book,
  type BookTrade,
  type CostModel,
  type HistoryPoint,
  type MarketState,
  type OptionOrder,
  type RFQ,
  type ReplayBase,
  type ReplayWindow,
  type SimParams,
} from '../../src/engine/sim'
import { buildPreset, type PresetName } from '../../src/engine/presets'
import { makeNormal, mulberry32 } from '../../src/engine/exotics/mc'
import type { OptionType } from '../../src/engine/types'
import { writeGolden } from './writeGolden'

// ---------------------------------------------------------------------------- helpers

/** Non-finite numbers as strings (JSON has none); Python's float() parses them back. */
function enc(x: unknown): unknown {
  if (typeof x === 'number') return Number.isFinite(x) ? x : String(x)
  if (Array.isArray(x)) return x.map(enc)
  if (x !== null && typeof x === 'object') {
    return Object.fromEntries(Object.entries(x).map(([k, v]) => [k, enc(v)]))
  }
  return x
}

/** Compact RFQ: [id, label, clientSide, size, bornDay, [[type, side, ratio, K, T], ...]]. */
const rfqOut = (r: RFQ) => [r.id, r.label, r.clientSide, r.size, r.bornDay, r.legs.map((l) => [l.type, l.side, l.ratio, l.K, l.T])]

/** Compact trade: [id, type, side, quantity, K, expiryTime, tradedPrice]. */
const tradeOut = (t: BookTrade) => [t.id, t.type, t.side, t.quantity, t.K, t.expiryTime, t.tradedPrice]

const bookOut = (b: Book) => ({
  trades: b.trades.map(tradeOut),
  underlyingQty: b.underlyingQty,
  cash: b.cash,
  realizedEdge: b.realizedEdge,
  totalCosts: b.totalCosts,
  nextId: b.nextId,
})

/**
 * Synthetic "history": a multiplicative random walk for spot with a leverage-linked VIX,
 * driven by mulberry32 and PURE IEEE arithmetic (no libm), so the Python test regenerates
 * it bit for bit.
 */
function syntheticSeries(seed: number, n: number): HistoryPoint[] {
  const u = mulberry32(seed)
  let spot = 4200
  let vix = 17
  const out: HistoryPoint[] = []
  for (let k = 0; k < n; k++) {
    out.push({ date: `d${k}`, spot, vix })
    const a = u()
    const b = u()
    spot = spot * (1 + 0.03 * (a - 0.5))
    vix = Math.min(80, Math.max(9, vix + 4 * (b - 0.5) - 40 * 0.03 * (a - 0.5)))
  }
  return out
}

const M0: MarketState = { t: 0, spot: 100, atmVol: 0.2, r: 0.03, q: 0.01 }
const SKEW: MarketState = { t: 0, spot: 100, atmVol: 0.2, r: 0.03, q: 0.01, skewSlope: -0.5, skewCurv: 0.4 }
const SPX: MarketState = { t: 0, spot: 6312.45, atmVol: 0.146, r: 0.043, q: 0.013, skewSlope: -0.48, skewCurv: 0.62 }
const UI_COSTS: CostModel = { underlyingHalfSpread: 0.0001, optionHalfSpread: 0.01 }

// ---------------------------------------------------------------------------- grids

function volGrid() {
  const markets: MarketState[] = [
    M0,
    SKEW,
    SPX,
    { ...SKEW, skewSlope: -20 }, // steep: hits the floor and the cap
    { ...M0, skewSlope: 0, skewCurv: 0.8 }, // smile only
    { ...M0, atmVol: 2.0 }, // flat, clamped at the cap
    { ...SPX, atmVol: 0.01, r: -0.005, q: 0.03 }, // flat level under the floor, negative carry
  ]
  const moneyness = [0.5, 0.8, 0.9, 0.97, 1, 1.03, 1.1, 1.3, 2]
  const Ts = [0, 1e-7, 1 / 52, 0.25, 1, 3]
  return markets.map((m) => {
    const Ks = moneyness.map((x) => x * m.spot)
    return { market: m, Ks, Ts, vols: Ks.map((K) => Ts.map((T) => volForStrike(m, K, T))) }
  })
}

function stepCases() {
  const zs: [number, number][] = [[0, 0], [2, 0], [-2, 0], [0.7, -1.3], [0, -50], [0, 50], [-6, 3]]
  const states: MarketState[] = [M0, SKEW, { ...SPX, atmVol: 0.9, t: 0.37 }]
  const params: SimParams[] = [
    DEFAULT_SIM_PARAMS,
    { drift: 0.1, leverage: 2, volMeanRev: 5, baseVol: 0.25, volOfVol: 1.1, dt: 1 / 52 },
  ]
  // results: [stateIdx, paramsIdx, zIdx, t, spot, atmVol, r, q, skewSlope, skewCurv, dS, dVol, spotReturn]
  // (an absent skew field is written as null)
  const results: unknown[] = []
  states.forEach((state, si) =>
    params.forEach((p, pi) =>
      zs.forEach(([z1, z2], zi) => {
        let i = 0
        const normal = () => (i++ === 0 ? z1 : z2)
        const res = gbmLeverageProcess.step(state, p, normal)
        const s = res.state
        results.push([si, pi, zi, s.t, s.spot, s.atmVol, s.r, s.q, s.skewSlope, s.skewCurv, res.dS, res.dVol, res.spotReturn])
      }),
    ),
  )
  return { states, params, zs, results }
}

function simPaths() {
  const pathOut = (sim: MarketSimulator, n: number) => {
    const rows: number[][] = []
    const spots = [sim.state.spot]
    for (let k = 0; k < n; k++) {
      const res = sim.next()
      spots.push(res.state.spot)
      rows.push([res.state.t, res.state.spot, res.state.atmVol, res.dS, res.dVol, res.spotReturn])
    }
    return { rows, finalState: sim.state, realisedVol: realisedVol(spots, 1 / 252) }
  }
  const custom: SimParams = { drift: -0.2, leverage: 1.4, volMeanRev: 1.5, baseVol: 0.3, volOfVol: 1.5, dt: 1 / 365 }
  return [
    { label: 'defaults (seed 0x5eed)', initial: M0, params: null, seed: null, ...pathOut(new MarketSimulator(M0), 30) },
    { label: 'seed 123', initial: SKEW, params: DEFAULT_SIM_PARAMS, seed: 123, ...pathOut(new MarketSimulator(SKEW, DEFAULT_SIM_PARAMS, 123), 30) },
    { label: 'custom params', initial: SPX, params: custom, seed: 0x9a17, ...pathOut(new MarketSimulator(SPX, custom, 0x9a17), 40) },
  ]
}

function realisedVolCases() {
  const paths = [
    [100],
    [100, 101],
    [100, 102, 99, 103, 98, 104, 97],
    Array.from({ length: 20 }, (_, k) => 100 * Math.exp(0.001 * k)),
    [6312.45, 6290.1, 6333.8, 6301.25, 6150, 6199.99, 6250.5, 6248],
  ]
  return paths.flatMap((spots) => [1 / 252, 1 / 52].map((dt) => ({ spots, dt, vol: realisedVol(spots, dt) })))
}

function rfqStreams() {
  const specs = [
    { seed: 99, spot: 100, strikeStep: 5, n: 50, day: 0 },
    { seed: 0x2bad, spot: 6312.45, strikeStep: 25, n: 50, day: 3 },
    { seed: 5, spot: 1, strikeStep: 5, n: 15, day: 7 }, // tiny spot: strikes floored at one step
  ]
  return specs.map((s) => {
    const rng = mulberry32(s.seed)
    const rfqs = Array.from({ length: s.n }, (_, k) => generateRFQ(s.spot, s.strikeStep, rng, k + 1, s.day))
    const m: MarketState = s.spot > 1000 ? SPX : { ...SKEW, spot: s.spot }
    return {
      ...s,
      market: m,
      rfqs: rfqs.map(rfqOut),
      // The tiny-spot stream builds structures with non-positive strikes (atm rounds to 0),
      // which the pricer rightly rejects: its fair is not exported.
      fair: s.spot > 1
        ? rfqs.map((r) => {
            const f = rfqFair(r, m)
            return [f.net, f.gross]
          })
        : null,
    }
  })
}

function quoteGrid() {
  const rfqs = [singleOptionRfq('call', 100, 0.25, 10, 'buy', 1), singleOptionRfq('put', 95, 0.5, 25, 'sell', 2, 4)]
  const fairs: [number, number][] = [[10, 10], [-0.4, 7.9], [0, 5]]
  const out: unknown[] = []
  for (const rfq of rfqs)
    for (const [net, gross] of fairs)
      for (const spread of [0.04, 0.1])
        for (const z of [-1.5, -0.2, 0.2, 1.5])
          for (const lean of [-0.03, 0, 0.03]) {
            const f = evaluateQuote(rfq, net, gross, spread, 0.1, z, lean)
            out.push([rfq.id, net, gross, spread, z, lean, f.filled, f.youSide, f.price, f.edge, f.bid, f.ask, f.fairValue])
          }
  // the default lean (omitted argument)
  const d = evaluateQuote(rfqs[0], 10, 10, 0.04, 0.1, 0.5)
  out.push([1, 10, 10, 0.04, 0.5, null, d.filled, d.youSide, d.price, d.edge, d.bid, d.ask, d.fairValue])
  return { rfqs: rfqs.map(rfqOut), cases: out }
}

const LONG_CALL: Book = {
  trades: [{ id: 1, type: 'call', side: 'long', quantity: 10, K: 100, expiryTime: 0.5, tradedPrice: 5 }],
  underlyingQty: 0,
  cash: -50,
  realizedEdge: 0,
  totalCosts: 0,
  nextId: 2,
}
const SKEW_BOOK: Book = {
  trades: [
    { id: 1, type: 'put', side: 'short', quantity: 20, K: 90, expiryTime: 0.5, tradedPrice: 2 },
    { id: 2, type: 'call', side: 'long', quantity: 10, K: 110, expiryTime: 0.4, tradedPrice: 1.5 },
  ],
  underlyingQty: 5,
  cash: 0,
  realizedEdge: 0,
  totalCosts: 0,
  nextId: 3,
}

function attributionCases() {
  const cases: { book: Book; before: MarketState; after: MarketState }[] = [
    { book: LONG_CALL, before: M0, after: { t: 1 / 252, spot: 101.5, atmVol: 0.205, r: 0.03, q: 0.01 } },
    { book: LONG_CALL, before: M0, after: { ...M0, spot: 100.5 } },
    { book: LONG_CALL, before: M0, after: { ...M0, atmVol: 0.21 } },
    { book: hedgeToFlat(LONG_CALL, M0), before: M0, after: { ...M0, spot: 103 } },
    { book: SKEW_BOOK, before: SKEW, after: { ...SKEW, t: 1 / 252, spot: 99, atmVol: 0.21 } },
    { book: SKEW_BOOK, before: SKEW, after: { ...SKEW, t: 2 / 252, spot: 98.7, atmVol: 0.215 } },
    { book: SKEW_BOOK, before: SKEW, after: { ...SKEW, t: 5 / 252, spot: 88, atmVol: 0.31 } }, // crash gap
    { book: SKEW_BOOK, before: { ...SKEW, t: 0.39 }, after: { ...SKEW, t: 0.45, spot: 112, atmVol: 0.17 } }, // call expires
    { book: SKEW_BOOK, before: SKEW, after: SKEW }, // no move
    { book: { ...emptyBook(), underlyingQty: -3, cash: 300 }, before: M0, after: { ...M0, spot: 101, t: 1 / 252, atmVol: 0.25 } },
  ]
  return cases.map(({ book, before, after }) => ({ book: bookOut(book), before, after, att: attribute(book, before, after) }))
}

function replayGoldens() {
  const series = syntheticSeries(0x7e1a, 250)
  const base: ReplayBase = { r: 0.043, q: 0.013, skewSlope: -0.48, skewCurv: 0.62, dt: 1 / 252 }
  const specs: [number, number][] = [[60, 0.5], [60, 0], [60, 0.999999], [300, 0.3], [1, 0.7], [0, 0.2], [120, 0.123]]
  const windows = specs.map(([length, u]) => {
    const win = pickWindow(series, length, u)
    const n = win.points.length
    const idx = [-3, 0, 1, 5, n - 1, n, 999]
    return {
      length,
      u,
      startIndex: win.startIndex,
      nPoints: n,
      steps: windowSteps(win),
      states: idx.map((i) => ({ i, state: replayState(win, i, base) })),
    }
  })
  return { seed: 0x7e1a, n: 250, base, first: series.slice(0, 3), last: series[series.length - 1], windows }
}

// ---------------------------------------------------------------------------- advisor

function short(type: OptionType, quantity: number, expiryTime: number, id = 1, K = 100): BookTrade {
  return { id, type, side: 'short', quantity, K, expiryTime, tradedPrice: 0 }
}
function long(type: OptionType, quantity: number, expiryTime: number, id = 1, K = 100): BookTrade {
  return { id, type, side: 'long', quantity, K, expiryTime, tradedPrice: 0 }
}
const withTrades = (trades: BookTrade[], underlyingQty = 0, extra: Partial<Book> = {}): Book => ({
  ...emptyBook(),
  trades,
  underlyingQty,
  ...extra,
})

function advisorCases() {
  const lowVol = { ...M0, atmVol: 0.1 }
  const cases: { label: string; book: Book; market: MarketState; rv: number | null; step?: number }[] = [
    { label: 'empty', book: emptyBook(), market: M0, rv: 0.2 },
    { label: 'long delta 300', book: withTrades([], 300), market: M0, rv: 0.2, step: 5 },
    { label: 'short delta 200', book: withTrades([], -200), market: M0, rv: null },
    { label: 'long delta 1500', book: withTrades([], 1500), market: M0, rv: null },
    { label: 'small delta 100', book: withTrades([], 100), market: M0, rv: null },
    { label: 'short vega low vol', book: withTrades([short('call', 500, 0.5)]), market: lowVol, rv: 0.08, step: 5 },
    { label: 'short vega normal vol', book: withTrades([short('call', 500, 0.5)]), market: M0, rv: 0.08 },
    { label: 'short gamma hot', book: withTrades([short('call', 200, 0.25)]), market: M0, rv: 0.35 },
    { label: 'short gamma quiet', book: withTrades([short('call', 200, 0.25)]), market: M0, rv: 0.1 },
    { label: 'long gamma quiet', book: withTrades([long('call', 200, 0.25)]), market: M0, rv: 0.1 },
    { label: 'long gamma hot', book: withTrades([long('call', 200, 0.25)]), market: M0, rv: 0.5 },
    { label: 'short gamma no rv', book: withTrades([short('call', 200, 0.25)]), market: M0, rv: null },
    { label: 'short straddle + delta', book: withTrades([short('call', 100, 0.5, 1), short('put', 80, 0.5, 2)], 40), market: M0, rv: 0.25, step: 5 },
    { label: 'long 3000 calls (pay theta)', book: withTrades([long('call', 3000, 0.25)]), market: M0, rv: 0.2 },
    { label: 'short 3000 calls (collect theta)', book: withTrades([short('call', 3000, 0.25)]), market: M0, rv: 0.2 },
    { label: 'costs eating edge', book: withTrades([], 0, { realizedEdge: 100, totalCosts: 60 }), market: M0, rv: 0.2 },
    { label: 'costs fine', book: withTrades([], 0, { realizedEdge: 100, totalCosts: 50 }), market: M0, rv: 0.2 },
    { label: 'short-dated gamma axe', book: withTrades([short('call', 3, 5 / 365)]), market: M0, rv: null },
    { label: 'everything', book: withTrades([short('call', 5000, 0.25)], 100), market: lowVol, rv: 0.3, step: 5 },
    {
      label: 'SPX mixed book',
      book: withTrades(
        [
          short('put', 150, 0.25, 1, 5900),
          long('call', 80, 0.5, 2, 6600),
          short('call', 40, 1 / 12, 3, 6325),
          long('put', 25, 1, 4, 5500),
        ],
        -35,
        { realizedEdge: 5230.5, totalCosts: 1210.25, cash: 12345.67 },
      ),
      market: SPX,
      rv: 0.19,
      step: 25,
    },
    { label: 'SPX tiny long gamma (-0 money)', book: withTrades([long('call', 0.001, 21 / 365, 1, 6300)]), market: SPX, rv: 0.1, step: 25 },
    { label: 'fractional grid', book: withTrades([short('call', 300, 0.3)], 0), market: { ...M0, spot: 100.37 }, rv: 0.3, step: 0.5 },
    { label: 'zero grid (falls back to 1)', book: withTrades([short('put', 300, 0.3)], 12), market: { ...M0, spot: 100.37 }, rv: 0.12, step: 0 },
    { label: 'expired trade on the book', book: withTrades([short('call', 50, 0.1, 1, 99), long('put', 40, 0.6, 2, 95)], 0), market: { ...SKEW, t: 0.2 }, rv: 0.22 },
  ]

  const probeRfqs: RFQ[] = [
    singleOptionRfq('call', 100, 0.25, 20, 'buy', 1),
    singleOptionRfq('call', 100, 0.25, 20, 'sell', 2),
    {
      id: 3,
      label: 'Straddle',
      legs: [
        { type: 'call', side: 'long', ratio: 1, K: 100, T: 0.5 },
        { type: 'put', side: 'long', ratio: 1, K: 100, T: 0.5 },
      ],
      size: 50,
      clientSide: 'sell',
      bornDay: 0,
    },
    {
      id: 4,
      label: 'Straddle',
      legs: [
        { type: 'call', side: 'long', ratio: 1, K: 100, T: 0.5 },
        { type: 'put', side: 'long', ratio: 1, K: 100, T: 0.5 },
      ],
      size: 50,
      clientSide: 'buy',
      bornDay: 0,
    },
    singleOptionRfq('call', 100, 5 / 365, 2, 'buy', 5),
    {
      id: 6,
      label: 'Risk reversal',
      legs: [
        { type: 'put', side: 'short', ratio: 1, K: 90, T: 0.5 },
        { type: 'call', side: 'long', ratio: 2, K: 110, T: 0.5 },
      ],
      size: 10,
      clientSide: 'sell',
      bornDay: 1,
    },
  ]
  // RFQ risk impact is probed on a representative subset of the books (keeps the file small).
  const PROBED = new Set([
    'empty',
    'short vega low vol',
    'short gamma hot',
    'long gamma quiet',
    'short straddle + delta',
    'long 3000 calls (pay theta)',
    'short-dated gamma axe',
    'SPX mixed book',
    'expired trade on the book',
  ])
  // Scale the probes to the market (SPX books get SPX strikes).
  const probesFor = (m: MarketState) =>
    probeRfqs.map((r) => ({ ...r, legs: r.legs.map((l) => ({ ...l, K: (l.K * m.spot) / 100 })) }))

  return cases.map((c) => ({
    label: c.label,
    book: bookOut(c.book),
    market: c.market,
    rv: c.rv,
    step: c.step ?? null,
    advice: c.step === undefined ? adviseBook(c.book, c.market, c.rv) : adviseBook(c.book, c.market, c.rv, c.step),
    joint: c.step === undefined ? jointHedge(c.book, c.market) : jointHedge(c.book, c.market, c.step),
    // the probe RFQs are rebuilt by the Python test (pure arithmetic), so only the impact is kept
    impacts: PROBED.has(c.label) ? probesFor(c.market).map((r) => rfqRiskImpact(r, c.book, c.market)) : null,
  }))
}

// ---------------------------------------------------------------------------- sessions

const NOISE_FRAC = 0.08
const HEDGE_TENOR = 60 / 365
const MAX_QUEUE = 4
const EXPIRE_DAYS = 4
const RFQ_ARRIVAL_PROB = 0.4
const SPREADS = [0.03, 0.05, 0.08]
const STRUCTURE_CYCLE: PresetName[] = ['strangle', 'risk-reversal', 'butterfly', 'calendar', 'iron-condor']
const SNAP_EVERY = 30

interface SessionCfg {
  name: string
  mode: 'simulated' | 'historical'
  market0: MarketState | null
  params: SimParams
  seeds: { market: number; rfq: number; noise: number; arrival: number; replay: number }
  strikeStep: number
  costs: CostModel
  steps: number
  replay: { seriesSeed: number; seriesLen: number; length: number; base: ReplayBase } | null
}

const ROW_COLUMNS = [
  'day', 't', 'spot', 'atmVol', 'realisedVol', 'bookValue', 'cash', 'underlyingQty', 'nextId', 'nTrades',
  'attTotal', 'attDelta', 'attGamma', 'attTheta', 'attVega', 'attVanna', 'attVolga', 'attResidual',
]
const QUOTE_COLUMNS = [
  'day', 'rfq', 'passed', 'verdict', 'dDelta', 'dVega', 'dGamma', 'net', 'gross', 'spread', 'lean', 'z',
  'filled', 'youSide', 'price', 'edge', 'bid', 'ask',
]

/**
 * The scripted desk. Every random stream is its own mulberry32 so the draw order is
 * explicit: market normals (inside MarketSimulator), RFQ contents, client noise, RFQ
 * arrival (drawn only when the queue has room, exactly like the UI), and the replay pick.
 */
function runSession(cfg: SessionCfg) {
  const round = (x: number) => Math.round(x / cfg.strikeStep) * cfg.strikeStep
  const rfqRng = mulberry32(cfg.seeds.rfq)
  const noise = makeNormal(mulberry32(cfg.seeds.noise))
  const arrival = mulberry32(cfg.seeds.arrival)

  let sim: MarketSimulator | null = null
  let win: ReplayWindow | null = null
  let market: MarketState
  let nSteps = cfg.steps
  if (cfg.mode === 'simulated') {
    sim = new MarketSimulator(cfg.market0!, cfg.params, cfg.seeds.market)
    market = sim.state
  } else {
    const series = syntheticSeries(cfg.replay!.seriesSeed, cfg.replay!.seriesLen)
    win = pickWindow(series, cfg.replay!.length, mulberry32(cfg.seeds.replay)())
    market = replayState(win, 0, cfg.replay!.base)
    nSteps = Math.min(cfg.steps, windowSteps(win))
  }

  let book = emptyBook()
  let queue: RFQ[] = []
  let nextRfqId = 1
  const spots = [market.spot]
  const rows: unknown[] = []
  const quotes: unknown[] = []
  const actions: unknown[] = []
  const snaps: unknown[] = []

  const execPlanQty = (q: number) => Math.max(1, Math.round(q))

  for (let day = 1; day <= nSteps; day++) {
    // 1) the market moves; explain the P&L of the book held over the step
    // (the StepResult deltas are checked in simPaths; here only the states matter)
    const next = sim ? sim.next().state : replayState(win!, day, cfg.replay!.base)
    const att = attribute(book, market, next)
    market = next
    spots.push(market.spot)

    // 2) client flow: expire stale RFQs; maybe a new one arrives; the trader asks for one
    queue = queue.filter((r) => day - r.bornDay <= EXPIRE_DAYS)
    if (queue.length < MAX_QUEUE && arrival() < RFQ_ARRIVAL_PROB) {
      queue.push(generateRFQ(market.spot, cfg.strikeStep, rfqRng, nextRfqId++, day))
    }
    if (day % 9 === 0 && queue.length < MAX_QUEUE) {
      queue.push(generateRFQ(market.spot, cfg.strikeStep, rfqRng, nextRfqId++, day))
    }

    // 3) quote the head of the queue (or pass on it), leaning on the risk-impact verdict
    if (queue.length > 0) {
      const rfq = queue.shift()!
      if (day % 7 === 6) {
        quotes.push([day, rfqOut(rfq), true])
      } else {
        const impact = rfqRiskImpact(rfq, book, market)
        const fair = rfqFair(rfq, market)
        const spread = SPREADS[day % 3]
        const toward = rfq.clientSide === 'buy' ? -1 : 1 // the lean that makes you likelier to trade
        const lean = impact.verdict === 'hedges' ? 0.02 * toward : impact.verdict === 'adds' ? -0.02 * toward : 0
        const z = noise()
        const fill = evaluateQuote(rfq, fair.net, fair.gross, spread, NOISE_FRAC, z, lean)
        book = addFill(book, fill, rfq, market)
        quotes.push([
          day, rfqOut(rfq), false, impact.verdict, impact.dDelta, impact.dVega, impact.dGamma,
          fair.net, fair.gross, spread, lean, z, fill.filled, fill.youSide, fill.price, fill.edge, fill.bid, fill.ask,
        ])
      }
    }

    // 4) risk management: a fixed schedule
    const rVol = realisedVol(spots, cfg.params.dt)
    if (day % 20 === 11) {
      // the combined hedge, executed like the UI: rounded option legs, then delta to flat
      const jh = jointHedge(book, market, cfg.strikeStep)
      if (jh.feasible) {
        const orders: OptionOrder[] = jh.legs
          .filter((l) => l.instrument === 'option')
          .map((l) => ({
            type: l.optionType ?? 'call',
            side: l.side === 'buy' ? 'long' : 'short',
            quantity: execPlanQty(l.quantity),
            K: l.K ?? round(market.spot),
            T: (l.tenorDays ?? 30) / 365,
          }))
        book = tradeStructure(book, orders, market, cfg.costs)
        book = hedgeToFlat(book, market, cfg.costs)
      }
      // (the rationale text is checked in the snapshots; here only the legs traded)
      actions.push({ day, kind: 'joint', feasible: jh.feasible, legs: jh.legs })
    } else if (day % 10 === 5) {
      book = flattenVega(book, market, HEDGE_TENOR, cfg.costs)
      actions.push({ day, kind: 'flattenVega' })
    } else if (day % 15 === 7) {
      book = flattenGamma(book, market, HEDGE_TENOR, cfg.costs)
      actions.push({ day, kind: 'flattenGamma' })
    } else if (day % 25 === 13) {
      const preset = STRUCTURE_CYCLE[Math.floor(day / 25) % STRUCTURE_CYCLE.length]
      const buy = Math.floor(day / 25) % 2 === 0
      const legs = buildPreset(preset, { S: market.spot, baseT: 30 / 365, widthPct: 0.04, strikeStep: cfg.strikeStep, volFor: () => 0 })
      const orders: OptionOrder[] = legs.map((l) => ({
        type: l.type,
        side: buy ? l.side : l.side === 'long' ? 'short' : 'long',
        quantity: l.quantity * 5,
        K: l.K,
        T: l.T,
      }))
      book = tradeStructure(book, orders, market, cfg.costs)
      actions.push({ day, kind: 'structure', preset, buy, nOrders: orders.length })
    } else if (day % 30 === 17) {
      // load the advisor's first concrete plan into the ticket and execute it
      const advice = adviseBook(book, market, rVol, cfg.strikeStep)
      const plan = advice.find((a) => a.plan !== undefined)?.plan
      if (plan) {
        const qty = execPlanQty(plan.quantity)
        const side = plan.side === 'buy' ? 'long' : 'short'
        if (plan.instrument === 'future') {
          book = hedgeTrade(book, side === 'long' ? qty : -qty, market, cfg.costs)
        } else {
          const T = (plan.tenorDays ?? 60) / 365
          book = tradeOption(book, { type: plan.optionType ?? 'call', side, quantity: qty, K: plan.K ?? round(market.spot), T }, market, cfg.costs)
        }
      }
      actions.push({ day, kind: 'plan', plan: plan ?? null })
    }
    if (day % 3 === 0) book = hedgeToFlat(book, market, cfg.costs)

    // 5) record
    rows.push([
      day, market.t, market.spot, market.atmVol, rVol, bookValue(book, market), book.cash, book.underlyingQty, book.nextId, book.trades.length,
      att.total, att.delta, att.gamma, att.theta, att.vega, att.vanna, att.volga, att.residual,
    ])
    if (day % SNAP_EVERY === 0 || day === nSteps) {
      snaps.push({
        day,
        realizedEdge: book.realizedEdge,
        totalCosts: book.totalCosts,
        greeks: bookGreeks(book, market),
        advice: adviseBook(book, market, rVol, cfg.strikeStep),
        joint: jointHedge(book, market, cfg.strikeStep),
      })
    }
  }

  return {
    cfg,
    window: win ? { startIndex: win.startIndex, points: win.points } : null,
    nSteps,
    rows,
    quotes,
    actions,
    snaps,
    finalBook: bookOut(book),
    finalMarket: market,
    finalMarked: markedLegs(book, market).map((l) => [l.id, l.T, l.sigma]),
  }
}

function sessions() {
  const cfgs: SessionCfg[] = [
    {
      // The UI's own configuration and seeds (SimulatorView): SPX snapshot, skewed surface.
      name: 'spx-ui',
      mode: 'simulated',
      market0: SPX,
      params: { ...DEFAULT_SIM_PARAMS, baseVol: 0.146 },
      seeds: { market: 0x9a17, rfq: 0x2bad, noise: 0x51de, arrival: 0xa771, replay: 0x7e1a },
      strikeStep: 25,
      costs: UI_COSTS,
      steps: 120,
      replay: null,
    },
    {
      // A 100-level flat surface, frictionless, with drift and a jumpier vol.
      name: 'flat-100',
      mode: 'simulated',
      market0: M0,
      params: { drift: 0.05, leverage: 1.5, volMeanRev: 2, baseVol: 0.22, volOfVol: 0.9, dt: 1 / 252 },
      seeds: { market: 101, rfq: 202, noise: 303, arrival: 404, replay: 505 },
      strikeStep: 5,
      costs: ZERO_COSTS,
      steps: 80,
      replay: null,
    },
    {
      // SX5E-like, WEEKLY steps: 1-month RFQs expire within the session (T floored).
      name: 'sx5e-weekly',
      mode: 'simulated',
      market0: { t: 0, spot: 4950, atmVol: 0.19, r: 0.025, q: 0.03, skewSlope: -0.6, skewCurv: 0.9 },
      params: { drift: 0, leverage: 1.2, volMeanRev: 3, baseVol: 0.18, volOfVol: 0.7, dt: 1 / 52 },
      seeds: { market: 7, rfq: 8, noise: 9, arrival: 10, replay: 11 },
      strikeStep: 50,
      costs: { underlyingHalfSpread: 0.0002, optionHalfSpread: 0.02 },
      steps: 52,
      replay: null,
    },
    {
      // Historical replay over the synthetic series (window picked by a seeded draw).
      name: 'replay',
      mode: 'historical',
      market0: null,
      params: { ...DEFAULT_SIM_PARAMS, baseVol: 0.146 },
      seeds: { market: 0, rfq: 0x2bae, noise: 0x51df, arrival: 0xa772, replay: 0x7e1a },
      strikeStep: 25,
      costs: UI_COSTS,
      steps: 90,
      replay: { seriesSeed: 0x7e1b, seriesLen: 300, length: 70, base: { r: 0.043, q: 0.013, skewSlope: -0.48, skewCurv: 0.62, dt: 1 / 252 } },
    },
  ]
  return cfgs.map(runSession)
}

it('exports sim goldens', () => {
  writeGolden(
    'sim',
    enc({
      constants: { defaultSimParams: DEFAULT_SIM_PARAMS, zeroCosts: ZERO_COSTS },
      volGrid: volGrid(),
      stepCases: stepCases(),
      simPaths: simPaths(),
      realisedVol: realisedVolCases(),
      rfqStreams: rfqStreams(),
      quoteGrid: quoteGrid(),
      attribution: attributionCases(),
      replay: replayGoldens(),
      advisor: advisorCases(),
      session: {
        rowColumns: ROW_COLUMNS,
        quoteColumns: QUOTE_COLUMNS,
        constants: { NOISE_FRAC, HEDGE_TENOR, MAX_QUEUE, EXPIRE_DAYS, RFQ_ARRIVAL_PROB, SPREADS, STRUCTURE_CYCLE, SNAP_EVERY },
        sessions: sessions(),
      },
    }),
  )
})
