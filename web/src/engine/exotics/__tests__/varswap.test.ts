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

  it('flat smile prices the ATM vol to 1e-4 on the default strip, 7 days to a year', () => {
    // Regression: without the forward-kink correction a flat smile printed a nonzero
    // "convexity premium" (30d at 14.6%: 14.585%; 7d at 5%: 4.805% — the wrong sign).
    const spx = { S: 6312.45, r: 0.043, q: 0.013 }
    for (const days of [7, 14, 30, 60, 90, 180, 365])
      for (const sig of [0.05, 0.1, 0.146, 0.2, 0.3]) {
        const res = priceVarianceSwap({ ...spx, T: days / 365, volFor: () => sig })
        expect(Math.abs(res.fairVol - sig)).toBeLessThan(1e-4)
      }
  })

  it('a short-tenor premium agrees with a fine strip (right sign)', () => {
    const spx = { S: 6312.45, r: 0.043, q: 0.013, T: 7 / 365 }
    const F = spx.S * Math.exp((spx.r - spx.q) * spx.T)
    const volFor = (K: number) => Math.max(0.03, 0.05 + 0.2 * Math.log(K / F))
    const res = priceVarianceSwap({ ...spx, volFor })
    const fine = priceVarianceSwap({ ...spx, volFor, nStrikes: 40000 })
    expect(res.fairVol - res.atmVol).toBeGreaterThan(0)
    expect(Math.abs(res.fairVol - fine.fairVol)).toBeLessThan(1e-4)
  })

  it('no grid correction when the forward lies outside the strip', () => {
    const res = priceVarianceSwap({ ...base, volFor: () => 0.2, loMult: 1.1 })
    expect(res.gridCorrection).toBe(0)
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
    const dK = res.strip[1].K - res.strip[0].K
    res.strip.forEach((pt, j) => {
      expect(pt.type).toBe(pt.K < res.forward ? 'put' : 'call')
      const half = j === 0 || j === res.strip.length - 1 ? 0.5 : 1 // trapezoid ends
      expect(pt.weight).toBeCloseTo((half * dK) / (pt.K * pt.K), 12)
    })
  })
})
