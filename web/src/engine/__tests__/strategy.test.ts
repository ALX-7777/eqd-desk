import { describe, it, expect } from 'vitest'
import {
  analyzePosition,
  positionPremium,
  positionValueAt,
  payoffProfile,
  frontExpiry,
  signedQty,
  type Leg,
  type MarketParams,
} from '../strategy'
import { buildPreset } from '../presets'
import { expectClose } from './finiteDifference'

const m: MarketParams = { S: 100, r: 0.04, q: 0.01 }
const flatVol = () => 0.2

// A representative skewed surface for the skew-bet test (puts richer than calls).
const skewVol = (K: number) => 0.2 - 0.0015 * (K - 100)

function butterfly(): Leg[] {
  return buildPreset('butterfly', {
    S: 100,
    baseT: 0.25,
    widthPct: 0.05,
    strikeStep: 5,
    volFor: flatVol,
  })
}

describe('aggregate = signed-quantity-weighted sum of legs', () => {
  it('net price equals Σ signedQty · leg price', () => {
    const legs = butterfly()
    const a = analyzePosition(legs, m)
    const manual = a.legs.reduce((acc, la) => acc + la.signedQty * la.unit.price, 0)
    expect(a.price).toBeCloseTo(manual, 12)
    // and every greek aggregates the same way
    for (const k of ['delta', 'gamma', 'vega', 'theta', 'rho', 'vanna'] as const) {
      const sum = a.legs.reduce((acc, la) => acc + la.signedQty * la.unit[k], 0)
      expect(a.raw[k]).toBeCloseTo(sum, 12)
    }
  })

  it('reported price equals raw price (net premium)', () => {
    const a = analyzePosition(butterfly(), m)
    expect(a.reported.price).toBeCloseTo(a.raw.price, 12)
    expect(a.price).toBeCloseTo(positionPremium(butterfly(), m), 12)
  })
})

describe('position greeks match finite differences', () => {
  const cases: { name: string; legs: Leg[] }[] = [
    { name: 'butterfly', legs: butterfly() },
    {
      name: 'risk reversal',
      legs: buildPreset('risk-reversal', {
        S: 100,
        baseT: 0.5,
        widthPct: 0.05,
        strikeStep: 5,
        volFor: flatVol,
      }),
    },
    {
      name: 'calendar',
      legs: buildPreset('calendar', {
        S: 100,
        baseT: 0.25,
        widthPct: 0.05,
        strikeStep: 5,
        volFor: flatVol,
      }),
    },
  ]

  for (const { name, legs } of cases) {
    it(`delta / gamma / vega / theta / rho — ${name}`, () => {
      const a = analyzePosition(legs, m)
      const prem = (mm: MarketParams) => positionPremium(legs, mm)
      const dS = 1e-3 * m.S
      const fdDelta = (prem({ ...m, S: m.S + dS }) - prem({ ...m, S: m.S - dS })) / (2 * dS)
      const fdGamma =
        (prem({ ...m, S: m.S + dS }) - 2 * prem(m) + prem({ ...m, S: m.S - dS })) / (dS * dS)
      // parallel vol shift
      const bumpSig = (h: number) => legs.map((l) => ({ ...l, sigma: l.sigma + h }))
      const fdVega =
        (positionPremium(bumpSig(1e-4), m) - positionPremium(bumpSig(-1e-4), m)) / (2 * 1e-4)
      // parallel time shift → theta = −∂/∂T
      const bumpT = (h: number) => legs.map((l) => ({ ...l, T: l.T + h }))
      const fdTheta =
        -(positionPremium(bumpT(1e-5), m) - positionPremium(bumpT(-1e-5), m)) / (2 * 1e-5)
      const fdRho = (prem({ ...m, r: m.r + 1e-6 }) - prem({ ...m, r: m.r - 1e-6 })) / (2 * 1e-6)

      expectClose(a.raw.delta, fdDelta, 1e-4, 1e-6, `${name} delta`)
      expectClose(a.raw.gamma, fdGamma, 1e-3, 1e-6, `${name} gamma`)
      expectClose(a.raw.vega, fdVega, 1e-4, 1e-5, `${name} vega`)
      expectClose(a.raw.theta, fdTheta, 1e-4, 1e-5, `${name} theta`)
      expectClose(a.raw.rho, fdRho, 1e-4, 1e-5, `${name} rho`)
    })
  }
})

