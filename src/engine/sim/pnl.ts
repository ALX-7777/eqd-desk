/**
 * P&L attribution ("explain") for the book over one market step, via the
 * second-order Taylor expansion of the book value in (S, σ, t):
 *
 *   ΔV ≈ Δ·ΔS + ½·Γ·ΔS² + Θ·Δt + vega·Δσ + vanna·ΔS·Δσ + ½·volga·Δσ² + residual
 *
 * Uses RAW greeks (exact partials) at the START of the step; the residual is the
 * actual repriced ΔV minus the explained terms, so the decomposition reconciles
 * exactly. The residual collects third-and-higher order and any vol-path effects
 * — small for small steps, larger across a gap. The underlying hedge sits in the
 * delta term (it folds into the book's net delta).
 */

import { bookValue, type Book } from './book'
import { volForStrike, type MarketState } from './market'
import { rawGreeks } from '../greeks'

export interface PnlAttribution {
  /** Actual mark-to-market change of the (unchanged) book over the step. */
  total: number
  delta: number
  gamma: number
  theta: number
  vega: number
  vanna: number
  volga: number
  /** Actual − explained: third-order and beyond (incl. surface dynamics). */
  residual: number
}

/**
 * Per-leg attribution. Each leg's vol change Δσ comes from the surface
 * (`volForStrike`), so when spot moves both the ATM level AND the leg's moneyness
 * shift — the skew/leverage P&L lands in vega/vanna/volga rather than the
 * residual. Spot greeks (delta/gamma) and theta sum across legs; the underlying
 * hedge contributes only to delta.
 */
export function attribute(book: Book, before: MarketState, after: MarketState): PnlAttribution {
  const dS = after.spot - before.spot
  const dt = after.t - before.t

  let delta = 0
  let gamma = 0
  let theta = 0
  let vega = 0
  let vanna = 0
  let volga = 0

  for (const tr of book.trades) {
    const k = (tr.side === 'long' ? 1 : -1) * tr.quantity
    const Tb = Math.max(tr.expiryTime - before.t, 1e-6)
    const Ta = Math.max(tr.expiryTime - after.t, 1e-6)
    const sigB = volForStrike(before, tr.K, Tb)
    const sigA = volForStrike(after, tr.K, Ta)
    const dSig = sigA - sigB
    const g = rawGreeks({ S: before.spot, K: tr.K, T: Tb, r: before.r, q: before.q, sigma: sigB }, tr.type)
    delta += k * g.delta * dS
    gamma += 0.5 * k * g.gamma * dS * dS
    theta += k * g.theta * dt
    vega += k * g.vega * dSig
    vanna += k * g.vanna * dS * dSig
    volga += 0.5 * k * g.volga * dSig * dSig
  }
  // underlying hedge: pure delta.
  delta += book.underlyingQty * dS

  const total = bookValue(book, after) - bookValue(book, before)
  const explained = delta + gamma + theta + vega + vanna + volga
  return { total, delta, gamma, theta, vega, vanna, volga, residual: total - explained }
}
