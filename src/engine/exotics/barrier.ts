/**
 * Single-barrier European options (continuously monitored), Reiner–Rubinstein /
 * Merton closed forms, zero rebate. Carry b = r − q.
 *
 * Building blocks A, B, C, D (Haug) with φ = +1 call / −1 put and η = +1 down /
 * −1 up. A is exactly the vanilla price, so knock-in + knock-out = vanilla holds
 * by construction; the MC cross-check (in tests) validates the A/B/C/D formulas
 * and the in/out table itself.
 *
 * Teaching point: a knock-out's value (and its delta) collapse to zero AT the
 * barrier, so gamma explodes there — the barrier is where the hedge is hardest.
 */

import { normCdf } from '../mathUtils'
import { price as vanillaPrice } from '../bsm'
import type { OptionType } from '../types'
import { numericGreeks, type ExoticGreeks } from './numericGreeks'

const T_FLOOR = 1e-8
const SIGMA_FLOOR = 1e-8

export type BarrierKind = 'down-in' | 'down-out' | 'up-in' | 'up-out'

export interface BarrierInputs {
  S: number
  K: number
  T: number
  r: number
  q: number
  sigma: number
  type: OptionType
  /** Barrier level H. */
  H: number
  kind: BarrierKind
}

interface ABCD {
  A: number
  B: number
  C: number
  D: number
}

function abcd(
  S: number,
  K: number,
  H: number,
  T: number,
  r: number,
  q: number,
  sigma: number,
  phi: number,
  eta: number,
): ABCD {
  const b = r - q
  const sig = Math.max(sigma, SIGMA_FLOOR)
  const Teff = Math.max(T, T_FLOOR)
  const sigT = sig * Math.sqrt(Teff)
  const mu = (b - 0.5 * sig * sig) / (sig * sig)
  const x1 = Math.log(S / K) / sigT + (1 + mu) * sigT
  const x2 = Math.log(S / H) / sigT + (1 + mu) * sigT
  const y1 = Math.log((H * H) / (S * K)) / sigT + (1 + mu) * sigT
  const y2 = Math.log(H / S) / sigT + (1 + mu) * sigT
  const ebrT = Math.exp((b - r) * Teff)
  const erT = Math.exp(-r * Teff)
  const hsP = Math.pow(H / S, 2 * (mu + 1))
  const hsM = Math.pow(H / S, 2 * mu)

  const A =
    phi * S * ebrT * normCdf(phi * x1) - phi * K * erT * normCdf(phi * x1 - phi * sigT)
  const B =
    phi * S * ebrT * normCdf(phi * x2) - phi * K * erT * normCdf(phi * x2 - phi * sigT)
  const C =
    phi * S * ebrT * hsP * normCdf(eta * y1) -
    phi * K * erT * hsM * normCdf(eta * y1 - eta * sigT)
  const D =
    phi * S * ebrT * hsP * normCdf(eta * y2) -
    phi * K * erT * hsM * normCdf(eta * y2 - eta * sigT)
  return { A, B, C, D }
}

/** Price of a single-barrier European option (continuous monitoring, zero rebate). */
export function barrierPrice(i: BarrierInputs): number {
  if (!(i.H > 0)) throw new RangeError(`barrier: H must be > 0 (got ${i.H})`)
  const isCall = i.type === 'call'
  const isDown = i.kind === 'down-in' || i.kind === 'down-out'
  const isOut = i.kind === 'down-out' || i.kind === 'up-out'

  // Already breached? Knock-out is dead; knock-in is just the vanilla from here.
  const breached = isDown ? i.S <= i.H : i.S >= i.H
  if (breached) {
    return isOut ? 0 : vanillaPrice({ S: i.S, K: i.K, T: i.T, r: i.r, q: i.q, sigma: i.sigma }, i.type)
  }

  const phi = isCall ? 1 : -1
  const eta = isDown ? 1 : -1
  const { A, B, C, D } = abcd(i.S, i.K, i.H, i.T, i.r, i.q, i.sigma, phi, eta)
  const KgtH = i.K > i.H

  let v: number
  switch (i.kind) {
    case 'down-in':
      v = isCall ? (KgtH ? C : A - B + D) : KgtH ? B - C + D : A
      break
    case 'up-in':
      v = isCall ? (KgtH ? A : B - C + D) : KgtH ? A - B + D : C
      break
    case 'down-out':
      v = isCall ? (KgtH ? A - C : B - D) : KgtH ? A - B + C - D : 0
      break
    case 'up-out':
      v = isCall ? (KgtH ? 0 : A - B + C - D) : KgtH ? B - D : A - C
      break
  }
  return Math.max(v, 0) // clamp tiny negative numerical noise
}

/** Greeks of a barrier option, by bumping — gamma blows up near the barrier. */
export function barrierGreeks(i: BarrierInputs): ExoticGreeks {
  const px = (S: number, sigma: number, T: number, r: number) =>
    barrierPrice({ ...i, S, sigma, T, r })
  return numericGreeks(px, i.S, i.sigma, i.T, i.r)
}
