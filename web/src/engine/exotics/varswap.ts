/**
 * Variance swap — fair variance via the model-free replication of the log
 * contract by a strip of OTM options weighted 1/K² (Demeterfi–Derman–Kamal–Zou).
 * Splitting the strip at the forward F removes the boundary term:
 *
 *   K_var = (2·e^{rT}/T) · [ Σ_{K<F} (ΔK/K²)·P(K) + Σ_{K≥F} (ΔK/K²)·C(K) ]
 *
 * The fair variance equals −(2/T)·E^Q[ln(S_T/F)] (the log contract); under GBM
 * that is exactly σ², so a flat surface returns σ² (validated in tests). With a
 * real downward skew the strip is overweight low-strike (high-vol) puts, so the
 * fair vol prints ABOVE the ATM vol — the convexity premium that makes VIX (a
 * 30-day variance swap on the S&P) trade rich to ATM.
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
  /** Replication weight ΔK / K². */
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
  /** Forward F = S·e^{(r−q)T}. */
  forward: number
  /** ATM implied vol (at the forward), for comparison. */
  atmVol: number
  /** The replication strip (for plotting the 1/K² contributions). */
  strip: StripPoint[]
}

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
    const weight = dK / (K * K)
    const contribution = weight * optionPrice
    sum += contribution
    strip.push({ K, weight, optionPrice, type: isPut ? 'put' : 'call', contribution })
  }

  const fairVariance = ((2 * Math.exp(i.r * i.T)) / i.T) * sum
  return {
    fairVariance,
    fairVol: Math.sqrt(Math.max(fairVariance, 0)),
    forward: F,
    atmVol: i.volFor(F),
    strip,
  }
}
