import { describe, it, expect } from 'vitest'
import { normCdf, normPdf, SQRT_2PI } from '../mathUtils'

describe('normPdf', () => {
  it('matches known density values', () => {
    expect(normPdf(0)).toBeCloseTo(1 / SQRT_2PI, 15)
    expect(normPdf(0)).toBeCloseTo(0.3989422804014327, 15)
    expect(normPdf(1)).toBeCloseTo(0.24197072451914337, 15)
    expect(normPdf(-1)).toBeCloseTo(0.24197072451914337, 15) // even function
    expect(normPdf(2)).toBeCloseTo(0.05399096651318806, 15)
  })
})

describe('normCdf (West 2009)', () => {
  it('matches known CDF values to ~1e-12', () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 15)
    expect(normCdf(1)).toBeCloseTo(0.8413447460685429, 12)
    expect(normCdf(-1)).toBeCloseTo(0.15865525393145707, 12)
    expect(normCdf(2)).toBeCloseTo(0.9772498680518208, 12)
    expect(normCdf(-2)).toBeCloseTo(0.022750131948179195, 12)
    expect(normCdf(1.96)).toBeCloseTo(0.9750021048517795, 12)
    expect(normCdf(1.6448536269514722)).toBeCloseTo(0.95, 12)
    expect(normCdf(3)).toBeCloseTo(0.9986501019683699, 12)
    expect(normCdf(-3)).toBeCloseTo(0.0013498980316300933, 12)
  })

  it('is symmetric: N(x) + N(-x) = 1', () => {
    for (const x of [0.1, 0.5, 1, 2.3, 4.7, 6.5]) {
      expect(normCdf(x) + normCdf(-x)).toBeCloseTo(1, 14)
    }
  })

  it('is monotonically increasing', () => {
    let prev = -Infinity
    for (let x = -6; x <= 6; x += 0.25) {
      const v = normCdf(x)
      expect(v).toBeGreaterThanOrEqual(prev)
      prev = v
    }
  })

  it('keeps relative accuracy in the deep tails', () => {
    // West/Hart is machine-precision near the centre, ~5e-11 relative at the
    // rational/CF boundary (z≈5) and ~1e-8 relative deep in the continued-
    // fraction tail (z≈8) — orders of magnitude tighter than pricing needs.
    const ref5 = 2.8665157187919333e-7 // P(Z < −5)
    const ref8 = 6.220960574271782e-16 // P(Z < −8)
    expect(Math.abs(normCdf(-5) / ref5 - 1)).toBeLessThan(1e-9)
    expect(Math.abs(normCdf(-8) / ref8 - 1)).toBeLessThan(1e-7)
    expect(normCdf(-40)).toBe(0) // underflow region
    expect(normCdf(40)).toBe(1)
  })

  it('stays within [0, 1]', () => {
    for (let x = -50; x <= 50; x += 0.7) {
      const v = normCdf(x)
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThanOrEqual(1)
    }
  })
})