describe('payoff profiles', () => {
  it('bull call spread: max loss = debit, max gain = width − debit', () => {
    const legs = buildPreset('call-vertical', {
      S: 100,
      baseT: 0.25,
      widthPct: 0.05,
      strikeStep: 5,
      volFor: flatVol,
    })
    const debit = positionPremium(legs, m) // long lower strike, short higher → debit > 0
    expect(debit).toBeGreaterThan(0)
    const pts = payoffProfile(legs, m, 80, 120, 200)
    const lo = pts[0].expiryPnl // deep OTM → both worthless → −debit
    const hi = pts[pts.length - 1].expiryPnl // deep ITM → width − debit
    expect(lo).toBeCloseTo(-debit, 6)
    expect(hi).toBeCloseTo(5 - debit, 6) // width = 5
  })

  it('long straddle: worst case at the strike is −premium', () => {
    const legs = buildPreset('straddle', {
      S: 100,
      baseT: 0.25,
      widthPct: 0.05,
      strikeStep: 5,
      volFor: flatVol,
    })
    const premium = positionPremium(legs, m)
    const atK = positionValueAt(legs, 100, frontExpiry(legs), m) - premium
    expect(atK).toBeCloseTo(-premium, 6)
    expect(premium).toBeGreaterThan(0) // long vol costs money
  })

  it('butterfly: peak P&L at the body strike', () => {
    const legs = butterfly()
    const pts = payoffProfile(legs, m, 80, 120, 400)
    const peak = pts.reduce((best, p) => (p.expiryPnl > best.expiryPnl ? p : best))
    expect(peak.S).toBeCloseTo(100, 0) // body strike
    expect(peak.expiryPnl).toBeGreaterThan(0)
  })

  it('calendar: front expiry is the short front leg; value is finite there', () => {
    const legs = buildPreset('calendar', {
      S: 100,
      baseT: 0.25,
      widthPct: 0.05,
      strikeStep: 5,
      volFor: flatVol,
    })
    expect(frontExpiry(legs)).toBeCloseTo(0.25, 9)
    const v = positionValueAt(legs, 100, frontExpiry(legs), m)
    expect(Number.isFinite(v)).toBe(true)
    // a long calendar (short front, long back) is a debit
    expect(positionPremium(legs, m)).toBeGreaterThan(0)
  })
})

describe('presets', () => {
  const params = { S: 100, baseT: 0.25, widthPct: 0.05, strikeStep: 5, volFor: flatVol }

  it('build the expected leg structures', () => {
    expect(buildPreset('straddle', params)).toHaveLength(2)
    expect(buildPreset('butterfly', params)).toHaveLength(3)
    expect(buildPreset('iron-condor', params)).toHaveLength(4)
    const bfly = buildPreset('butterfly', params)
    expect(bfly[1].quantity).toBe(2) // body is 2x
    expect(bfly[1].side).toBe('short')
    const rr = buildPreset('risk-reversal', params)
    expect(rr.find((l) => l.type === 'put')?.side).toBe('short')
    expect(rr.find((l) => l.type === 'call')?.side).toBe('long')
  })

  it('seeds each leg vol from the provider and supports multi-expiry', () => {
    const legs = buildPreset('calendar', { ...params, volFor: (_K, T) => 0.2 + T * 0.01 })
    expect(legs[0].T).not.toBe(legs[1].T) // calendar spans two expiries
    for (const l of legs) expect(l.sigma).toBeCloseTo(0.2 + l.T * 0.01, 9)
  })

  it('unique leg ids', () => {
    const ids = buildPreset('iron-condor', params).map((l) => l.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

describe('risk reversal expresses a skew bet', () => {
  it('skew (richer puts) makes the long-call/short-put RR cheaper than under flat vol', () => {
    const flat = buildPreset('risk-reversal', {
      S: 100,
      baseT: 0.5,
      widthPct: 0.05,
      strikeStep: 5,
      volFor: flatVol,
    })
    const skewed = buildPreset('risk-reversal', {
      S: 100,
      baseT: 0.5,
      widthPct: 0.05,
      strikeStep: 5,
      volFor: skewVol,
    })
    // Under put-skew the short put collects more, so the structure is cheaper.
    expect(positionPremium(skewed, m)).toBeLessThan(positionPremium(flat, m))
  })
})

describe('edge cases', () => {
  it('empty position is all zeros', () => {
    const a = analyzePosition([], m)
    expect(a.price).toBe(0)
    expect(a.raw.delta).toBe(0)
    expect(signedQty({ id: 'x', type: 'call', side: 'short', quantity: 3, K: 100, T: 1, sigma: 0.2 })).toBe(-3)
  })
})
