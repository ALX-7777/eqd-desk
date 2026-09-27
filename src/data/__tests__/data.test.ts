import { describe, it, expect } from 'vitest'
import { UNDERLYINGS, DEFAULT_UNDERLYING } from '../config'
import { snapshot, validateSnapshot, seedInputs } from '../snapshot'
import type { MarketSnapshot } from '../snapshot'
import { buildSurface, VOL_FLOOR } from '../volSurface'

describe('underlying config', () => {
  it('has SPX and SX5E presets, SPX default', () => {
    expect(DEFAULT_UNDERLYING).toBe('spx')
    expect(UNDERLYINGS.spx.indexTicker).toBe('^GSPC')
    expect(UNDERLYINGS.spx.volIndexTicker).toBe('^VIX')
    expect(UNDERLYINGS.spx.optionsProxy).toBe('SPY')
    expect(UNDERLYINGS.sx5e.currency).toBe('EUR')
    expect(UNDERLYINGS.sx5e.volIndexTicker).toBe('V2TX.DE')
  })
})

describe('snapshot loader', () => {
  it('loads and validates the committed seed', () => {
    expect(snapshot.spot).toBeGreaterThan(0)
    expect(snapshot.atm_vol_30d).toBeGreaterThan(0)
    expect(snapshot.underlying).toBe('spx')
    expect(snapshot.skew.atm).toBeCloseTo(snapshot.atm_vol_30d, 6)
    expect(snapshot.term_structure.length).toBeGreaterThan(0)
  })

  it('rejects malformed snapshots', () => {
    expect(() => validateSnapshot(null)).toThrow()
    expect(() => validateSnapshot({ ...snapshot, spot: -1 })).toThrow()
    expect(() => validateSnapshot({ ...snapshot, atm_vol_30d: 'x' })).toThrow()
    expect(() => validateSnapshot({ ...snapshot, r: undefined })).toThrow()
  })

  it('seeds a sensible default option from the snapshot', () => {
    const i = seedInputs(snapshot)
    expect(i.S).toBe(snapshot.spot)
    expect(i.sigma).toBe(snapshot.atm_vol_30d)
    expect(i.r).toBe(snapshot.r)
    expect(i.q).toBe(snapshot.q)
    expect(i.T).toBeCloseTo(30 / 365, 9)
    expect(i.K % 25).toBe(0) // strike snapped to a round level
    expect(Math.abs(i.K - snapshot.spot)).toBeLessThan(25)
  })
})

describe('vol surface', () => {
  const surface = buildSurface(snapshot)

  it('ATM term structure interpolates and clamps', () => {
    const ts = snapshot.term_structure
    // exact at a knot
    expect(surface.atmVol(ts[0].t)).toBeCloseTo(ts[0].atm_iv, 9)
    // flat extrapolation beyond the ends
    expect(surface.atmVol(0.0001)).toBeCloseTo(ts[0].atm_iv, 9)
    expect(surface.atmVol(50)).toBeCloseTo(ts[ts.length - 1].atm_iv, 9)
    // interpolated strictly between two knots
    const mid = surface.atmVol((ts[0].t + ts[1].t) / 2)
    const lo = Math.min(ts[0].atm_iv, ts[1].atm_iv)
    const hi = Math.max(ts[0].atm_iv, ts[1].atm_iv)
    expect(mid).toBeGreaterThanOrEqual(lo)
    expect(mid).toBeLessThanOrEqual(hi)
  })

  it('ATM strike (k=0) returns the ATM vol', () => {
    const T = 0.25
    expect(surface.getVol(snapshot.spot, T)).toBeCloseTo(surface.atmVol(T), 9)
  })

  it('skew slopes downward in strike (equity skew)', () => {
    const T = 0.25
    const lowK = surface.getVol(snapshot.spot * 0.95, T)
    const atmK = surface.getVol(snapshot.spot, T)
    const highK = surface.getVol(snapshot.spot * 1.05, T)
    expect(lowK).toBeGreaterThan(atmK)
    expect(highK).toBeLessThan(atmK)
  })

  it('never returns vol below the floor', () => {
    for (const mult of [0.5, 0.8, 1, 1.2, 2, 5]) {
      expect(surface.getVol(snapshot.spot * mult, 0.1)).toBeGreaterThanOrEqual(VOL_FLOOR)
    }
  })

  it('can be built from a custom snapshot', () => {
    const custom: MarketSnapshot = {
      ...snapshot,
      spot: 5000,
      atm_vol_30d: 0.2,
      skew: { atm: 0.2, slope: -0.5, curv: 0.5 },
      term_structure: [{ t: 0.25, atm_iv: 0.2 }],
    }
    const s = buildSurface(custom)
    expect(s.spot).toBe(5000)
    expect(s.getVol(5000, 0.25)).toBeCloseTo(0.2, 9)
  })
})
