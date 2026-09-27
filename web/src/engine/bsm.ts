/**
 * Black–Scholes–Merton pricing for vanilla European options with a continuous
 * dividend yield `q`, implemented from scratch.
 *
 *   d1 = (ln(S/K) + (r − q + σ²/2)·T) / (σ·√T)
 *   d2 = d1 − σ·√T
 *   Call = S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2)
 *   Put  = K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1)
 *
 * All greeks (see greeks.ts) are derived from the same `bsmCore` intermediates,
 * so the pricer and the greeks always share one consistent set of d1/d2 and
 * discount factors.
 */

import { normCdf } from './mathUtils'
import type { BsmInputs, OptionType } from './types'

/**
 * Lower bound applied to T (in years) so the smooth formulas stay finite as an
 * option approaches expiry. ~1e-8 yr ≈ 0.3 ms — far below any meaningful
 * trading granularity, so it never perturbs realistic inputs; it only tames the
 * 1/√T singularity for display at the instant of expiry.
 */
export const T_FLOOR = 1e-8

/**
 * Lower bound applied to σ so we never divide by σ·√T. 1e-8 is negligible vs any
 * real vol; the floored result tends to the discounted-intrinsic limit.
 */
export const SIGMA_FLOOR = 1e-8

/** Shared intermediates computed once and reused by the pricer and every greek. */
export interface BsmCore {
  /** d1 of the BSM formula. */
  d1: number
  /** d2 = d1 − σ√T. */
  d2: number
  /** √T (using the floored T). */
  sqrtT: number
  /** σ·√T (using floored σ and T) — the single guarded denominator. */
  volSqrtT: number
  /** Riskless discount factor e^(−rT). */
  dfR: number
  /** Carry / dividend discount factor e^(−qT). */
  dfQ: number
  /** Effective T after flooring (years). */
  Teff: number
  /** Effective σ after flooring (decimal). */
  sigmaEff: number
}

/**
 * Validate inputs. Non-positive S/K make ln(S/K) undefined, so these are hard
 * errors (programmer / un-validated-UI bugs) rather than silently-clamped values.
 */
export function validateInputs(i: BsmInputs): void {
  if (!(i.S > 0)) throw new RangeError(`BSM: spot S must be > 0 (got ${i.S})`)
  if (!(i.K > 0)) throw new RangeError(`BSM: strike K must be > 0 (got ${i.K})`)
  if (!(i.T >= 0)) throw new RangeError(`BSM: time T must be >= 0 (got ${i.T})`)
  if (!(i.sigma >= 0)) throw new RangeError(`BSM: vol sigma must be >= 0 (got ${i.sigma})`)
  if (!Number.isFinite(i.r)) throw new RangeError(`BSM: rate r must be finite (got ${i.r})`)
  if (!Number.isFinite(i.q)) throw new RangeError(`BSM: dividend q must be finite (got ${i.q})`)
}

/**
 * Compute the shared BSM intermediates (d1, d2, discount factors, guarded
 * denominators). Floors T and σ to keep everything finite at the boundaries.
 */
export function bsmCore(i: BsmInputs): BsmCore {
  validateInputs(i)
  const Teff = Math.max(i.T, T_FLOOR)
  const sigmaEff = Math.max(i.sigma, SIGMA_FLOOR)
  const sqrtT = Math.sqrt(Teff)
  const volSqrtT = sigmaEff * sqrtT
  const dfR = Math.exp(-i.r * Teff)
  const dfQ = Math.exp(-i.q * Teff)
  const d1 = (Math.log(i.S / i.K) + (i.r - i.q + 0.5 * sigmaEff * sigmaEff) * Teff) / volSqrtT
  const d2 = d1 - volSqrtT
  return { d1, d2, sqrtT, volSqrtT, dfR, dfQ, Teff, sigmaEff }
}

/** Call price: S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2). */
export function callPrice(i: BsmInputs): number {
  const { d1, d2, dfR, dfQ } = bsmCore(i)
  return i.S * dfQ * normCdf(d1) - i.K * dfR * normCdf(d2)
}

/** Put price: K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1). */
export function putPrice(i: BsmInputs): number {
  const { d1, d2, dfR, dfQ } = bsmCore(i)
  return i.K * dfR * normCdf(-d2) - i.S * dfQ * normCdf(-d1)
}

/** Price dispatch by option type. */
export function price(i: BsmInputs, type: OptionType): number {
  return type === 'call' ? callPrice(i) : putPrice(i)
}

/**
 * Forward price F = S·e^((r−q)T). The discounted intrinsic on the forward is the
 * σ→0 limit of the BSM price; useful for edge-case tests and intuition.
 */
export function forward(i: BsmInputs): number {
  const Teff = Math.max(i.T, T_FLOOR)
  return i.S * Math.exp((i.r - i.q) * Teff)
}
