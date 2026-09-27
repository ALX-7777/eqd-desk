/**
 * Reporting layer — the ONLY place that converts raw mathematical greeks into
 * conventional desk units. Keeping every scale factor here means the rest of the
 * engine stays unit-pure and trivially finite-difference testable, and the UI
 * has one labelled source of truth for units.
 *
 * Conventions (see WORKLOG for the rationale of each):
 *   vega  ÷100    — per 1 vol point  (σ moves 0.01)
 *   rho   ÷100    — per 1 rate point (r moves 0.01)
 *   theta ÷365    — per calendar day
 *   vanna ÷100    — Δdelta per 1 vol point
 *   volga ÷10000  — change in the (per-vol-point) vega, per 1 vol point
 *   charm ÷365    — delta decay per calendar day
 *   color ÷365    — gamma decay per calendar day
 *   delta, gamma, speed, price — unchanged (already in natural desk units)
 */

import type { RawGreeks, ReportedGreeks } from './types'

/** Display metadata for one greek (for UI labels and education panels). */
export interface GreekUnit {
  /** Short display name. */
  label: string
  /** Human-readable reporting unit. */
  unit: string
  /** How the raw partial maps to the reported number. */
  scaleNote: string
}

/** Per-greek display metadata, keyed by the {@link RawGreeks} field name. */
export const GREEK_UNITS: Record<keyof RawGreeks, GreekUnit> = {
  price: { label: 'Price', unit: 'premium', scaleNote: 'raw' },
  delta: { label: 'Delta', unit: 'per $1 spot', scaleNote: 'raw' },
  gamma: { label: 'Gamma', unit: 'Δdelta per $1 spot', scaleNote: 'raw' },
  vega: { label: 'Vega', unit: 'per 1 vol pt', scaleNote: '÷100' },
  theta: { label: 'Theta', unit: 'per day', scaleNote: '÷365' },
  rho: { label: 'Rho', unit: 'per 1 rate pt', scaleNote: '÷100' },
  vanna: { label: 'Vanna', unit: 'Δdelta per 1 vol pt', scaleNote: '÷100' },
  volga: { label: 'Volga', unit: 'Δvega per 1 vol pt', scaleNote: '÷10000' },
  charm: { label: 'Charm', unit: 'Δdelta per day', scaleNote: '÷365' },
  speed: { label: 'Speed', unit: 'Δgamma per $1 spot', scaleNote: 'raw' },
  color: { label: 'Color', unit: 'Δgamma per day', scaleNote: '÷365' },
}

/** Convert raw greeks to conventional desk-reported units. */
export function toReported(raw: RawGreeks): ReportedGreeks {
  return {
    price: raw.price,
    delta: raw.delta,
    gamma: raw.gamma,
    vega: raw.vega / 100,
    theta: raw.theta / 365,
    rho: raw.rho / 100,
    vanna: raw.vanna / 100,
    volga: raw.volga / 10000,
    charm: raw.charm / 365,
    speed: raw.speed,
    color: raw.color / 365,
  }
}
