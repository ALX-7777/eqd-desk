/**
 * Historical replay — step the market along a REAL past spot/VIX path instead of
 * simulating it. Pure: the history series is supplied by the data layer; this
 * just picks a random window and maps each point to a MarketState (VIX/100 is the
 * ATM implied; the skew shape is carried from config). The date is not exposed —
 * you trade an undisclosed slice of history.
 */

import type { MarketState } from './market'

export interface HistoryPoint {
  date: string
  spot: number
  vix: number
}

export interface ReplayWindow {
  points: HistoryPoint[]
  /** Index into the full series — for an optional post-hoc reveal. */
  startIndex: number
}

export interface ReplayBase {
  r: number
  q: number
  skewSlope: number
  skewCurv: number
  /** Step size in years (1/252 = one trading day). */
  dt: number
}

/** Pick a random window of `length` steps (length+1 points) from the series. */
export function pickWindow(series: HistoryPoint[], length: number, u: number): ReplayWindow {
  const maxStart = Math.max(0, series.length - length - 1)
  const startIndex = Math.min(maxStart, Math.floor(u * (maxStart + 1)))
  return { points: series.slice(startIndex, startIndex + length + 1), startIndex }
}

/** Number of steps available in a window. */
export function windowSteps(win: ReplayWindow): number {
  return Math.max(0, win.points.length - 1)
}

/** Market state at step `i` of a replay window. */
export function replayState(win: ReplayWindow, i: number, base: ReplayBase): MarketState {
  const idx = Math.max(0, Math.min(i, win.points.length - 1))
  const p = win.points[idx]
  return {
    t: idx * base.dt,
    spot: p.spot,
    atmVol: Math.max(0.05, p.vix / 100),
    r: base.r,
    q: base.q,
    skewSlope: base.skewSlope,
    skewCurv: base.skewCurv,
  }
}
