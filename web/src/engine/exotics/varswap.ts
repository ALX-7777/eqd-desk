/**
 * Variance swap — fair variance via the model-free replication of the log
 * contract by a strip of OTM options weighted 1/K² (Demeterfi–Derman–Kamal–Zou).
 * Splitting the strip at the forward F removes the boundary term:
 *
 *   K_var = (2·e^{rT}/T) · ∫ Q(K)/K² dK      Q(K) = P(K) for K < F, C(K) for K ≥ F
 *
 * The fair variance equals −(2/T)·E^Q[ln(S_T/F)] (the log contract); under GBM
 * that is exactly σ², so a flat surface returns σ². With a real downward skew
 * the strip is overweight low-strike (high-vol) puts, so the fair vol prints
 * ABOVE the ATM vol — the convexity premium that makes VIX (a 30-day variance
 * swap on the S&P) trade rich to ATM.
 *
 * Discrete strip. On an evenly spaced strike grid (spacing ΔK) the integral over
 * the strip becomes a trapezoid-rule sum (weight ΔK/K², halved at the two end
 * strikes so the sum covers exactly lo…hi), plus one closed-form correction for
 * the kink at the forward:
 *
 *   K_var ≈ (2·e^{rT}/T) · Σ wᵢ·Q(Kᵢ)  −  (ΔK/F)²·B₂(θ)/T      wᵢ = ΔK/Kᵢ² (½ at the ends)
 *   θ = (F − K₀)/ΔK ∈ [0, 1)     K₀ = the grid strike at or just below F
 *   B₂(θ) = θ² − θ + 1/6         (the second Bernoulli polynomial)
 *
 * Why: Q(K)/K² is smooth except at F, where the strip switches from puts to
 * calls and its slope drops by e^{−rT}/F² (put–call parity: C − P = e^{−rT}·(F − K)).
 * An even-grid sum integrates the smooth part almost exactly but mis-counts that
 * kink by (ΔK²/2)·B₂(θ)·e^{−rT}/F² (the Euler–Maclaurin term for a kink θ of the
 * way between two strikes). Left in, the error in variance runs from
 * −(ΔK/F)²/(12T) to +(ΔK/F)²/(6T): negligible at a year, but at 7 days and 5% vol
 * on the default strip it prints 4.80% for a flat 5% smile. The CBOE VIX
 * formula's −(1/T)·(F/K₀ − 1)² term (with the put–call average at K₀) removes the
 * θ-dependent part of the same error; the constant 1/6 is the part it keeps,
 * negligible at listed SPX strike spacing but not on a 400-strike grid from 0.3F
 * to 3F.
 *
 * Truncation. Strikes outside loMult·F … hiMult·F are simply absent, which drops
 * the tails: it matters only at long tenors and high vol (a flat 60% smile at 1
 * year prices ≈59.5% on the default 0.3F–3F strip). A wider strip is not
 * automatically better with a parametric smile whose wings grow without bound (a
 * quadratic in log-moneyness).
 *
 * Pure: the surface is supplied as a `volFor(K)` callback so the engine keeps no
 * data dependency.
 */

import { price as vanillaPrice } from '../bsm'

export interface VarSwapInputs {
  S: number
  T: number
  r: number
  q: number
  /** Implied vol for a given strike (the smile), e.g. surface.getVol(K, T). */
  volFor: (K: number) => number
  /** Low/high strike bounds as multiples of the forward (default 0.3×F … 3×F). */
  loMult?: number
  hiMult?: number
  /** Number of strikes in the replication strip (default 400). */
  nStrikes?: number
}

export interface StripPoint {
  K: number
  /** Replication weight ΔK / K² (half that at the strip's first and last strike). */
  weight: number
  /** OTM option price used at this strike. */
  optionPrice: number
  type: 'call' | 'put'
  /** Weighted contribution to the fair variance (before the 2·e^{rT}/T factor). */
  contribution: number
}

export interface VarSwapResult {
  /** Annualised fair variance. */
  fairVariance: number
  /** Fair volatility = √(fair variance). */
  fairVol: number
  /**
   * The forward-kink correction −(ΔK/F)²·B₂(θ)/T already included in
   * fairVariance (annualised variance; 0 when F lies outside the strip).
   */
  gridCorrection: number
  /** Forward F = S·e^{(r−q)T}. */
  forward: number
  /** ATM implied vol (at the forward), for comparison. */
  atmVol: number
  /** The replication strip (for plotting the 1/K² contributions). */
  strip: StripPoint[]
}

/**
 * Fair variance by the 1/K²-weighted OTM strip (see the module doc). Strikes run
 * evenly from loMult·F to hiMult·F (nStrikes points, spacing ΔK); non-positive
 * strikes are skipped. Each strike prices an OTM vanilla at volFor(K) — a put for
 * K < F, a call for K ≥ F — weighted ΔK/K² (trapezoid rule: half at the first and
 * last grid strike). When F lies inside the strip (lo ≤ F < hi) the forward-kink
 * correction −(ΔK/F)²·B₂(θ)/T is added.
 */
export function priceVarianceSwap(i: VarSwapInputs): VarSwapResult {
  const F = i.S * Math.exp((i.r - i.q) * i.T)
  const lo = (i.loMult ?? 0.3) * F
  const hi = (i.hiMult ?? 3.0) * F
  const n = i.nStrikes ?? 400
  const dK = (hi - lo) / (n - 1)

  const strip: StripPoint[] = []
  let sum = 0
  for (let j = 0; j < n; j++) {
    const K = lo + j * dK
    if (K <= 0) continue
    const isPut = K < F
    const sigma = i.volFor(K)
    const optionPrice = vanillaPrice({ S: i.S, K, T: i.T, r: i.r, q: i.q, sigma }, isPut ? 'put' : 'call')
    const end = j === 0 || j === n - 1 // trapezoid rule: the strip's ends get half a slice
    const weight = (end ? 0.5 * dK : dK) / (K * K)
    const contribution = weight * optionPrice
    sum += contribution
    strip.push({ K, weight, optionPrice, type: isPut ? 'put' : 'call', contribution })
  }

  // Forward-kink correction (module doc): θ = where F sits between its two grid strikes.
  let gridCorrection = 0
  if (n >= 2 && lo <= F && F < hi) {
    let theta = (F - lo) / dK
    theta -= Math.floor(theta)
    const g = dK / F
    gridCorrection = (-(g * g) * (theta * theta - theta + 1 / 6)) / i.T
  }

  const fairVariance = ((2 * Math.exp(i.r * i.T)) / i.T) * sum + gridCorrection
  return {
    fairVariance,
    fairVol: Math.sqrt(Math.max(fairVariance, 0)),
    gridCorrection,
    forward: F,
    atmVol: i.volFor(F),
    strip,
  }
}
