/**
 * Binary (digital) options. Cash-or-nothing pays a fixed cash amount if the
 * option finishes in the money; asset-or-nothing pays the asset. Closed form
 * under BSM with carry b = r − q.
 *
 *   d2 = (ln(S/K) + (r − q − σ²/2)·T) / (σ√T)
 *   cash-or-nothing call  = Q·e^(−rT)·N(d2)
 *   cash-or-nothing put   = Q·e^(−rT)·N(−d2)
 *   asset-or-nothing call = S·e^(−qT)·N(d1),  d1 = d2 + σ√T
 *
 * Identity (tested): vanilla call = asset-or-nothing call − K · cash-or-nothing
 * call(Q=1). The digital is the limit of a tight call spread — see
 * `callSpreadReplication` — which is exactly why it is un-hedgeable at expiry
 * (the replicating spread needs infinite size as its width → 0): that is the
 * digital's pin risk.
 */

import { normCdf } from '../mathUtils'
import { price as vanillaPrice } from '../bsm'
import type { OptionType } from '../types'
import { numericGreeks, type ExoticGreeks } from './numericGreeks'

const T_FLOOR = 1e-8
const SIGMA_FLOOR = 1e-8

export interface DigitalInputs {
  S: number
  K: number
  T: number
  r: number
  q: number
  sigma: number
  type: OptionType
  /** Fixed cash payout Q if the option finishes in the money. */
  cash: number
}

function d1d2(S: number, K: number, T: number, r: number, q: number, sigma: number) {
  const Teff = Math.max(T, T_FLOOR)
  const sig = Math.max(sigma, SIGMA_FLOOR)
  const volSqrtT = sig * Math.sqrt(Teff)
  const d2 = (Math.log(S / K) + (r - q - 0.5 * sig * sig) * Teff) / volSqrtT
  return { d1: d2 + volSqrtT, d2 }
}

/** Cash-or-nothing price: pays `cash` (Q) if in the money at expiry. */
export function cashOrNothingPrice(i: DigitalInputs): number {
  const { d2 } = d1d2(i.S, i.K, i.T, i.r, i.q, i.sigma)
  const df = Math.exp(-i.r * Math.max(i.T, T_FLOOR))
  return i.type === 'call' ? i.cash * df * normCdf(d2) : i.cash * df * normCdf(-d2)
}

/** Asset-or-nothing price: pays the asset (S_T) if in the money at expiry. */
export function assetOrNothingPrice(i: DigitalInputs): number {
  const { d1 } = d1d2(i.S, i.K, i.T, i.r, i.q, i.sigma)
  const dfq = Math.exp(-i.q * Math.max(i.T, T_FLOOR))
  return i.type === 'call' ? i.S * dfq * normCdf(d1) : i.S * dfq * normCdf(-d1)
}

/** Greeks of the cash-or-nothing digital, by bumping (note the delta/gamma spike near the strike). */
export function digitalGreeks(i: DigitalInputs): ExoticGreeks {
  const px = (S: number, sigma: number, T: number, r: number) =>
    cashOrNothingPrice({ ...i, S, sigma, T, r })
  return numericGreeks(px, i.S, i.sigma, i.T, i.r)
}

/**
 * Price of the tight CALL-SPREAD that replicates a cash-or-nothing digital with
 * the given spread width Δ (strike units): for a call, long (Q/Δ) calls at K−Δ/2
 * and short (Q/Δ) at K+Δ/2. As Δ → 0 this converges to the digital price; the
 * (Q/Δ) size is the un-hedgeable bit at expiry.
 */
export function callSpreadReplication(i: DigitalInputs, width: number): number {
  const w = Math.max(width, 1e-9)
  const n = i.cash / w
  if (i.type === 'call') {
    const lo = vanillaPrice({ S: i.S, K: i.K - w / 2, T: i.T, r: i.r, q: i.q, sigma: i.sigma }, 'call')
    const hi = vanillaPrice({ S: i.S, K: i.K + w / 2, T: i.T, r: i.r, q: i.q, sigma: i.sigma }, 'call')
    return n * (lo - hi)
  }
  // put digital ≈ long (Q/Δ) puts at K+Δ/2, short (Q/Δ) puts at K−Δ/2
  const hi = vanillaPrice({ S: i.S, K: i.K + w / 2, T: i.T, r: i.r, q: i.q, sigma: i.sigma }, 'put')
  const lo = vanillaPrice({ S: i.S, K: i.K - w / 2, T: i.T, r: i.r, q: i.q, sigma: i.sigma }, 'put')
  return n * (hi - lo)
}
