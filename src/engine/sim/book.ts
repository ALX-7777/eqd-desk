/**
 * The trading book: filled option trades + an underlying (index-proxy) hedge +
 * cash. Marked off the current market's single ATM vol. Clean accounting:
 *
 *   bookValue = cash + Σ(marked option value) + underlyingQty·spot
 *
 * starts at 0 (no positions, no cash), so bookValue IS the running P&L. Trading
 * away from fair makes value jump by the edge; hedging in the underlying is
 * value-neutral at execution (frictionless).
 */

import { analyzePosition, type Leg } from '../strategy'
import { toReported } from '../reporting'
import { rawGreeks } from '../greeks'
import { price as vanillaPrice } from '../bsm'
import type { OptionType, RawGreeks, ReportedGreeks } from '../types'
import { volForStrike, type MarketState } from './market'
import type { RFQ } from './rfq'
import type { FillResult } from './quote'

export interface BookTrade {
  id: number
  type: OptionType
  side: 'long' | 'short'
  quantity: number
  K: number
  /** Absolute sim-clock time (years) at which this option expires. */
  expiryTime: number
  tradedPrice: number
}

export interface Book {
  trades: BookTrade[]
  /** Signed position in the index proxy (delta 1). */
  underlyingQty: number
  cash: number
  /** Cumulative edge captured at trade time (a stat). */
  realizedEdge: number
  /** Cumulative transaction costs paid crossing the market on hedges/tickets. */
  totalCosts: number
  nextId: number
}

export function emptyBook(): Book {
  return { trades: [], underlyingQty: 0, cash: 0, realizedEdge: 0, totalCosts: 0, nextId: 1 }
}

/** Market trading costs (half-spreads you cross when you hedge in the market). */
export interface CostModel {
  /** Underlying half-spread as a fraction of spot (e.g. 0.0001 = 1 bp). */
  underlyingHalfSpread: number
  /** Option half-spread as a fraction of premium (e.g. 0.01 = 1%). */
  optionHalfSpread: number
}

export const ZERO_COSTS: CostModel = { underlyingHalfSpread: 0, optionHalfSpread: 0 }

/** Trades re-expressed as legs marked on the current surface (vol = skew vol, T = remaining). */
export function markedLegs(book: Book, m: MarketState): Leg[] {
  return book.trades.map((t) => {
    const T = Math.max(t.expiryTime - m.t, 1e-6)
    return {
      id: String(t.id),
      type: t.type,
      side: t.side,
      quantity: t.quantity,
      K: t.K,
      T,
      sigma: volForStrike(m, t.K, T),
    }
  })
}

/** Net option value (signed) of the book at the current market. */
function optionValue(book: Book, m: MarketState): number {
  if (book.trades.length === 0) return 0
  return analyzePosition(markedLegs(book, m), { S: m.spot, r: m.r, q: m.q }).price
}

/** Book mark-to-market value (= running P&L, since it starts at 0). */
export function bookValue(book: Book, m: MarketState): number {
  return book.cash + optionValue(book, m) + book.underlyingQty * m.spot
}

/** Net raw greeks of the book, with the underlying hedge folded into delta. */
export function bookGreeksRaw(book: Book, m: MarketState): RawGreeks {
  const raw =
    book.trades.length === 0
      ? zero()
      : analyzePosition(markedLegs(book, m), { S: m.spot, r: m.r, q: m.q }).raw
  return { ...raw, delta: raw.delta + book.underlyingQty }
}

/** Net greeks of the book in raw and desk-reported units. */
export function bookGreeks(book: Book, m: MarketState): { raw: RawGreeks; reported: ReportedGreeks } {
  const raw = bookGreeksRaw(book, m)
  return { raw, reported: toReported(raw) }
}

/**
 * Net (signed) and gross (Σ|leg|) fair value of an RFQ package at the current
 * surface. The trader quotes around `net`; the spread/lean are sized off `gross`.
 */
export function rfqFair(rfq: RFQ, m: MarketState): { net: number; gross: number } {
  let net = 0
  let gross = 0
  for (const leg of rfq.legs) {
    const sigma = volForStrike(m, leg.K, leg.T)
    const p = vanillaPrice({ S: m.spot, K: leg.K, T: leg.T, r: m.r, q: m.q, sigma }, leg.type)
    net += (leg.side === 'long' ? 1 : -1) * leg.ratio * p
    gross += leg.ratio * Math.abs(p)
  }
  return { net, gross }
}

/**
 * Add a filled RFQ to the book — you take the opposite side of the client on the
 * whole package. Package cash flows at the net traded price; each leg is booked
 * at its fair (the mark), so book value jumps by exactly `fill.edge`.
 */
