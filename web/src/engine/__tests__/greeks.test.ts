import { describe, it, expect } from 'vitest'
import {
  delta,
  gamma,
  vega,
  theta,
  rho,
  vanna,
  volga,
  charm,
  speed,
  color,
  rawGreeks,
} from '../greeks'
import { analyzeOption } from '../index'
import { bsmCore } from '../bsm'
import type { BsmInputs, OptionType } from '../types'
import { fd, expectClose } from './finiteDifference'

const canonical: BsmInputs = { S: 100, K: 100, T: 1, r: 0.05, q: 0, sigma: 0.2 }

// Smooth parameter sets used for finite-difference validation. A q≠0 case is
// included because q=0 hides the dividend terms in delta/charm/color.
const SETS: { name: string; i: BsmInputs }[] = [
  { name: 'ATM q=0', i: canonical },
  // q≠0 set, deliberately off the d2=0 point so volga/charm are meaningfully nonzero.
  { name: 'ATM q=3%', i: { S: 100, K: 100, T: 1, r: 0.05, q: 0.03, sigma: 0.25 } },
  { name: 'OTM call', i: { S: 100, K: 120, T: 0.5, r: 0.03, q: 0.01, sigma: 0.25 } },
  { name: 'ITM strikes', i: { S: 120, K: 100, T: 0.75, r: 0.04, q: 0.02, sigma: 0.18 } },
]

const TYPES: OptionType[] = ['call', 'put']

// Analytic greek under test, keyed to its finite-difference estimate and tolerance.
const GREEKS: {
  name: string
  analytic: (i: BsmInputs, t: OptionType) => number
  fd: (i: BsmInputs, t: OptionType) => number
  rtol: number
  atol: number
}[] = [
  { name: 'delta', analytic: (i, t) => delta(i, t), fd: fd.delta, rtol: 1e-5, atol: 1e-8 },
  { name: 'vega', analytic: (i) => vega(i), fd: fd.vega, rtol: 1e-5, atol: 1e-7 },
  { name: 'theta', analytic: (i, t) => theta(i, t), fd: fd.theta, rtol: 1e-5, atol: 1e-7 },
  { name: 'rho', analytic: (i, t) => rho(i, t), fd: fd.rho, rtol: 1e-5, atol: 1e-7 },
  { name: 'gamma', analytic: (i) => gamma(i), fd: fd.gamma, rtol: 1e-4, atol: 1e-8 },
  { name: 'vanna', analytic: (i) => vanna(i), fd: fd.vanna, rtol: 1e-4, atol: 1e-7 },
  { name: 'volga', analytic: (i) => volga(i), fd: fd.volga, rtol: 1e-4, atol: 1e-6 },
  { name: 'charm', analytic: (i, t) => charm(i, t), fd: fd.charm, rtol: 1e-4, atol: 1e-6 },
  { name: 'speed', analytic: (i) => speed(i), fd: fd.speed, rtol: 2e-3, atol: 1e-9 },
  { name: 'color', analytic: (i) => color(i), fd: fd.color, rtol: 5e-3, atol: 1e-6 },
]

describe('greeks match central finite differences', () => {
  for (const { name, i } of SETS) {
    for (const t of TYPES) {
      for (const g of GREEKS) {
        it(`${g.name} — ${name} ${t}`, () => {
          expectClose(g.analytic(i, t), g.fd(i, t), g.rtol, g.atol, `${g.name}/${name}/${t}`)
        })
      }
    }
  }
})

