import { describe, it, expect } from 'vitest'
import { callPrice, putPrice, price, forward, bsmCore, validateInputs } from '../bsm'
import type { BsmInputs } from '../types'

const canonical: BsmInputs = { S: 100, K: 100, T: 1, r: 0.05, q: 0, sigma: 0.2 }

describe('bsmCore', () => {
  it('computes d1/d2 for the canonical set', () => {
    const c = bsmCore(canonical)
    expect(c.d1).toBeCloseTo(0.35, 12) // (0.05 + 0.02) / 0.2
    expect(c.d2).toBeCloseTo(0.15, 12)
    expect(c.dfR).toBeCloseTo(Math.exp(-0.05), 15)
    expect(c.dfQ).toBe(1)
  })
})

describe('BSM price — reference values', () => {
  it('matches textbook call/put for S=K=100, T=1, r=5%, q=0, σ=20%', () => {
    expect(callPrice(canonical)).toBeCloseTo(10.450583572185565, 6)
    expect(putPrice(canonical)).toBeCloseTo(5.573526022256971, 6)
  })

  it('dispatches by type', () => {
    expect(price(canonical, 'call')).toBe(callPrice(canonical))
    expect(price(canonical, 'put')).toBe(putPrice(canonical))
  })
})

describe('put-call parity: C − P = S·e^(−qT) − K·e^(−rT)', () => {
  const sets: BsmInputs[] = [
    canonical,
    { S: 100, K: 120, T: 0.5, r: 0.03, q: 0.02, sigma: 0.25 },
    { S: 130, K: 100, T: 0.75, r: 0.04, q: 0.015, sigma: 0.18 },
    { S: 50, K: 100, T: 2, r: 0.06, q: 0.01, sigma: 0.4 },
  ]
  it.each(sets)('holds for %o', (i) => {
    const lhs = callPrice(i) - putPrice(i)
    const rhs = i.S * Math.exp(-i.q * i.T) - i.K * Math.exp(-i.r * i.T)
    expect(lhs).toBeCloseTo(rhs, 9)
  })
})

describe('no-arbitrage bounds', () => {
  it('prices are non-negative and at least discounted intrinsic', () => {
    const sets: BsmInputs[] = [
      canonical,
      { S: 150, K: 100, T: 1, r: 0.05, q: 0.0, sigma: 0.2 }, // deep ITM call
      { S: 60, K: 100, T: 1, r: 0.05, q: 0.0, sigma: 0.2 }, // deep OTM call
    ]
    for (const i of sets) {
      const c = callPrice(i)
      const p = putPrice(i)
      expect(c).toBeGreaterThanOrEqual(0)
      expect(p).toBeGreaterThanOrEqual(0)
      // discounted intrinsic on the forward
      const dfR = Math.exp(-i.r * i.T)
      const F = forward(i)
      expect(c).toBeGreaterThanOrEqual(dfR * Math.max(F - i.K, 0) - 1e-9)
      expect(p).toBeGreaterThanOrEqual(dfR * Math.max(i.K - F, 0) - 1e-9)
    }
  })

  it('deep ITM call ≈ S·e^(−qT) − K·e^(−rT) (no time value left)', () => {
    const i: BsmInputs = { S: 1000, K: 100, T: 1, r: 0.05, q: 0.02, sigma: 0.2 }
    const intrinsic = i.S * Math.exp(-i.q * i.T) - i.K * Math.exp(-i.r * i.T)
    expect(callPrice(i)).toBeCloseTo(intrinsic, 6)
  })
})

describe('edge-case guards', () => {
  it('σ → 0 tends to the discounted-intrinsic limit', () => {
    const i: BsmInputs = { S: 110, K: 100, T: 1, r: 0.05, q: 0.0, sigma: 0 }
    const dfR = Math.exp(-i.r * i.T)
    const F = forward(i)
    expect(callPrice(i)).toBeCloseTo(dfR * Math.max(F - i.K, 0), 4)
  })

  it('T → 0 tends to the payoff (intrinsic)', () => {
    const itm: BsmInputs = { S: 110, K: 100, T: 0, r: 0.05, q: 0.0, sigma: 0.2 }
    const otm: BsmInputs = { S: 90, K: 100, T: 0, r: 0.05, q: 0.0, sigma: 0.2 }
    expect(callPrice(itm)).toBeCloseTo(10, 3)
    expect(callPrice(otm)).toBeCloseTo(0, 3)
    expect(putPrice(otm)).toBeCloseTo(10, 3)
  })

  it('produces finite numbers at the boundaries', () => {
    const i: BsmInputs = { S: 100, K: 100, T: 0, r: 0.05, q: 0.0, sigma: 0 }
    expect(Number.isFinite(callPrice(i))).toBe(true)
    expect(Number.isFinite(putPrice(i))).toBe(true)
  })

  it('rejects invalid inputs', () => {
    expect(() => validateInputs({ ...canonical, S: 0 })).toThrow(RangeError)
    expect(() => validateInputs({ ...canonical, K: -1 })).toThrow(RangeError)
    expect(() => validateInputs({ ...canonical, T: -0.5 })).toThrow(RangeError)
    expect(() => validateInputs({ ...canonical, sigma: -0.1 })).toThrow(RangeError)
  })
})
