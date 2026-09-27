import { describe, it, expect } from 'vitest'
import {
  cashOrNothingPrice,
  assetOrNothingPrice,
  callSpreadReplication,
  digitalGreeks,
  type DigitalInputs,
} from '../digital'
import { normCdf } from '../../mathUtils'
import { price as vanillaPrice } from '../../bsm'

const base: DigitalInputs = { S: 100, K: 100, T: 1, r: 0.05, q: 0.02, sigma: 0.2, type: 'call', cash: 1 }

describe('cash-or-nothing digital', () => {
  it('prices as Q·e^(−rT)·N(±d2)', () => {
    const sig = base.sigma
    const d2 = (Math.log(base.S / base.K) + (base.r - base.q - 0.5 * sig * sig) * base.T) / (sig * Math.sqrt(base.T))
    const df = Math.exp(-base.r * base.T)
    expect(cashOrNothingPrice({ ...base, type: 'call' })).toBeCloseTo(df * normCdf(d2), 12)
    expect(cashOrNothingPrice({ ...base, type: 'put' })).toBeCloseTo(df * normCdf(-d2), 12)
  })

  it('call + put cash digitals = e^(−rT) (something must pay)', () => {
    const c = cashOrNothingPrice({ ...base, type: 'call' })
    const p = cashOrNothingPrice({ ...base, type: 'put' })
    expect(c + p).toBeCloseTo(Math.exp(-base.r * base.T), 12)
  })

  it('is bounded by 0 and the discounted cash', () => {
    const c = cashOrNothingPrice(base)
    expect(c).toBeGreaterThanOrEqual(0)
    expect(c).toBeLessThanOrEqual(Math.exp(-base.r * base.T) * base.cash + 1e-12)
  })
})

describe('digital identities & replication', () => {
  it('vanilla call = asset-or-nothing call − K·cash-or-nothing(Q=1)', () => {
    const an = assetOrNothingPrice({ ...base, type: 'call' })
    const cn = cashOrNothingPrice({ ...base, type: 'call', cash: 1 })
    const vanilla = vanillaPrice({ S: base.S, K: base.K, T: base.T, r: base.r, q: base.q, sigma: base.sigma }, 'call')
    expect(an - base.K * cn).toBeCloseTo(vanilla, 10)
  })

  it('tight call spread converges to the digital as width → 0', () => {
    const digital = cashOrNothingPrice(base)
    expect(callSpreadReplication(base, 2)).toBeCloseTo(digital, 2)
    expect(callSpreadReplication(base, 0.2)).toBeCloseTo(digital, 4)
    expect(callSpreadReplication(base, 0.02)).toBeCloseTo(digital, 6)
    // put side too
    const putBase = { ...base, type: 'put' as const }
    expect(callSpreadReplication(putBase, 0.02)).toBeCloseTo(cashOrNothingPrice(putBase), 6)
  })
})

describe('digital greeks', () => {
  it('delta matches the analytic Q·e^(−rT)·φ(d2)/(S·σ√T) and is +ve for a call', () => {
    const sig = base.sigma
    const d2 = (Math.log(base.S / base.K) + (base.r - base.q - 0.5 * sig * sig) * base.T) / (sig * Math.sqrt(base.T))
    const phi = Math.exp(-0.5 * d2 * d2) / Math.sqrt(2 * Math.PI)
    const analytic = base.cash * Math.exp(-base.r * base.T) * phi / (base.S * sig * Math.sqrt(base.T))
    const g = digitalGreeks(base)
    expect(g.delta).toBeCloseTo(analytic, 4)
    expect(g.delta).toBeGreaterThan(0)
  })

  it('gamma changes sign across the strike (spike behaviour)', () => {
    // Just below the strike gamma is positive, just above it is negative (short T).
    const shortDated = { ...base, T: 0.05 }
    const below = digitalGreeks({ ...shortDated, S: 98 })
    const above = digitalGreeks({ ...shortDated, S: 102 })
    expect(below.gamma).toBeGreaterThan(0)
    expect(above.gamma).toBeLessThan(0)
  })
})
