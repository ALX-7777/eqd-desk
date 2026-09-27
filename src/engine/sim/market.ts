/**
 * Simulated market for the trading simulator. A GBM spot path with the ATM vol
 * moving AGAINST spot (the leverage effect) plus mild mean-reversion and
 * vol-of-vol noise. The book is priced off this single ATM vol — a flat surface
 * that shifts — which keeps the P&L attribution clean while still letting spot
 * and vol co-move so vanna bites.
 *
 * The step is written behind a small interface so a Heston-style spot+vol process
 * can drop in later without touching the rest of the simulator.
 */

import { mulberry32, makeNormal } from '../exotics/mc'

export interface MarketState {
  /** Elapsed time in years (the clock). */
  t: number
  spot: number
  /** ATM implied vol (at the forward); the level the whole surface hangs off. */
  atmVol: number
  r: number
  q: number
  /** Skew slope in log-moneyness (≤0 for equity skew). Absent ⇒ flat surface. */
  skewSlope?: number
  /** Smile curvature in log-moneyness. Absent ⇒ flat surface. */
  skewCurv?: number
}

/**
 * Implied vol for a strike under the current market — a quadratic skew in
 * log-moneyness around the forward, anchored to the ATM level. The ATM level
 * moves with spot (leverage), and the whole surface shifts with it, so a strike's
 * vol responds both to the ATM move and to its moneyness changing. Flat when the
 * skew params are absent (keeps the simpler tests untouched).
 */
export function volForStrike(market: MarketState, K: number, T: number): number {
  const slope = market.skewSlope ?? 0
  const curv = market.skewCurv ?? 0
  if (slope === 0 && curv === 0) return Math.min(VOL_CAP, Math.max(VOL_FLOOR, market.atmVol))
  const F = market.spot * Math.exp((market.r - market.q) * Math.max(T, 1e-6))
  const k = Math.log(K / F)
  return Math.min(VOL_CAP, Math.max(VOL_FLOOR, market.atmVol + slope * k + curv * k * k))
}

export interface SimParams {
  /** Real-world spot drift (default 0 — no directional edge). */
  drift: number
  /** Leverage: dVol ≈ −leverage·(dS/S). ~1 ⇒ a −1% move lifts vol ~1 point. */
  leverage: number
  /** Mean-reversion speed of vol back to baseVol. */
  volMeanRev: number
  /** Long-run vol level. */
  baseVol: number
  /** Vol-of-vol (idiosyncratic vol noise). */
  volOfVol: number
  /** Step size in years (1/252 ≈ one trading day). */
  dt: number
}

export interface StepResult {
  state: MarketState
  /** Change in spot over the step. */
  dS: number
  /** Change in ATM vol over the step. */
  dVol: number
  /** Spot return over the step (dS/S). */
  spotReturn: number
}

export const DEFAULT_SIM_PARAMS: SimParams = {
  drift: 0,
  leverage: 1.0,
  volMeanRev: 3.0,
  baseVol: 0.15,
  volOfVol: 0.6,
  dt: 1 / 252,
}

export const VOL_FLOOR = 0.05
export const VOL_CAP = 1.2

/** A pluggable one-step market process. GBM+leverage is the default. */
export interface MarketProcess {
  step(state: MarketState, params: SimParams, normal: () => number): StepResult
}

/** GBM spot with leverage-linked vol. */
export const gbmLeverageProcess: MarketProcess = {
  step(state, params, normal) {
    const z1 = normal()
    const z2 = normal()
    const sigma = state.atmVol
    const ret = (params.drift - 0.5 * sigma * sigma) * params.dt + sigma * Math.sqrt(params.dt) * z1
    const newSpot = state.spot * Math.exp(ret)
    const spotReturn = newSpot / state.spot - 1

    let newVol =
      state.atmVol -
      params.leverage * spotReturn +
      params.volMeanRev * (params.baseVol - state.atmVol) * params.dt +
      params.volOfVol * Math.sqrt(params.dt) * z2
    newVol = Math.min(VOL_CAP, Math.max(VOL_FLOOR, newVol))

    return {
      state: {
        t: state.t + params.dt,
        spot: newSpot,
        atmVol: newVol,
        r: state.r,
        q: state.q,
        skewSlope: state.skewSlope,
        skewCurv: state.skewCurv,
      },
      dS: newSpot - state.spot,
      dVol: newVol - state.atmVol,
      spotReturn,
    }
  },
}

/**
 * A small driver that owns a seeded RNG so a whole session is reproducible.
 * Call `next()` to advance one step.
 */
export class MarketSimulator {
  state: MarketState
  private params: SimParams
  private process: MarketProcess
  private normal: () => number

  constructor(
    initial: MarketState,
    params: SimParams = DEFAULT_SIM_PARAMS,
    seed = 0x5eed,
    process: MarketProcess = gbmLeverageProcess,
  ) {
    this.state = initial
    this.params = params
    this.process = process
    this.normal = makeNormal(mulberry32(seed))
  }

  next(): StepResult {
    const res = this.process.step(this.state, this.params, this.normal)
    this.state = res.state
    return res
  }
}

/** Annualised realised vol of a spot path (from log returns), or null if too short. */
export function realisedVol(spots: number[], dt: number): number | null {
  if (spots.length < 3) return null
  let sum = 0
  let sumSq = 0
  let n = 0
  for (let i = 1; i < spots.length; i++) {
    const lr = Math.log(spots[i] / spots[i - 1])
    sum += lr
    sumSq += lr * lr
    n++
  }
  const mean = sum / n
  const variance = sumSq / n - mean * mean
  return Math.sqrt(Math.max(variance, 0) / dt)
}
