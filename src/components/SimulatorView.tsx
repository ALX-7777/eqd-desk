/**
 * SimulatorView — the market-making desk. Two market modes (a simulated GBM path
 * with leverage, or REPLAY of a random undisclosed slice of real ^GSPC/^VIX
 * history), a QUEUE of client RFQs (singles and structures) that arrive
 * automatically while the market runs on Auto, two-way quoting with a lean,
 * active hedging (delta in the future; vega/gamma/any option via the market, at a
 * cost), and a live P&L explain on a skewed surface.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import {
  price as vanillaPrice,
  volForStrike,
  gbmLeverageProcess,
  DEFAULT_SIM_PARAMS,
  generateRFQ,
  evaluateQuote,
  emptyBook,
  addFill,
  hedgeToFlat,
  hedgeTrade,
  tradeOption,
  tradeStructure,
  flattenVega,
  flattenGamma,
  rfqFair,
  bookValue,
  bookGreeks,
  attribute,
  realisedVol,
  pickWindow,
  replayState,
  windowSteps,
  buildPreset,
  PRESETS,
  adviseBook,
  rfqRiskImpact,
  jointHedge,
  mulberry32,
  makeNormal,
  type MarketState,
  type Book,
  type RFQ,
  type CostModel,
  type JointHedge,
  type OptionType,
  type OptionOrder,
  type PresetName,
  type ReplayWindow,
  type HedgePlan,
} from '../engine'
import { snapshot } from '../data/snapshot'
import { historySeries, historyMeta } from '../data/history'
import { LabeledSlider, Segmented } from './Controls'
import { fmtNum, fmtMoney, fmtPct, signClass } from './format'
import { tooltipStyle, axisTick, axisStroke, gridStroke } from './chartTheme'
import { SIM_CONCEPTS, ATTRIBUTION_TERMS } from './simDocs'

const STRIKE_STEP = snapshot.spot >= 2000 ? 25 : 5
const round = (x: number) => Math.round(x / STRIKE_STEP) * STRIKE_STEP
const NOISE_FRAC = 0.08
const COSTS: CostModel = { underlyingHalfSpread: 0.0001, optionHalfSpread: 0.01 }
const HEDGE_TENOR = 60 / 365
const PARAMS = { ...DEFAULT_SIM_PARAMS, baseVol: snapshot.atm_vol_30d }
const REPLAY_BASE = { r: snapshot.r, q: snapshot.q, skewSlope: snapshot.skew.slope, skewCurv: snapshot.skew.curv, dt: PARAMS.dt }
const DEFAULT_WINDOW_LEN = 120
const MAX_QUEUE = 4
const EXPIRE_DAYS = 4
const RFQ_ARRIVAL_PROB = 0.4

type Mode = 'simulated' | 'historical'

interface Attr {
  delta: number
  gamma: number
  theta: number
  vega: number
  vanna: number
  volga: number
  residual: number
}
const ZERO_ATTR: Attr = { delta: 0, gamma: 0, theta: 0, vega: 0, vanna: 0, volga: 0, residual: 0 }

interface HistPoint {
  day: number
  spot: number
  vol: number
  pnl: number
}

interface SimState {
  market: MarketState
  book: Book
  queue: RFQ[]
  selectedId: number | null
  fill: { msg: string; won: boolean } | null
  history: HistPoint[]
  cumAttr: Attr
  day: number
  quotes: number
  fills: number
}

function initialMarket(mode: Mode, win: ReplayWindow | null): MarketState {
  if (mode === 'historical' && win) return replayState(win, 0, REPLAY_BASE)
  return { t: 0, spot: snapshot.spot, atmVol: snapshot.atm_vol_30d, r: snapshot.r, q: snapshot.q, skewSlope: snapshot.skew.slope, skewCurv: snapshot.skew.curv }
}

function initialState(mode: Mode, win: ReplayWindow | null): SimState {
  const market = initialMarket(mode, win)
  return {
    market,
    book: emptyBook(),
    queue: [],
    selectedId: null,
    fill: null,
    history: [{ day: 0, spot: market.spot, vol: market.atmVol, pnl: 0 }],
    cumAttr: ZERO_ATTR,
    day: 0,
    quotes: 0,
    fills: 0,
  }
}

export function SimulatorView({ active = true }: { active?: boolean }) {
  const [mode, setMode] = useState<Mode>('simulated')
  const [spread, setSpread] = useState(0.05)
  const [lean, setLean] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [autoDelay, setAutoDelay] = useState(650)
  const [replayLen, setReplayLen] = useState(DEFAULT_WINDOW_LEN)
  const [showAdvisor, setShowAdvisor] = useState(false)
  // trade ticket
  const [tkKind, setTkKind] = useState<'option' | 'structure' | 'future'>('option')
  const [tkType, setTkType] = useState<OptionType>('call')
  const [tkSide, setTkSide] = useState<'long' | 'short'>('long')
  const [tkK, setTkK] = useState(() => round(snapshot.spot))
  const [tkDays, setTkDays] = useState(60)
  const [tkSize, setTkSize] = useState(10)
  const [stPreset, setStPreset] = useState<PresetName>('straddle')
  const [stWidthPct, setStWidthPct] = useState(0.05)

  const marketNormal = useRef(makeNormal(mulberry32(0x9a17)))
  const rfqUniform = useRef(mulberry32(0x2bad))
  const noiseNormal = useRef(makeNormal(mulberry32(0x51de)))
  const arrivalRef = useRef(mulberry32(0xa771))
  const replayPick = useRef(mulberry32(0x7e1a))
  const replayWin = useRef<ReplayWindow | null>(null)
  const idRef = useRef(1)
  const resetCountRef = useRef(0)

  const [st, setSt] = useState<SimState>(() => initialState('simulated', null))

  const replayMax = replayWin.current ? windowSteps(replayWin.current) : Infinity

  const nextMarket = (s: SimState): MarketState => {
    if (mode === 'historical' && replayWin.current) return replayState(replayWin.current, s.day + 1, REPLAY_BASE)
    return gbmLeverageProcess.step(s.market, PARAMS, marketNormal.current).state
  }

  const advance = (spawn: boolean) =>
    setSt((s) => {
      if (mode === 'historical' && s.day >= replayMax) return s
      const next = nextMarket(s)
      const att = attribute(s.book, s.market, next)
      const cumAttr: Attr = {
        delta: s.cumAttr.delta + att.delta,
        gamma: s.cumAttr.gamma + att.gamma,
        theta: s.cumAttr.theta + att.theta,
        vega: s.cumAttr.vega + att.vega,
        vanna: s.cumAttr.vanna + att.vanna,
        volga: s.cumAttr.volga + att.volga,
        residual: s.cumAttr.residual + att.residual,
      }
      const day = s.day + 1
      const pnl = bookValue(s.book, next)
      let queue = s.queue.filter((r) => day - r.bornDay <= EXPIRE_DAYS)
      if (spawn && queue.length < MAX_QUEUE && arrivalRef.current() < RFQ_ARRIVAL_PROB) {
        queue = [...queue, generateRFQ(next.spot, STRIKE_STEP, rfqUniform.current, idRef.current++, day)]
      }
      let selectedId = s.selectedId
      if (selectedId != null && !queue.some((r) => r.id === selectedId)) selectedId = null
      if (selectedId == null && queue.length) selectedId = queue[0].id
      return { ...s, market: next, cumAttr, day, queue, selectedId, history: [...s.history, { day, spot: next.spot, vol: next.atmVol, pnl }] }
    })

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => advance(true), autoDelay)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, mode, autoDelay])

  // Auto-pause when navigating away (the session state stays mounted/preserved).
  useEffect(() => {
    if (!active) setPlaying(false)
  }, [active])

  // pause automatically at the end of a replay episode
  useEffect(() => {
    if (mode === 'historical' && playing && st.day >= replayMax) setPlaying(false)
  }, [mode, playing, st.day, replayMax])

  const requestRFQ = () =>
    setSt((s) => {
      if (s.queue.length >= MAX_QUEUE) return s
      const rfq = generateRFQ(s.market.spot, STRIKE_STEP, rfqUniform.current, idRef.current++, s.day)
      return { ...s, queue: [...s.queue, rfq], selectedId: s.selectedId ?? rfq.id, fill: null }
    })

  const selectRFQ = (id: number) => setSt((s) => ({ ...s, selectedId: id }))

  const quote = () =>
    setSt((s) => {
      const rfq = s.queue.find((r) => r.id === s.selectedId)
      if (!rfq) return s
      const { net, gross } = rfqFair(rfq, s.market)
      const f = evaluateQuote(rfq, net, gross, spread, NOISE_FRAC, noiseNormal.current(), lean)
      const queue = s.queue.filter((r) => r.id !== rfq.id)
      const selectedId = queue.length ? queue[0].id : null
      if (f.filled && f.youSide) {
        return { ...s, book: addFill(s.book, f, rfq, s.market), queue, selectedId, quotes: s.quotes + 1, fills: s.fills + 1, fill: { won: true, msg: `Filled — you ${f.youSide.toUpperCase()} ${rfq.size}× ${rfq.label} @ ${fmtMoney(f.price)} · edge ${fmtMoney(f.edge)}` } }
      }
      return { ...s, queue, selectedId, quotes: s.quotes + 1, fill: { won: false, msg: `Missed ${rfq.label} — client traded elsewhere` } }
    })

  const passRFQ = () =>
    setSt((s) => {
      const queue = s.queue.filter((r) => r.id !== s.selectedId)
      return { ...s, queue, selectedId: queue.length ? queue[0].id : null, fill: null }
    })

  const flattenDelta = () => setSt((s) => ({ ...s, book: hedgeToFlat(s.book, s.market, COSTS) }))
  const flatVega = () => setSt((s) => ({ ...s, book: flattenVega(s.book, s.market, HEDGE_TENOR, COSTS) }))
  const flatGamma = () => setSt((s) => ({ ...s, book: flattenGamma(s.book, s.market, HEDGE_TENOR, COSTS) }))

  // Load an advisor hedge plan into the trade ticket (you review the size & execute).
  const loadPlan = (plan: HedgePlan) => {
    const qty = Math.max(1, Math.round(plan.quantity))
    if (plan.instrument === 'future') {
      setTkKind('future')
      setTkSide(plan.side === 'buy' ? 'long' : 'short')
      setTkSize(qty)
    } else {
      setTkKind('option')
      setTkType(plan.optionType ?? 'call')
      setTkSide(plan.side === 'buy' ? 'long' : 'short')
      if (plan.K != null) setTkK(plan.K)
      if (plan.tenorDays != null) setTkDays(plan.tenorDays)
      setTkSize(qty)
    }
    setShowAdvisor(false)
  }

  // Execute the combined hedge (two options + future) in one shot. Greeks interact,
  // so we book the options first, then mop up the residual delta with hedgeToFlat —
  // the future goes LAST and adds nothing else, leaving delta exactly flat.
  const executeJoint = (jh: JointHedge) => {
    setSt((s) => {
      const orders = jh.legs
        .filter((l) => l.instrument === 'option')
        .map((l) => ({
          type: l.optionType ?? ('call' as OptionType),
          side: (l.side === 'buy' ? 'long' : 'short') as 'long' | 'short',
          quantity: Math.max(1, Math.round(l.quantity)),
          K: l.K ?? round(s.market.spot),
          T: (l.tenorDays ?? 30) / 365,
        }))
      let book = tradeStructure(s.book, orders, s.market, COSTS)
      book = hedgeToFlat(book, s.market, COSTS)
      return { ...s, book }
    })
    setShowAdvisor(false)
  }

  const flipSide = (sd: 'long' | 'short'): 'long' | 'short' => (sd === 'long' ? 'short' : 'long')
  const structureOrders = (m: MarketState): OptionOrder[] =>
    buildPreset(stPreset, { S: m.spot, baseT: tkDays / 365, widthPct: stWidthPct, strikeStep: STRIKE_STEP, volFor: () => 0 }).map((l) => ({
      type: l.type,
      side: tkSide === 'long' ? l.side : flipSide(l.side),
      quantity: l.quantity * tkSize,
      K: l.K,
      T: l.T,
    }))

  const executeTicket = () =>
    setSt((s) => {
      if (tkKind === 'future') return { ...s, book: hedgeTrade(s.book, tkSide === 'long' ? tkSize : -tkSize, s.market, COSTS) }
      if (tkKind === 'structure') return { ...s, book: tradeStructure(s.book, structureOrders(s.market), s.market, COSTS) }
      return { ...s, book: tradeOption(s.book, { type: tkType, side: tkSide, quantity: tkSize, K: tkK, T: tkDays / 365 }, s.market, COSTS) }
    })

  const reset = (m: Mode = mode, len: number = replayLen) => {
    const n = ++resetCountRef.current
    marketNormal.current = makeNormal(mulberry32(0x9a17 + n * 101))
    noiseNormal.current = makeNormal(mulberry32(0x51de + n * 211))
    arrivalRef.current = mulberry32(0xa771 + n * 307)
    idRef.current = 1
    setPlaying(false)
    const win = m === 'historical' ? pickWindow(historySeries, len, replayPick.current()) : null
    replayWin.current = win
    setSt(initialState(m, win))
  }

  const switchMode = (m: Mode) => {
    setMode(m)
    reset(m)
  }

  const greeks = useMemo(() => bookGreeks(st.book, st.market), [st.book, st.market])
  const pnl = useMemo(() => bookValue(st.book, st.market), [st.book, st.market])
  const rVol = useMemo(() => realisedVol(st.history.map((h) => h.spot), PARAMS.dt), [st.history])
  const advice = useMemo(() => adviseBook(st.book, st.market, rVol, STRIKE_STEP), [st.book, st.market, rVol])
  const jh = useMemo(() => jointHedge(st.book, st.market, STRIKE_STEP), [st.book, st.market])
  // Only worth a combined hedge when both gamma and vega are meaningfully exposed.
  const showJoint = jh.feasible && Math.abs(greeks.reported.vega) > 80 && Math.abs(greeks.raw.gamma) > 1e-6

  const selected = st.queue.find((r) => r.id === st.selectedId) ?? null
  const sel = selected ? rfqFair(selected, st.market) : null
  const selImpact = selected ? rfqRiskImpact(selected, st.book, st.market) : null
  const mid = sel ? sel.net + lean * sel.gross : 0
  const bid = sel ? mid - (spread / 2) * sel.gross : 0
  const ask = sel ? mid + (spread / 2) * sel.gross : 0

  const tkFair = tkKind === 'option'
    ? vanillaPrice({ S: st.market.spot, K: tkK, T: tkDays / 365, r: st.market.r, q: st.market.q, sigma: volForStrike(st.market, tkK, tkDays / 365) }, tkType)
    : st.market.spot
  const legFairOf = (o: OptionOrder) => vanillaPrice({ S: st.market.spot, K: o.K, T: o.T, r: st.market.r, q: st.market.q, sigma: volForStrike(st.market, o.K, o.T) }, o.type)
  const stOrders = tkKind === 'structure' ? structureOrders(st.market) : []
  const stNet = stOrders.reduce((a, o) => a + (o.side === 'long' ? 1 : -1) * legFairOf(o) * o.quantity, 0)
  const stCost = stOrders.reduce((a, o) => a + Math.abs(legFairOf(o)) * o.quantity * COSTS.optionHalfSpread, 0)
  const tkCost = tkKind === 'option' ? tkSize * Math.abs(tkFair) * COSTS.optionHalfSpread : tkSize * st.market.spot * COSTS.underlyingHalfSpread

  const attrData = ATTRIBUTION_TERMS.map((t) => ({ name: t.label, value: st.cumAttr[t.key] }))
  const fillRate = st.quotes > 0 ? st.fills / st.quotes : 0
  const deltaWarn = Math.abs(greeks.reported.delta) > 40
  const vegaWarn = Math.abs(greeks.reported.vega) > 1500
  const atEnd = mode === 'historical' && st.day >= replayMax

  return (
    <main className="layout">
      {/* ---- left: market, scorecard, RFQ queue ---- */}
      <section className="col col-left">
        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Market</h2>
            <Segmented options={[{ value: 'simulated', label: 'Simulated' }, { value: 'historical', label: 'Replay' }]} value={mode} onChange={switchMode} />
          </div>
          <div className="sim-stats mono">
            <div><span className="dim">Spot</span><span>{fmtMoney(st.market.spot)}</span></div>
            <div><span className="dim">ATM vol (implied)</span><span className="accent">{fmtPct(st.market.atmVol)}</span></div>
            <div><span className="dim">Realised vol</span><span className={rVol != null && rVol > st.market.atmVol ? 'pos' : 'neg'}>{rVol != null ? fmtPct(rVol) : '—'}</span></div>
            <div><span className="dim">{mode === 'historical' ? 'Replay day' : 'Skew slope'}</span><span>{mode === 'historical' ? `${st.day} / ${replayMax}` : fmtNum(st.market.skewSlope ?? 0, 3)}</span></div>
          </div>
          {mode === 'historical' && (
            <>
              <div className="chart-caption dim" style={{ marginTop: 6 }}>Undisclosed slice of real S&amp;P 500 / VIX history ({historyMeta.count} days on file).</div>
              <div style={{ marginTop: 8 }}>
                <LabeledSlider label="Replay length" value={replayLen} min={30} max={504} step={6} display={`${replayLen} days`} onChange={setReplayLen} />
                <div className="chart-caption dim" style={{ marginTop: -2 }}>Applies on the next reset.</div>
              </div>
            </>
          )}
          {atEnd && <div className="fill-msg lost" style={{ marginTop: 8 }}>Episode ended — reset for a new one.</div>}
          <div style={{ marginTop: 10 }}>
            <LabeledSlider label="Auto speed" value={autoDelay} min={120} max={3000} step={60} display={`${autoDelay} ms/day`} onChange={setAutoDelay} />
          </div>
          <div className="input-actions">
            <button className="btn" onClick={() => advance(false)} disabled={atEnd}>▶ Tick</button>
            <button className="btn" onClick={() => setPlaying((p) => !p)} disabled={atEnd}>{playing ? '❚❚ Pause' : '▶▶ Auto'}</button>
          </div>
          <button className="btn" style={{ width: '100%', marginTop: 8 }} onClick={() => reset()}>⟲ Reset session</button>
        </div>

        <div className="panel">
          <div className="panel-title-row"><h2 className="panel-title">Desk scorecard</h2></div>
          <div className="sim-stats mono">
            <div><span className="dim">P&amp;L</span><span className={signClass(pnl)}>{pnl >= 0 ? '+' : ''}{fmtMoney(pnl)}</span></div>
            <div><span className="dim">Edge captured</span><span className="pos">{fmtMoney(st.book.realizedEdge)}</span></div>
            <div><span className="dim">Costs paid</span><span className="neg">−{fmtMoney(st.book.totalCosts)}</span></div>
            <div><span className="dim">Fill rate</span><span>{fmtPct(fillRate, 0)} ({st.fills}/{st.quotes})</span></div>
            <div><span className="dim">Net Δ</span><span className={deltaWarn ? 'neg' : 'dim'}>{fmtNum(greeks.reported.delta)} {deltaWarn ? '⚠' : ''}</span></div>
            <div><span className="dim">Net vega</span><span className={vegaWarn ? 'neg' : 'dim'}>{fmtNum(greeks.reported.vega)} {vegaWarn ? '⚠' : ''}</span></div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Client RFQs</h2>
            <span className="tag subtle">{st.queue.length} live</span>
          </div>
          <div className="rfq-queue">
            {st.queue.length === 0 && <div className="dim" style={{ fontSize: 12, marginBottom: 8 }}>No live requests — Auto brings them in, or request one.</div>}
            {st.queue.map((r) => {
              const f = rfqFair(r, st.market)
              const v = rfqRiskImpact(r, st.book, st.market).verdict
              return (
                <button key={r.id} className={`rfq-chip ${r.id === st.selectedId ? 'active' : ''}`} onClick={() => selectRFQ(r.id)}>
                  <span className={`dot ${r.clientSide === 'buy' ? 'buy' : 'sell'}`}>{r.clientSide === 'buy' ? '▲' : '▼'}</span>
                  <span className="mono">{r.size}× {r.label}</span>
                  <span className={`rfq-flag ${v}`} title={v === 'hedges' ? 'winning this cuts your risk' : v === 'adds' ? 'winning this adds risk' : ''}>{v === 'hedges' ? '↓' : v === 'adds' ? '↑' : ''}</span>
                  <span className="dim mono">{fmtMoney(f.net)}</span>
                </button>
              )
            })}
          </div>

          {selected && sel && (
            <div className="quote-box">
              <div className="rfq-detail dim mono">
                CLIENT {selected.clientSide.toUpperCase()}S · {selected.legs.map((l) => `${l.side === 'long' ? '+' : '−'}${l.ratio} ${l.type === 'call' ? 'C' : 'P'}${Math.round(l.K)}`).join(' ')} · net {fmtMoney(sel.net)}
              </div>
              {selImpact && (
                <div className={`rfq-impact ${selImpact.verdict}`}>
                  {selImpact.verdict === 'hedges' ? '↓ ' : selImpact.verdict === 'adds' ? '↑ ' : ''}
                  {selImpact.note}
                </div>
              )}
              <LabeledSlider label="Your spread" value={spread} min={0.005} max={0.2} step={0.005} display={fmtPct(spread)} onChange={setSpread} />
              <LabeledSlider label="Lean (skew your price)" value={lean} min={-0.03} max={0.03} step={0.0025} display={`${lean >= 0 ? '+' : ''}${fmtPct(lean)}`} onChange={setLean} />
              <div className="quote-row mono">
                <span className="quote-bid">bid {fmtMoney(bid)}</span>
                <span className="quote-ask">ask {fmtMoney(ask)}</span>
              </div>
              <div className="input-actions">
                <button className="btn quote-btn" onClick={quote}>Quote</button>
                <button className="btn" onClick={passRFQ}>Pass</button>
              </div>
            </div>
          )}
          <button className="btn" style={{ width: '100%', marginTop: 8 }} onClick={requestRFQ} disabled={st.queue.length >= MAX_QUEUE}>Request a quote →</button>
          {st.fill && <div className={`fill-msg ${st.fill.won ? 'won' : 'lost'}`}>{st.fill.msg}</div>}
        </div>
      </section>

      {/* ---- center: P&L + attribution + path ---- */}
      <section className="col col-center">
        <div className="panel grow">
          <div className="panel-title-row">
            <h2 className="panel-title">P&amp;L</h2>
            <span className={`tag ${pnl >= 0 ? '' : 'subtle'}`}>{pnl >= 0 ? 'up' : 'down'}</span>
          </div>
          <div className="price-hero" style={{ cursor: 'default' }}>
            <div className={`price-hero-main mono ${signClass(pnl)}`}>{pnl >= 0 ? '+' : ''}{fmtMoney(pnl)}</div>
            <div className="price-hero-sub">
              <span>mark-to-market P&amp;L ({snapshot.currency})</span>
              <span className="dim">edge {fmtMoney(st.book.realizedEdge)} · costs {fmtMoney(st.book.totalCosts)}</span>
            </div>
          </div>
          <div className="chart-wrap short">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={st.history} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={gridStroke} strokeDasharray="2 4" />
                <XAxis dataKey="day" type="number" domain={['dataMin', 'dataMax']} stroke={axisStroke} tick={axisTick} />
                <YAxis tickFormatter={(v) => fmtNum(v, 3)} stroke={axisStroke} tick={axisTick} width={56} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => `Day ${v}`} formatter={(v) => [fmtMoney(Number(v)), 'P&L']} />
                <ReferenceLine y={0} stroke={axisStroke} />
                <Line type="monotone" dataKey="pnl" stroke="var(--accent)" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <h3 className="sub-head">P&amp;L explain (cumulative)</h3>
          <div className="chart-wrap short">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={attrData} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={gridStroke} strokeDasharray="2 4" />
                <XAxis dataKey="name" stroke={axisStroke} tick={{ fontSize: 10, fill: 'var(--text-dim)' }} />
                <YAxis tickFormatter={(v) => fmtNum(v, 2)} stroke={axisStroke} tick={axisTick} width={56} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => [fmtMoney(Number(v)), 'P&L']} />
                <ReferenceLine y={0} stroke={axisStroke} />
                <Bar dataKey="value" isAnimationActive={false}>
                  {attrData.map((d, idx) => (
                    <Cell key={idx} fill={d.value >= 0 ? 'var(--pos)' : 'var(--neg)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <h3 className="sub-head">Spot &amp; vol path</h3>
          <div className="chart-wrap short">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={st.history} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={gridStroke} strokeDasharray="2 4" />
                <XAxis dataKey="day" type="number" domain={['dataMin', 'dataMax']} stroke={axisStroke} tick={axisTick} />
                <YAxis yAxisId="s" tickFormatter={(v) => v.toFixed(0)} stroke={axisStroke} tick={axisTick} width={56} />
                <YAxis yAxisId="v" orientation="right" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} stroke={axisStroke} tick={axisTick} width={44} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => `Day ${v}`} />
                <Line yAxisId="s" type="monotone" dataKey="spot" stroke="var(--line)" strokeWidth={2} dot={false} isAnimationActive={false} name="spot" />
                <Line yAxisId="v" type="monotone" dataKey="vol" stroke="var(--put)" strokeWidth={1.5} dot={false} isAnimationActive={false} name="vol" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* ---- right: book + hedging + ticket + learn ---- */}
      <section className="col col-right">
        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Book &amp; hedging</h2>
            <button className="btn advisor-open" onClick={() => setShowAdvisor(true)}>💡 Advisor</button>
          </div>
          <table className="greeks-table">
            <tbody>
              {(['delta', 'gamma', 'vega', 'theta'] as const).map((k) => (
                <tr key={k} className="greek-row" style={{ cursor: 'default' }}>
                  <td className="g-label">{k[0].toUpperCase() + k.slice(1)}</td>
                  <td className={`g-value mono ${signClass(greeks.reported[k])}`}>{fmtNum(greeks.reported[k])}</td>
                </tr>
              ))}
              <tr className="greek-row" style={{ cursor: 'default' }}>
                <td className="g-label">Hedge (underlying)</td>
                <td className={`g-value mono ${signClass(st.book.underlyingQty)}`}>{fmtNum(st.book.underlyingQty, 3)}</td>
              </tr>
            </tbody>
          </table>
          <div className="hedge-grid">
            <button className="btn" onClick={flattenDelta}>Flatten Δ (future)</button>
            <button className="btn" onClick={flatVega}>Flatten vega (opt)</button>
            <button className="btn" onClick={flatGamma}>Flatten Γ (opt)</button>
          </div>
          <div className="chart-caption dim" style={{ marginTop: 6 }}>Option hedges cross the market spread (a cost); they flatten one greek but pick up others.</div>

          <h3 className="sub-head">
            Positions ({st.book.trades.length + (st.book.underlyingQty !== 0 ? 1 : 0)})
          </h3>
          <div className="blotter">
            {st.book.trades.length === 0 && st.book.underlyingQty === 0 && (
              <div className="dim" style={{ fontSize: 12 }}>No trades yet.</div>
            )}
            {st.book.underlyingQty !== 0 && (
              <div className="blotter-row mono">
                <span className={st.book.underlyingQty > 0 ? 'pos' : 'neg'}>
                  {st.book.underlyingQty > 0 ? '+' : '−'}
                  {fmtNum(Math.abs(st.book.underlyingQty), 1)}
                </span>
                <span>FUTURE</span>
                <span className="dim">Δ-hedge</span>
              </div>
            )}
            {st.book.trades.slice(-8).map((t) => (
              <div key={t.id} className="blotter-row mono">
                <span className={t.side === 'long' ? 'pos' : 'neg'}>{t.side === 'long' ? '+' : '−'}{fmtNum(t.quantity, 1)}</span>
                <span>{t.type === 'call' ? 'C' : 'P'} {fmtMoney(t.K)}</span>
                <span className="dim">{Math.max(0, Math.round((t.expiryTime - st.market.t) * 365))}d</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title-row"><h2 className="panel-title">Trade ticket</h2></div>
          <div style={{ marginBottom: 10 }}>
            <Segmented options={[{ value: 'option', label: 'Option' }, { value: 'structure', label: 'Structure' }, { value: 'future', label: 'Future' }]} value={tkKind} onChange={setTkKind} />
          </div>
          {tkKind === 'option' && (
            <div className="ticket-grid">
              <Segmented options={[{ value: 'long', label: 'Buy' }, { value: 'short', label: 'Sell' }]} value={tkSide} onChange={setTkSide} />
              <Segmented options={[{ value: 'call', label: 'Call' }, { value: 'put', label: 'Put' }]} value={tkType} onChange={setTkType} />
              <label className="tk-field"><span className="dim">Strike</span><input className="mono leg-num" type="number" step={STRIKE_STEP} value={tkK} onChange={(e) => setTkK(Number(e.target.value) || tkK)} /></label>
              <label className="tk-field"><span className="dim">Exp (d)</span><input className="mono leg-num" type="number" step={5} value={tkDays} onChange={(e) => setTkDays(Math.max(1, Number(e.target.value) || tkDays))} /></label>
              <label className="tk-field"><span className="dim">Size</span><input className="mono leg-num" type="number" step={5} value={tkSize} onChange={(e) => setTkSize(Math.max(1, Number(e.target.value) || tkSize))} /></label>
            </div>
          )}
          {tkKind === 'structure' && (
            <>
              <div className="preset-grid">
                {PRESETS.map((p) => (
                  <button key={p.name} className={`preset-btn ${stPreset === p.name ? 'active' : ''}`} onClick={() => setStPreset(p.name)}>{p.label}</button>
                ))}
              </div>
              <div className="ticket-grid">
                <Segmented options={[{ value: 'long', label: 'Buy' }, { value: 'short', label: 'Sell' }]} value={tkSide} onChange={setTkSide} />
                <label className="tk-field"><span className="dim">Wing %</span><input className="mono leg-num" type="number" step={1} value={Math.round(stWidthPct * 100)} onChange={(e) => setStWidthPct(Math.max(1, Number(e.target.value) || stWidthPct * 100) / 100)} /></label>
                <label className="tk-field"><span className="dim">Exp (d)</span><input className="mono leg-num" type="number" step={5} value={tkDays} onChange={(e) => setTkDays(Math.max(1, Number(e.target.value) || tkDays))} /></label>
                <label className="tk-field"><span className="dim">Size</span><input className="mono leg-num" type="number" step={5} value={tkSize} onChange={(e) => setTkSize(Math.max(1, Number(e.target.value) || tkSize))} /></label>
              </div>
            </>
          )}
          {tkKind === 'future' && (
            <div className="ticket-grid">
              <Segmented options={[{ value: 'long', label: 'Buy' }, { value: 'short', label: 'Sell' }]} value={tkSide} onChange={setTkSide} />
              <label className="tk-field"><span className="dim">Size</span><input className="mono leg-num" type="number" step={1} value={tkSize} onChange={(e) => setTkSize(Math.max(1, Number(e.target.value) || tkSize))} /></label>
            </div>
          )}
          <div className="quote-row mono">
            <span className="dim">{tkKind === 'structure' ? `net ${fmtMoney(stNet)}` : tkKind === 'option' ? `price ${fmtMoney(tkFair)}` : `spot ${fmtMoney(st.market.spot)}`}</span>
            <span className="neg">cost −{fmtMoney(tkKind === 'structure' ? stCost : tkCost)}</span>
          </div>
          <button className="btn quote-btn" style={{ width: '100%' }} onClick={executeTicket}>Execute @ market</button>
        </div>

        <div className="panel grow">
          <div className="panel-title-row">
            <h2 className="panel-title">Learn</h2>
            <span className="tag subtle">market-making</span>
          </div>
          <div className="edu-rels">
            {SIM_CONCEPTS.map((c) => (
              <details key={c.title} className="rel">
                <summary>{c.title}</summary>
                <p>{c.body}</p>
              </details>
            ))}
          </div>
          <h3 className="sub-head">P&amp;L explain terms</h3>
          <dl className="edu-dl">
            {ATTRIBUTION_TERMS.map((t) => (
              <div key={t.key}>
                <dt>{t.label}</dt>
                <dd>{t.note}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {showAdvisor && (
        <div className="advisor-overlay" onClick={() => setShowAdvisor(false)}>
          <div className="advisor-card" onClick={(e) => e.stopPropagation()}>
            <div className="advisor-head">
              <div>
                <h2 className="panel-title">💡 Desk advisor</h2>
                <div className="dim" style={{ fontSize: 11.5, marginTop: 3 }}>Reads your live book &amp; the market — ranked by what to deal with first.</div>
              </div>
              <button className="advisor-close" onClick={() => setShowAdvisor(false)} aria-label="close advisor">✕</button>
            </div>
            <div className="advisor-list">
              {advice.map((a, i) => (
                <div key={i} className={`advice sev-${a.severity}`}>
                  <div className="advice-top">
                    <span className={`sev-dot sev-${a.severity}`} />
                    <span className="advice-title">{a.title}</span>
                  </div>
                  <p className="advice-detail">{a.detail}</p>
                  {a.plan && (
                    <div className="advice-plan">
                      <div className="plan-line mono">
                        <span className={`plan-side ${a.plan.side}`}>{a.plan.side.toUpperCase()}</span>
                        <span>
                          {Math.max(1, Math.round(a.plan.quantity)).toLocaleString('en-US')} ×{' '}
                          {a.plan.instrument === 'future'
                            ? 'FUTURE'
                            : `${a.plan.optionType === 'put' ? 'Put' : 'Call'} ${a.plan.K} · ${a.plan.tenorDays}d`}
                        </span>
                      </div>
                      <p className="plan-why">{a.plan.rationale}</p>
                      <button className="btn quote-btn" onClick={() => loadPlan(a.plan!)}>Load into ticket →</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
            {showJoint && (
              <div className="joint-hedge">
                <div className="joint-head">
                  <span className="joint-title">⚖︎ Hedge the book together</span>
                  <span className="dim" style={{ fontSize: 11 }}>greeks interact — don&apos;t chase them one at a time</span>
                </div>
                <div className="joint-legs">
                  {jh.legs.map((l, i) => (
                    <div key={i} className="plan-line mono">
                      <span className={`plan-side ${l.side}`}>{l.side.toUpperCase()}</span>
                      <span>
                        {Math.max(0, Math.round(l.quantity)).toLocaleString('en-US')} ×{' '}
                        {l.instrument === 'future' ? 'FUTURE' : `${l.optionType === 'put' ? 'Put' : 'Call'} ${l.K} · ${l.tenorDays}d`}
                      </span>
                      <span className="dim joint-role">
                        {l.instrument === 'future' ? 'cleans up Δ (last)' : l.tenorDays && l.tenorDays <= 30 ? 'gamma' : 'vega'}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="plan-why">{jh.rationale}</p>
                <button className="btn quote-btn" onClick={() => executeJoint(jh)}>Execute combined hedge →</button>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  )
}
