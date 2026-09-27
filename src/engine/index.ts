/**
 * Public surface of the pricing/greeks engine. UI code imports from here.
 *
 *   import { analyzeOption } from '@/engine'
 *   const { raw, reported } = analyzeOption({ S, K, T, r, q, sigma }, 'call')
 */

export * from './types'
export * from './mathUtils'
export * from './bsm'
export * from './greeks'
export * from './reporting'
export * from './strategy'
export * from './presets'
export * from './exotics'
export * from './sim'

import { rawGreeks } from './greeks'
import { toReported } from './reporting'
import type { BsmInputs, OptionType, OptionAnalysis } from './types'

/**
 * One-call analysis: price + all greeks in both raw and reported units.
 * Computes the BSM core once internally.
 */
export function analyzeOption(inputs: BsmInputs, type: OptionType): OptionAnalysis {
  const raw = rawGreeks(inputs, type)
  return { inputs, type, raw, reported: toReported(raw) }
}
