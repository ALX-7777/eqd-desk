/**
 * Client RFQs. A request can be a single vanilla or a multi-leg STRUCTURE
 * (straddle / strangle / risk-reversal / vertical), reusing the Phase-2 preset
 * builder for the leg geometry. `legs` describe the package as the CLIENT would
 * hold it if they BUY it; `clientSide` says whether they buy or sell the package.
 */

import type { OptionType } from '../types'
import { buildPreset, type PresetName } from '../presets'

export type ClientSide = 'buy' | 'sell'

export interface RfqLeg {
  type: OptionType
  side: 'long' | 'short'
  /** Per-package ratio (e.g. 2 for a butterfly body). */
  ratio: number
  K: number
  T: number
}

export interface RFQ {
  id: number
  /** Display label, e.g. "Call", "Risk reversal". */
  label: string
  legs: RfqLeg[]
  /** Number of packages. */
  size: number
  clientSide: ClientSide
  /** Day the RFQ arrived (for expiry in auto-flow mode). */
  bornDay: number
}

const EXPIRIES = [1 / 12, 0.25, 0.5, 1]
const SIZES = [10, 25, 50, 100]

type StructKind = 'single-call' | 'single-put' | PresetName
const STRUCTURES: { name: StructKind; label: string; weight: number }[] = [
  { name: 'single-call', label: 'Call', weight: 4 },
  { name: 'single-put', label: 'Put', weight: 4 },
  { name: 'straddle', label: 'Straddle', weight: 1 },
  { name: 'strangle', label: 'Strangle', weight: 1 },
  { name: 'risk-reversal', label: 'Risk reversal', weight: 1 },
  { name: 'call-vertical', label: 'Call spread', weight: 1 },
  { name: 'put-vertical', label: 'Put spread', weight: 1 },
]

function pick<T>(arr: T[], u: number): T {
  return arr[Math.min(arr.length - 1, Math.floor(u * arr.length))]
}

function weightedStructure(u: number): { name: StructKind; label: string } {
  const total = STRUCTURES.reduce((a, s) => a + s.weight, 0)
  let r = u * total
  for (const s of STRUCTURES) {
    if (r < s.weight) return s
    r -= s.weight
  }
  return STRUCTURES[0]
}

/** Build a single-vanilla RFQ (also handy in tests). */
export function singleOptionRfq(
  type: OptionType,
  K: number,
  T: number,
  size: number,
  clientSide: ClientSide,
  id: number,
  bornDay = 0,
): RFQ {
  return {
    id,
    label: type === 'call' ? 'Call' : 'Put',
    legs: [{ type, side: 'long', ratio: 1, K, T }],
    size,
    clientSide,
    bornDay,
  }
}

/** Generate a random RFQ (single or structure) around the current spot. */
export function generateRFQ(
  spot: number,
  strikeStep: number,
  rng: () => number,
  id: number,
  day = 0,
): RFQ {
  const struct = weightedStructure(rng())
  const T = pick(EXPIRIES, rng())
  const clientSide: ClientSide = rng() < 0.5 ? 'buy' : 'sell'
  const size = pick(SIZES, rng())

  if (struct.name === 'single-call' || struct.name === 'single-put') {
    const type: OptionType = struct.name === 'single-call' ? 'call' : 'put'
    const offset = (rng() - 0.5) * 0.2
    const K = Math.max(strikeStep, Math.round((spot * (1 + offset)) / strikeStep) * strikeStep)
    return { id, label: struct.label, legs: [{ type, side: 'long', ratio: 1, K, T }], size, clientSide, bornDay: day }
  }

  const widthPct = 0.03 + rng() * 0.05
  const legs: RfqLeg[] = buildPreset(struct.name, { S: spot, baseT: T, widthPct, strikeStep, volFor: () => 0.2 }).map(
    (l) => ({ type: l.type, side: l.side, ratio: l.quantity, K: l.K, T: l.T }),
  )
  return { id, label: struct.label, legs, size, clientSide, bornDay: day }
}
