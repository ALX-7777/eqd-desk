/**
 * Phase-1 implied-vol surface built from the seed snapshot.
 *
 * The interface (`getVol(strike, expiry)`) is the contract later phases depend
 * on; Phase 4 will swap in a surface that evolves with the simulated spot path
 * (the leverage effect) without touching the engine. For now it is STATIC:
 *  - ATM level varies with tenor via linear interpolation of the term structure;
 *  - the skew shape (a quadratic in log-moneyness, fit near 30 days) is applied
 *    at every tenor. Holding the skew shape constant across T is a deliberate
 *    Phase-1 simplification — enough to make skew and the cross-greeks visible.
 *
 * Dependency direction: this imports the engine's `BsmInputs` type only; the
 * engine never imports this module.
 */

import { snapshot } from './snapshot'
import type { MarketSnapshot } from './snapshot'

export interface VolSurface {
  /** Spot the surface is centred on. */
  readonly spot: number
  /** ATM implied vol at tenor T (years), interpolated from the term structure. */
  atmVol(expiry: number): number
  /** Implied vol for strike K at tenor T (years) via the log-moneyness skew. */
  getVol(strike: number, expiry: number): number
}

/** Floor so the surface never returns a non-positive vol in the deep wings. */
export const VOL_FLOOR = 0.01

/** Linear interpolation (with flat extrapolation) of the ATM term structure. */
function interpAtm(s: MarketSnapshot, T: number): number {
  const ts = s.term_structure
  if (ts.length === 0) return s.atm_vol_30d
  if (T <= ts[0].t) return ts[0].atm_iv
  const last = ts[ts.length - 1]
  if (T >= last.t) return last.atm_iv
  for (let i = 1; i < ts.length; i++) {
    const a = ts[i - 1]
    const b = ts[i]
    if (T <= b.t) {
      const w = (T - a.t) / (b.t - a.t)
      return a.atm_iv + w * (b.atm_iv - a.atm_iv)
    }
  }
  return s.atm_vol_30d
}

/** Build a vol surface from a snapshot. */
export function buildSurface(s: MarketSnapshot = snapshot): VolSurface {
  const spot = s.spot
  const { slope, curv } = s.skew
  return {
    spot,
    atmVol(T: number): number {
      return Math.max(VOL_FLOOR, interpAtm(s, Math.max(T, 1e-6)))
    },
    getVol(K: number, T: number): number {
      const k = Math.log(K / spot) // log-moneyness
      const atm = interpAtm(s, Math.max(T, 1e-6))
      return Math.max(VOL_FLOOR, atm + slope * k + curv * k * k)
    },
  }
}

/** Default surface built from the committed seed snapshot. */
export const surface: VolSurface = buildSurface()
