/**
 * Strategy / position engine (Phase 2). A position is a list of vanilla legs;
 * everything here just COMPOSES the Phase-1 pricer and greeks — aggregate value
 * and greeks are the signed-quantity-weighted sum of the per-leg values, which
 * keeps the position math trivially correct (and FD-validated at the position
 * level in strategy.test.ts).
 *
 * Shared market params (S, r, q) live on the position; each leg carries its own
 * strike, expiry and vol (seeded from the surface so skew/term-structure are
 * baked in). Multi-expiry structures (calendars) are supported: payoff is
 * evaluated at the FRONT expiry, valuing not-yet-expired legs with their
 * remaining maturity.
 */

import { rawGreeks } from './greeks'
import { price } from './bsm'
import { toReported } from './reporting'
import type { BsmInputs, OptionType, RawGreeks, ReportedGreeks } from './types'

export type LegSide = 'long' | 'short'

/** One vanilla leg of a structure. */
export interface Leg {
  id: string
  type: OptionType
  side: LegSide
  /** Number of contracts (positive); sign comes from `side`. */
  quantity: number
  K: number
  /** Time to expiry in years. */
  T: number
  /** Implied vol for this leg (decimal), typically seeded from the surface. */
  sigma: number
}

/** Market parameters shared by every leg of a position. */
export interface MarketParams {
  S: number
  r: number
  q: number
}

/** Per-leg breakdown returned alongside the aggregate. */
export interface LegAnalysis {
  leg: Leg
  inputs: BsmInputs
  /** Signed quantity = +qty (long) / −qty (short). */
  signedQty: number
  /** Per-unit (single-contract) price + greeks, raw units. */
  unit: RawGreeks
}

/** Aggregate analysis of a whole position. */
export interface PositionAnalysis {
  /** Net premium (signed: positive = the structure costs you / is a debit). */
  price: number
  raw: RawGreeks
  reported: ReportedGreeks
  legs: LegAnalysis[]
}

const GREEK_FIELDS: (keyof RawGreeks)[] = [
  'price',
  'delta',
  'gamma',
  'vega',
  'theta',
  'rho',
  'vanna',
  'volga',
  'charm',
  'speed',
  'color',
]

function zeroGreeks(): RawGreeks {
  return {
    price: 0,
    delta: 0,
    gamma: 0,
    vega: 0,
    theta: 0,
    rho: 0,
    vanna: 0,
    volga: 0,
    charm: 0,
    speed: 0,
    color: 0,
  }
}

/** Signed quantity of a leg (+ long, − short). */
export function signedQty(leg: Leg): number {
  return (leg.side === 'long' ? 1 : -1) * leg.quantity
}

/** BSM inputs for a leg under the shared market params. */
export function legInputs(leg: Leg, m: MarketParams): BsmInputs {
  return { S: m.S, K: leg.K, T: leg.T, r: m.r, q: m.q, sigma: leg.sigma }
}

/**
 * Aggregate price + greeks for a position: Σ signedQty · (per-unit greek).
 * Greeks at different expiries sum directly — they are all sensitivities with
 * respect to the same underlying S, r, q.
 */
export function analyzePosition(legs: Leg[], m: MarketParams): PositionAnalysis {
  const agg = zeroGreeks()
  const legAnalyses: LegAnalysis[] = legs.map((leg) => {
    const inputs = legInputs(leg, m)
    const unit = rawGreeks(inputs, leg.type)
    const k = signedQty(leg)
    for (const f of GREEK_FIELDS) agg[f] += k * unit[f]
    return { leg, inputs, signedQty: k, unit }
  })
  return { price: agg.price, raw: agg, reported: toReported(agg), legs: legAnalyses }
}

/** The earliest expiry among the legs (the "front" expiry). 0 for an empty list. */
export function frontExpiry(legs: Leg[]): number {
  if (legs.length === 0) return 0
  return legs.reduce((m, l) => Math.min(m, l.T), Infinity)
}

/** Intrinsic value of a single option at terminal spot. */
function intrinsic(type: OptionType, K: number, S: number): number {
  return type === 'call' ? Math.max(S - K, 0) : Math.max(K - S, 0)
}

/**
 * Value of one leg at terminal spot `S` evaluated at calendar time `atT` (years
 * from now). Legs that have expired by `atT` contribute intrinsic value; legs
 * still alive are priced with their remaining maturity. Signed by side/quantity.
 */
export function legValueAt(leg: Leg, S: number, atT: number, m: MarketParams): number {
  const remaining = leg.T - atT
  const k = signedQty(leg)
  if (remaining <= 1e-9) {
    return k * intrinsic(leg.type, leg.K, S)
  }
  const v = price({ S, K: leg.K, T: remaining, r: m.r, q: m.q, sigma: leg.sigma }, leg.type)
  return k * v
}

/** Position value at terminal spot `S`, evaluated at calendar time `atT`. */
export function positionValueAt(legs: Leg[], S: number, atT: number, m: MarketParams): number {
  let v = 0
  for (const leg of legs) v += legValueAt(leg, S, atT, m)
  return v
}

/** Net premium of the position at the current market (debit positive). */
export function positionPremium(legs: Leg[], m: MarketParams): number {
  return positionValueAt(legs, m.S, 0, m)
}

export interface PayoffPoint {
  /** Terminal spot. */
  S: number
  /** Profit/loss at the front expiry: value-at-front-expiry − net premium paid now. */
  expiryPnl: number
  /** Profit/loss "now" (mark-to-market vs spot, today): value-now − net premium. */
  nowPnl: number
}

/**
 * Sample the P&L profile vs terminal spot. `expiryPnl` is the classic payoff
 * diagram (evaluated at the front expiry so calendars render correctly);
 * `nowPnl` is the smooth current mark-to-market. Both are net of the premium
 * paid today, so they cross zero at the break-evens.
 */
export function payoffProfile(
  legs: Leg[],
  m: MarketParams,
  sLo: number,
  sHi: number,
  n = 120,
): PayoffPoint[] {
  const premium = positionPremium(legs, m)
  const atT = frontExpiry(legs)
  const pts: PayoffPoint[] = []
  for (let i = 0; i <= n; i++) {
    const S = sLo + ((sHi - sLo) * i) / n
    pts.push({
      S,
      expiryPnl: positionValueAt(legs, S, atT, m) - premium,
      nowPnl: positionValueAt(legs, S, 0, m) - premium,
    })
  }
  return pts
}
