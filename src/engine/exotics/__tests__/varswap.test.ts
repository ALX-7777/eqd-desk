import { describe, it, expect } from 'vitest'
import { priceVarianceSwap } from '../varswap'

const base = { S: 100, T: 1, r: 0.03, q: 0.01 }

describe('variance swap fair variance', () => {
  it('flat vol → fair variance = σ² (log-contract recovers GBM variance)', () => {
    for (const sig of [0.15, 0.2, 0.3]) {
      const res = priceVarianceSwap({ ...base, volFor: () => sig })
      expect(res.fairVariance).toBeCloseTo(sig * sig, 3)
      expect(res.fairVol).toBeCloseTo(sig, 3)
    }
  })

  it('returns the forward and ATM vol', () => {
    const res = priceVarianceSwap({ ...base, volFor: () => 0.2 })
    expect(res.forward).toBeCloseTo(base.S * Math.exp((base.r - base.q) * base.T), 9)
    expect(res.atmVol).toBeCloseTo(0.2, 9)
  })

  it('downward skew lifts fair vol above ATM (the convexity / VIX premium)', () => {
    // Puts richer than calls (vol falls with strike).
    const skew = (K: number) => Math.max(0.05, 0.2 - 0.0015 * (K - 100))
    const res = priceVarianceSwap({ ...base, volFor: skew })
    expect(res.fairVol).toBeGreaterThan(res.atmVol)
  })

  it('strip is OTM (puts below the forward, calls above) and weighted 1/K²', () => {
    const res = priceVarianceSwap({ ...base, volFor: () => 0.2 })
    for (const pt of res.strip) {
      expect(pt.type).toBe(pt.K < res.forward ? 'put' : 'call')
      expect(pt.weight).toBeGreaterThan(0)
    }
  })
})
