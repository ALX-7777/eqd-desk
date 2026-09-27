/**
 * Phoenix autocallable — a path-dependent structured note, priced by Monte Carlo.
 *
 * On each (evenly-spaced) observation date:
 *   • conditional coupon: if S ≥ couponBarrier·S0, pay the period coupon (plus any
 *     missed coupons, if `memory`); otherwise the coupon is missed (and remembered);
 *   • early redemption: if S ≥ autocallBarrier·S0 (before maturity), the note
 *     redeems at par and stops.
 * At maturity, if not autocalled: par if S ≥ protectionBarrier·S0, else
 * par·(S/S0) — the holder is long the downside below the barrier.
 *
 * Barriers are ABSOLUTE levels set from the initial fixing S0; greeks bump the
 * current spot with those levels fixed (the correct risk view). Teaching point:
 * the price is a path-dependent blend of a yield instrument and a short
 * down-and-in put — early-redemption probability and "expected life" are as
 * important as the price.
 */

import { mulberry32, makeNormal } from './mc'
import { numericGreeks, type ExoticGreeks } from './numericGreeks'

export interface AutocallInputs {
  /** Current spot. */
  S: number
  /** Initial fixing level (sets the absolute barriers). At inception S === S0. */
  S0: number
  sigma: number
  r: number
  q: number
  /** Maturity in years. */
  maturity: number
  /** Number of equally-spaced observation dates. */
  nObs: number
  /** Per-period coupon as a fraction of notional (e.g. 0.02 = 2% per observation). */
  couponRate: number
  /** Early-redemption barrier as a fraction of S0 (e.g. 1.0). */
  autocallBarrier: number
  /** Conditional-coupon barrier as a fraction of S0 (e.g. 0.7). */
  couponBarrier: number
  /** Capital-protection barrier at maturity as a fraction of S0 (e.g. 0.7). */
  protectionBarrier: number
  /** Whether missed coupons accumulate and pay later (snowball / memory). */
  memory: boolean
  /** Notional (par), e.g. 100. */
  notional: number
}

export interface AutocallResult {
  price: number
  /** Monte-Carlo standard error of the price. */
  stderr: number
  /** Probability of early redemption (autocalled before maturity). */
  probAutocall: number
  /** Probability of capital loss at maturity. */
  probCapitalLoss: number
  /** Expected time to redemption (years). */
  expectedLife: number
}

const DEFAULT_PATHS = 20000
const DEFAULT_SEED = 0x9e3779b1

/** Price a Phoenix autocallable by Monte Carlo (seeded → reproducible). */
export function priceAutocall(
  i: AutocallInputs,
  paths: number = DEFAULT_PATHS,
  seed: number = DEFAULT_SEED,
): AutocallResult {
  const normal = makeNormal(mulberry32(seed))
  const dt = i.maturity / i.nObs
  const drift = (i.r - i.q - 0.5 * i.sigma * i.sigma) * dt
  const vol = i.sigma * Math.sqrt(dt)
  const AB = i.autocallBarrier * i.S0
  const CB = i.couponBarrier * i.S0
  const PB = i.protectionBarrier * i.S0
  const N = i.notional

  // Pre-compute discount factors at each observation date.
  const df: number[] = new Array(i.nObs)
  for (let k = 1; k <= i.nObs; k++) df[k - 1] = Math.exp(-i.r * k * dt)

  let sum = 0
  let sum2 = 0
  let nAuto = 0
  let nLoss = 0
  let lifeSum = 0

  for (let p = 0; p < paths; p++) {
    let s = i.S
    let missed = 0
    let pv = 0
    let life = i.maturity

    for (let k = 1; k <= i.nObs; k++) {
      s = s * Math.exp(drift + vol * normal())
      const d = df[k - 1]

      // conditional coupon (with optional memory)
      if (s >= CB) {
        const periods = i.memory ? 1 + missed : 1
        pv += N * i.couponRate * periods * d
        missed = 0
      } else {
        missed += 1
      }

      // early redemption (before maturity)
      if (k < i.nObs && s >= AB) {
        pv += N * d
        nAuto++
        life = k * dt
        break
      }

      // maturity redemption
      if (k === i.nObs) {
        if (s >= PB) {
          pv += N * d
        } else {
          pv += N * (s / i.S0) * d
          nLoss++
        }
        life = i.maturity
      }
    }

    sum += pv
    sum2 += pv * pv
    lifeSum += life
  }

  const price = sum / paths
  const variance = sum2 / paths - price * price
  return {
    price,
    stderr: Math.sqrt(Math.max(variance, 0) / paths),
    probAutocall: nAuto / paths,
    probCapitalLoss: nLoss / paths,
    expectedLife: lifeSum / paths,
  }
}

/**
 * Autocallable greeks by bumping, with common random numbers (fixed seed) so the
 * finite differences are stable. MC greeks are approximate — gamma especially is
 * noisy — but delta/vega read clearly.
 */
export function autocallGreeks(
  i: AutocallInputs,
  paths: number = 40000,
  seed: number = DEFAULT_SEED,
): ExoticGreeks {
  const px = (S: number, sigma: number, T: number, r: number) =>
    priceAutocall({ ...i, S, sigma, maturity: T, r }, paths, seed).price
  return numericGreeks(px, i.S, i.sigma, i.maturity, i.r)
}