export function addFill(book: Book, fill: FillResult, rfq: RFQ, m: MarketState): Book {
  if (!fill.filled || fill.youSide === null) return book
  const cashFlow = fill.youSide === 'sell' ? fill.price * rfq.size : -fill.price * rfq.size
  let nextId = book.nextId
  const trades = book.trades.slice()
  for (const leg of rfq.legs) {
    // client buys package ⇒ you short each leg (flip); client sells ⇒ you long it.
    const yourSide: 'long' | 'short' =
      rfq.clientSide === 'buy' ? (leg.side === 'long' ? 'short' : 'long') : leg.side
    const sigma = volForStrike(m, leg.K, leg.T)
    const legFair = vanillaPrice({ S: m.spot, K: leg.K, T: leg.T, r: m.r, q: m.q, sigma }, leg.type)
    trades.push({
      id: nextId++,
      type: leg.type,
      side: yourSide,
      quantity: leg.ratio * rfq.size,
      K: leg.K,
      expiryTime: m.t + leg.T,
      tradedPrice: legFair,
    })
  }
  return { ...book, trades, cash: book.cash + cashFlow, realizedEdge: book.realizedEdge + fill.edge, nextId }
}

/** Trade `dq` units of the underlying, crossing the market half-spread. */
export function hedgeTrade(book: Book, dq: number, m: MarketState, costs: CostModel = ZERO_COSTS): Book {
  const cost = Math.abs(dq) * m.spot * costs.underlyingHalfSpread
  return {
    ...book,
    underlyingQty: book.underlyingQty + dq,
    cash: book.cash - dq * m.spot - cost,
    totalCosts: book.totalCosts + cost,
  }
}

/** Trade the underlying to flatten net delta. */
export function hedgeToFlat(book: Book, m: MarketState, costs: CostModel = ZERO_COSTS): Book {
  const netDelta = bookGreeksRaw(book, m).delta
  return hedgeTrade(book, -netDelta, m, costs)
}

/** A proactive order to trade an option in the market. */
export interface OptionOrder {
  type: OptionType
  side: 'long' | 'short'
  quantity: number
  K: number
  T: number
}

/**
 * Trade an option in the market (your own hedge), crossing the option half-spread.
 * Unlike a client fill you DON'T capture edge — you pay the spread, so book value
 * falls by exactly the cost.
 */
export function tradeOption(book: Book, order: OptionOrder, m: MarketState, costs: CostModel = ZERO_COSTS): Book {
  if (order.quantity <= 0) return book
  const sigma = volForStrike(m, order.K, order.T)
  const fair = vanillaPrice({ S: m.spot, K: order.K, T: order.T, r: m.r, q: m.q, sigma }, order.type)
  const cost = order.quantity * Math.abs(fair) * costs.optionHalfSpread
  const cashFlow = order.side === 'long' ? -fair * order.quantity - cost : fair * order.quantity - cost
  const trade: BookTrade = {
    id: book.nextId,
    type: order.type,
    side: order.side,
    quantity: order.quantity,
    K: order.K,
    expiryTime: m.t + order.T,
    tradedPrice: fair,
  }
  return {
    ...book,
    trades: [...book.trades, trade],
    cash: book.cash + cashFlow,
    totalCosts: book.totalCosts + cost,
    nextId: book.nextId + 1,
  }
}

/** Trade a multi-leg structure in the market (each leg crosses the option spread). */
export function tradeStructure(book: Book, orders: OptionOrder[], m: MarketState, costs: CostModel = ZERO_COSTS): Book {
  let b = book
  for (const o of orders) b = tradeOption(b, o, m, costs)
  return b
}

/** Trade an ATM option of tenor `tenorT` to flatten net vega (picks up some gamma/delta). */
export function flattenVega(book: Book, m: MarketState, tenorT: number, costs: CostModel = ZERO_COSTS): Book {
  const netVega = bookGreeksRaw(book, m).vega
  const K = m.spot
  const sigma = volForStrike(m, K, tenorT)
  const legVega = rawGreeks({ S: m.spot, K, T: tenorT, r: m.r, q: m.q, sigma }, 'call').vega
  if (legVega < 1e-9) return book
  const need = -netVega / legVega
  if (Math.abs(need) < 1e-6) return book
  return tradeOption(book, { type: 'call', side: need >= 0 ? 'long' : 'short', quantity: Math.abs(need), K, T: tenorT }, m, costs)
}

/** Trade an ATM option of tenor `tenorT` to flatten net gamma (picks up some vega/delta). */
export function flattenGamma(book: Book, m: MarketState, tenorT: number, costs: CostModel = ZERO_COSTS): Book {
  const netGamma = bookGreeksRaw(book, m).gamma
  const K = m.spot
  const sigma = volForStrike(m, K, tenorT)
  const legGamma = rawGreeks({ S: m.spot, K, T: tenorT, r: m.r, q: m.q, sigma }, 'call').gamma
  if (legGamma < 1e-12) return book
  const need = -netGamma / legGamma
  if (Math.abs(need) < 1e-6) return book
  return tradeOption(book, { type: 'call', side: need >= 0 ? 'long' : 'short', quantity: Math.abs(need), K, T: tenorT }, m, costs)
}

function zero(): RawGreeks {
  return { price: 0, delta: 0, gamma: 0, vega: 0, theta: 0, rho: 0, vanna: 0, volga: 0, charm: 0, speed: 0, color: 0 }
}