describe('hard-coded reference values (canonical set, q=0)', () => {
  it('delta', () => {
    expect(delta(canonical, 'call')).toBeCloseTo(0.6368306511756191, 7)
    expect(delta(canonical, 'put')).toBeCloseTo(-0.36316934882438086, 7)
  })
  it('gamma', () => {
    expect(gamma(canonical)).toBeCloseTo(0.018762017345846895, 9)
  })
  it('vega (raw per 1.00, reported per 1%)', () => {
    expect(vega(canonical)).toBeCloseTo(37.52403469169379, 6)
    expect(analyzeOption(canonical, 'call').reported.vega).toBeCloseTo(0.3752403469169379, 8)
  })
  it('theta (raw per year, reported per day)', () => {
    expect(theta(canonical, 'call')).toBeCloseTo(-6.414027546438197, 6)
    expect(analyzeOption(canonical, 'call').reported.theta).toBeCloseTo(-0.017572678209419718, 8)
  })
  it('rho (raw per 1.00, reported per 1%)', () => {
    expect(rho(canonical, 'call')).toBeCloseTo(53.232481545376345, 6)
    expect(analyzeOption(canonical, 'call').reported.rho).toBeCloseTo(0.5323248154537635, 8)
  })
  it('vanna', () => {
    expect(vanna(canonical)).toBeCloseTo(-0.2814302602377034, 8)
  })
})

describe('greek invariants', () => {
  for (const { name, i } of SETS) {
    it(`vega, gamma ≥ 0 and delta within bounds — ${name}`, () => {
      expect(vega(i)).toBeGreaterThanOrEqual(0)
      expect(gamma(i)).toBeGreaterThanOrEqual(0)
      const dfQ = Math.exp(-i.q * i.T)
      const dc = delta(i, 'call')
      const dp = delta(i, 'put')
      expect(dc).toBeGreaterThanOrEqual(0)
      expect(dc).toBeLessThanOrEqual(dfQ + 1e-12)
      expect(dp).toBeLessThanOrEqual(0)
      expect(dp).toBeGreaterThanOrEqual(-dfQ - 1e-12)
    })

    it(`delta parity Δc − Δp = e^(−qT) — ${name}`, () => {
      const dfQ = Math.exp(-i.q * i.T)
      expect(delta(i, 'call') - delta(i, 'put')).toBeCloseTo(dfQ, 12)
    })

    it(`symmetric greeks identical for call & put — ${name}`, () => {
      const c = rawGreeks(i, 'call')
      const p = rawGreeks(i, 'put')
      for (const k of ['gamma', 'vega', 'vanna', 'volga', 'speed', 'color'] as const) {
        expect(c[k]).toBeCloseTo(p[k], 12)
      }
    })
  }
})

describe('degenerate points', () => {
  it('vomma (volga) vanishes exactly when d2 = 0', () => {
    // S=K=100, T=1, r−q=0.02, σ=0.2 ⇒ d2 = d1 − σ√T = 0.2 − 0.2 = 0.
    // Here vega·d1·d2/σ = 0 analytically; a finite difference would only show
    // truncation noise, so we assert the exact analytic value directly.
    const i: BsmInputs = { S: 100, K: 100, T: 1, r: 0.05, q: 0.03, sigma: 0.2 }
    expect(bsmCore(i).d2).toBeCloseTo(0, 12)
    expect(volga(i)).toBeCloseTo(0, 9)
  })
})

describe('acceptance behaviours (Phase 1 spec)', () => {
  it('ATM gamma spikes as T shrinks', () => {
    const long = gamma({ ...canonical, T: 1 })
    const mid = gamma({ ...canonical, T: 0.25 })
    const short = gamma({ ...canonical, T: 1 / 52 })
    expect(mid).toBeGreaterThan(long)
    expect(short).toBeGreaterThan(mid)
  })

  it('increasing T trades gamma down for vega up', () => {
    const shortV = vega({ ...canonical, T: 1 / 52 })
    const longV = vega({ ...canonical, T: 1 })
    const shortG = gamma({ ...canonical, T: 1 / 52 })
    const longG = gamma({ ...canonical, T: 1 })
    expect(longV).toBeGreaterThan(shortV)
    expect(shortG).toBeGreaterThan(longG)
  })
})

describe('bsmCore consistency', () => {
  it('rawGreeks price equals analyzeOption.reported.price', () => {
    for (const t of TYPES) {
      const a = analyzeOption(canonical, t)
      expect(a.raw.price).toBeCloseTo(a.reported.price, 12)
      // sanity: d1/d2 reproduce
      const c = bsmCore(canonical)
      expect(c.d2).toBeCloseTo(c.d1 - c.volSqrtT, 12)
    }
  })
})
