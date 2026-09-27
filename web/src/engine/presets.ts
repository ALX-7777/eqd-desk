/**
 * Standard index-desk structures, built relative to spot. Pure: the caller
 * passes a `volFor(K, T)` provider (the vol surface) so each leg is seeded with
 * a skew-aware implied vol while the engine keeps zero data dependency.
 */

import type { Leg, LegSide } from './strategy'
import type { OptionType } from './types'

export type PresetName =
  | 'call-vertical'
  | 'put-vertical'
  | 'straddle'
  | 'strangle'
  | 'risk-reversal'
  | 'butterfly'
  | 'iron-condor'
  | 'calendar'

export const PRESETS: { name: PresetName; label: string }[] = [
  { name: 'call-vertical', label: 'Bull call spread' },
  { name: 'put-vertical', label: 'Bear put spread' },
  { name: 'straddle', label: 'Straddle' },
  { name: 'strangle', label: 'Strangle' },
  { name: 'risk-reversal', label: 'Risk reversal' },
  { name: 'butterfly', label: 'Butterfly' },
  { name: 'iron-condor', label: 'Iron condor' },
  { name: 'calendar', label: 'Calendar' },
]

export interface PresetParams {
  /** Spot to centre the structure on. */
  S: number
  /** Base tenor (years) for the front/only expiry. */
  baseT: number
  /** Wing width as a fraction of spot (e.g. 0.05 = 5%). */
  widthPct: number
  /** Strike rounding step. */
  strikeStep: number
  /** Implied vol provider, typically `surface.getVol`. */
  volFor: (K: number, T: number) => number
}

function roundTo(x: number, step: number): number {
  return Math.round(x / step) * step
}

export function buildPreset(name: PresetName, p: PresetParams): Leg[] {
  const { S, baseT, widthPct, strikeStep, volFor } = p
  const atm = roundTo(S, strikeStep)
  const w = Math.max(strikeStep, roundTo(S * widthPct, strikeStep))
  const backT = baseT + 60 / 365 // ~2 months further out, for calendars

  let i = 0
  const leg = (
    type: OptionType,
    side: LegSide,
    K: number,
    T: number,
    quantity = 1,
  ): Leg => ({
    id: `${name}-${i++}`,
    type,
    side,
    quantity,
    K,
    T,
    sigma: volFor(K, T),
  })

  switch (name) {
    case 'call-vertical':
      return [leg('call', 'long', atm, baseT), leg('call', 'short', atm + w, baseT)]
    case 'put-vertical':
      return [leg('put', 'long', atm, baseT), leg('put', 'short', atm - w, baseT)]
    case 'straddle':
      return [leg('call', 'long', atm, baseT), leg('put', 'long', atm, baseT)]
    case 'strangle':
      return [leg('put', 'long', atm - w, baseT), leg('call', 'long', atm + w, baseT)]
    case 'risk-reversal':
      return [leg('put', 'short', atm - w, baseT), leg('call', 'long', atm + w, baseT)]
    case 'butterfly':
      return [
        leg('call', 'long', atm - w, baseT),
        leg('call', 'short', atm, baseT, 2),
        leg('call', 'long', atm + w, baseT),
      ]
    case 'iron-condor':
      return [
        leg('put', 'long', atm - 2 * w, baseT),
        leg('put', 'short', atm - w, baseT),
        leg('call', 'short', atm + w, baseT),
        leg('call', 'long', atm + 2 * w, baseT),
      ]
    case 'calendar':
      return [leg('call', 'short', atm, baseT), leg('call', 'long', atm, backT)]
    default:
      return []
  }
}
