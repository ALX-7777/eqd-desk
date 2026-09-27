/**
 * Central finite-difference harness for validating analytic greeks.
 *
 * Every analytic greek is checked against a central-difference bump of the
 * pricer here. Central differences are O(h²) accurate; for cross- and
 * third-derivatives we use slightly larger steps to keep roundoff in check and
 * loosen the tolerance accordingly (see greeks.test.ts).
 *
 * This file is a TEST HELPER (not a *.test.ts), so it runs no tests itself.
 */

import { expect } from 'vitest'
import { price } from '../bsm'
import type { BsmInputs, OptionType } from '../types'

type Var = 'S' | 'sigma' | 'T' | 'r'

function bump(i: BsmInputs, v: Var, delta: number): BsmInputs {
  return { ...i, [v]: i[v] + delta }
}

/** Central first derivative ∂P/∂v. */
export function central1(i: BsmInputs, type: OptionType, v: Var, h: number): number {
  return (price(bump(i, v, h), type) - price(bump(i, v, -h), type)) / (2 * h)
}

/** Central second derivative ∂²P/∂v². */
export function central2(i: BsmInputs, type: OptionType, v: Var, h: number): number {
  const up = price(bump(i, v, h), type)
  const mid = price(i, type)
  const dn = price(bump(i, v, -h), type)
  return (up - 2 * mid + dn) / (h * h)
}

/** Central third derivative ∂³P/∂v³ (symmetric 4-point stencil). */
export function central3(i: BsmInputs, type: OptionType, v: Var, h: number): number {
  const u2 = price(bump(i, v, 2 * h), type)
  const u1 = price(bump(i, v, h), type)
  const d1 = price(bump(i, v, -h), type)
  const d2 = price(bump(i, v, -2 * h), type)
  return (u2 - 2 * u1 + 2 * d1 - d2) / (2 * h * h * h)
}

/** Mixed second derivative ∂²P/∂a∂b (4-point cross stencil). */
export function cross2(
  i: BsmInputs,
  type: OptionType,
  a: Var,
  ha: number,
  b: Var,
  hb: number,
): number {
  const pp = price(bump(bump(i, a, ha), b, hb), type)
  const pm = price(bump(bump(i, a, ha), b, -hb), type)
  const mp = price(bump(bump(i, a, -ha), b, hb), type)
  const mm = price(bump(bump(i, a, -ha), b, -hb), type)
  return (pp - pm - mp + mm) / (4 * ha * hb)
}

/**
 * Finite-difference estimates of every greek, with bump sizes chosen to beat
 * the analytic value comfortably. Time greeks carry the −∂/∂T sign (= ∂/∂t).
 */
export const fd = {
  delta: (i: BsmInputs, type: OptionType) => central1(i, type, 'S', 1e-4 * i.S),
  vega: (i: BsmInputs, type: OptionType) => central1(i, type, 'sigma', 1e-4),
  rho: (i: BsmInputs, type: OptionType) => central1(i, type, 'r', 1e-6),
  theta: (i: BsmInputs, type: OptionType) => -central1(i, type, 'T', 1e-5),
  gamma: (i: BsmInputs, type: OptionType) => central2(i, type, 'S', 1e-3 * i.S),
  volga: (i: BsmInputs, type: OptionType) => central2(i, type, 'sigma', 1e-3),
  vanna: (i: BsmInputs, type: OptionType) => cross2(i, type, 'S', 1e-3 * i.S, 'sigma', 1e-3),
  charm: (i: BsmInputs, type: OptionType) => -cross2(i, type, 'S', 1e-3 * i.S, 'T', 1e-5),
  speed: (i: BsmInputs, type: OptionType) => central3(i, type, 'S', 5e-3 * i.S),
  color: (i: BsmInputs, type: OptionType) => {
    const hS = 1e-2 * i.S
    const hT = 1e-3
    const gammaAt = (Tval: number) => central2({ ...i, T: Tval }, type, 'S', hS)
    return -(gammaAt(i.T + hT) - gammaAt(i.T - hT)) / (2 * hT)
  },
}

/**
 * Assert `actual ≈ expected` with a mixed absolute+relative tolerance so that
 * legitimately near-zero greeks don't trip a pure-relative check.
 *   pass iff |actual − expected| ≤ atol + rtol·|expected|
 */
export function expectClose(
  actual: number,
  expected: number,
  rtol = 1e-4,
  atol = 1e-7,
  label = '',
): void {
  const diff = Math.abs(actual - expected)
  const bound = atol + rtol * Math.abs(expected)
  expect(
    diff <= bound,
    `${label} expected ${actual} ≈ ${expected} (|Δ|=${diff.toExponential(3)} > ${bound.toExponential(3)})`,
  ).toBe(true)
}
