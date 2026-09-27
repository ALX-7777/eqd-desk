import { describe, it, expect } from 'vitest'
import { priceAutocall, type AutocallInputs } from '../autocall'
import { cashOrNothingPrice, assetOrNothingPrice } from '../digital'

const base: AutocallInputs = {
  S: 100,
  S0: 100,
  sigma: 0.2,
  r: 0.04,
  q: 0.01,
  maturity: 3,
  nObs: 3,
  couponRate: 0.06,
  autocallBarrier: 1.0,
  couponBarrier: 0.7,
  protectionBarrier: 0.7,
  memory: true,
  notional: 100,
}

describe('autocallable Monte Carlo', () => {
  it('is reproducible with a fixed seed', () => {
    const a = priceAutocall(base, 5000, 42)
    const b = priceAutocall(base, 5000, 42)
    expect(a.price).toBe(b.price)
  })

  it('reports sane diagnostics', () => {
    const res = priceAutocall(base, 40000)
    expect(res.price).toBeGreaterThan(0)
    expect(res.probAutocall).toBeGreaterThanOrEqual(0)
    expect(res.probAutocall).toBeLessThanOrEqual(1)
    expect(res.probCapitalLoss).toBeGreaterThanOrEqual(0)
    expect(res.expectedLife).toBeGreaterThan(0)
    expect(res.expectedLife).toBeLessThanOrEqual(base.maturity + 1e-9)
    expect(res.stderr).toBeGreaterThan(0)
  })

  it('lower autocall barrier ⇒ higher early-redemption probability', () => {
    const high = priceAutocall({ ...base, autocallBarrier: 1.1 }, 40000)
    const low = priceAutocall({ ...base, autocallBarrier: 0.8 }, 40000)
    expect(low.probAutocall).toBeGreaterThan(high.probAutocall)
  })

  it('deterministic cross-check: zero-coupon, never-autocall note = digital replication', () => {
    // No coupon, autocall barrier unreachable ⇒ only the maturity redemption matters:
    //   payoff = N · [ 1_{S_T ≥ PB} + (S_T/S0)·1_{S_T < PB} ].
    // PV = N · [ cash-or-nothing call(PB) + asset-or-nothing put(PB)/S0 ].
    const i: AutocallInputs = {
      ...base,
      couponRate: 0,
      autocallBarrier: 10, // never reached
      protectionBarrier: 0.7,
      memory: false,
    }
    const PB = i.protectionBarrier * i.S0
    const cashCall = cashOrNothingPrice({ S: i.S, K: PB, T: i.maturity, r: i.r, q: i.q, sigma: i.sigma, type: 'call', cash: 1 })
    const assetPut = assetOrNothingPrice({ S: i.S, K: PB, T: i.maturity, r: i.r, q: i.q, sigma: i.sigma, type: 'put', cash: 0 })
    const analytic = i.notional * (cashCall + assetPut / i.S0)

    const mc = priceAutocall(i, 200000, 20250624)
    expect(Math.abs(mc.price - analytic)).toBeLessThan(4 * mc.stderr + 0.02)
  })
})
