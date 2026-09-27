import { describe, it, expect } from 'vitest'
import { barrierPrice, barrierGreeks, type BarrierInputs, type BarrierKind } from '../barrier'
import { price as vanillaPrice } from '../../bsm'
import { mulberry32, makeNormal } from '../mc'
import type { OptionType } from '../../types'

const base = { S: 100, T: 1, r: 0.05, q: 0.01, sigma: 0.2 }

describe('knock-in + knock-out = vanilla (in-out parity)', () => {
  const types: OptionType[] = ['call', 'put']
  const configs = [
    { dir: 'down', H: 90, Ks: [100, 85] },
    { dir: 'up', H: 110, Ks: [100, 115] },
  ] as const

  for (const type of types) {
    for (const { dir, H, Ks } of configs) {
      for (const K of Ks) {
        it(`${dir} ${type} K=${K} H=${H}`, () => {
          const ki = barrierPrice({ ...base, K, H, type, kind: `${dir}-in` as BarrierKind })
          const ko = barrierPrice({ ...base, K, H, type, kind: `${dir}-out` as BarrierKind })
          const vanilla = vanillaPrice({ ...base, K }, type)
          expect(ki + ko).toBeCloseTo(vanilla, 9)
        })
      }
    }
  }
})

describe('barrier limits', () => {
  it('down-and-out call with a far barrier ≈ vanilla call', () => {
    const v = vanillaPrice({ ...base, K: 100 }, 'call')
    expect(barrierPrice({ ...base, K: 100, H: 1, type: 'call', kind: 'down-out' })).toBeCloseTo(v, 6)
  })
  it('up-and-out call with a far barrier ≈ vanilla call', () => {
    const v = vanillaPrice({ ...base, K: 100 }, 'call')
    expect(barrierPrice({ ...base, K: 100, H: 1e6, type: 'call', kind: 'up-out' })).toBeCloseTo(v, 6)
  })
  it('down-and-in call with a far barrier ≈ 0', () => {
    expect(barrierPrice({ ...base, K: 100, H: 1, type: 'call', kind: 'down-in' })).toBeLessThan(1e-4)
  })
  it('knocked-out already → 0; knocked-in already → vanilla', () => {
    // down barrier above spot ⇒ already breached
    expect(barrierPrice({ ...base, K: 100, H: 105, type: 'call', kind: 'down-out' })).toBe(0)
    const v = vanillaPrice({ ...base, K: 100 }, 'call')
    expect(barrierPrice({ ...base, K: 100, H: 105, type: 'call', kind: 'down-in' })).toBeCloseTo(v, 9)
  })
})

// --- Monte-Carlo cross-check (discrete monitoring + BGK continuity correction) ---
function mcBarrier(i: BarrierInputs, paths: number, steps: number, seed: number) {
  const normal = makeNormal(mulberry32(seed))
  const dt = i.T / steps
  const drift = (i.r - i.q - 0.5 * i.sigma * i.sigma) * dt
  const vol = i.sigma * Math.sqrt(dt)
  const isDown = i.kind === 'down-in' || i.kind === 'down-out'
  const isOut = i.kind === 'down-out' || i.kind === 'up-out'
  // Broadie–Glasserman–Kou: to approximate the CONTINUOUS-barrier price with a
  // discrete MC, shift the monitored barrier so breaching is as easy as under
  // continuous monitoring — down-barrier UP, up-barrier DOWN.
  const beta = 0.5826
  const Hadj = isDown
    ? i.H * Math.exp(beta * i.sigma * Math.sqrt(dt))
    : i.H * Math.exp(-beta * i.sigma * Math.sqrt(dt))
  const df = Math.exp(-i.r * i.T)
  let sum = 0
  let sum2 = 0
  for (let p = 0; p < paths; p++) {
    let s = i.S
    let breached = false
    for (let k = 0; k < steps; k++) {
      s = s * Math.exp(drift + vol * normal())
      if (isDown ? s <= Hadj : s >= Hadj) breached = true
    }
    const intrinsic = i.type === 'call' ? Math.max(s - i.K, 0) : Math.max(i.K - s, 0)
    const alive = isOut ? !breached : breached
    const pv = alive ? df * intrinsic : 0
    sum += pv
    sum2 += pv * pv
  }
  const price = sum / paths
  const stderr = Math.sqrt(Math.max(sum2 / paths - price * price, 0) / paths)
  return { price, stderr }
}

describe('closed form matches Monte Carlo', () => {
  // Cover all four knock-OUT types (KI = vanilla − KO follows exactly from
  // parity), spanning both the K>H and K<H formula branches:
  //   down-out call K>H (A−C), up-out call K<H (A−B+C−D),
  //   down-out put  K>H (A−B+C−D), up-out put  K<H (A−C).
  const cases: { name: string; i: BarrierInputs }[] = [
    { name: 'down-out call', i: { ...base, K: 100, H: 90, type: 'call', kind: 'down-out' } },
    { name: 'up-out call', i: { ...base, K: 100, H: 120, type: 'call', kind: 'up-out' } },
    { name: 'down-out put', i: { ...base, K: 100, H: 90, type: 'put', kind: 'down-out' } },
    { name: 'up-out put', i: { ...base, K: 100, H: 110, type: 'put', kind: 'up-out' } },
    { name: 'down-in put', i: { ...base, K: 100, H: 90, type: 'put', kind: 'down-in' } },
  ]
  for (const { name, i } of cases) {
    it(name, () => {
      const cf = barrierPrice(i)
      const { price, stderr } = mcBarrier(i, 60000, 200, 0x1234 + i.K)
      // within ~4 standard errors plus a small absolute floor for discretisation
      expect(Math.abs(cf - price)).toBeLessThan(4 * stderr + 0.05)
    })
  }
})

describe('barrier greeks', () => {
  it('are finite and gamma is large near the barrier', () => {
    const nearBarrier = barrierGreeks({ ...base, K: 100, H: 90, S: 91, type: 'call', kind: 'down-out' })
    const farFromBarrier = barrierGreeks({ ...base, K: 100, H: 90, S: 110, type: 'call', kind: 'down-out' })
    expect(Number.isFinite(nearBarrier.gamma)).toBe(true)
    expect(Math.abs(nearBarrier.gamma)).toBeGreaterThan(Math.abs(farFromBarrier.gamma))
  })
})
