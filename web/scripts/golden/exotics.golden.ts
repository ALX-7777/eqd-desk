/**
 * Golden values for the Phase 3 exotics: single barriers (every kind × call/put over a
 * grid including spots right at / next to the barrier, plus market edge cases), digitals
 * (cash / asset-or-nothing, call-spread replication), variance-swap fair strikes over
 * several smiles, seeded autocallable Monte Carlo (several parameter sets and seeds),
 * GBM observation paths, and bump greeks for every product. Also records what the TS does
 * on the inputs the Python port rejects (zero/negative levels, degenerate counts).
 *
 * Non-finite numbers (NaN at degenerate inputs) are written as strings ("NaN",
 * "Infinity"), since JSON has no representation for them; Python's float() parses both.
 */
import { barrierPrice, barrierGreeks, type BarrierInputs, type BarrierKind } from '../../src/engine/exotics/barrier'
import {
  assetOrNothingPrice,
  callSpreadReplication,
  cashOrNothingPrice,
  digitalGreeks,
  type DigitalInputs,
} from '../../src/engine/exotics/digital'
import { priceVarianceSwap } from '../../src/engine/exotics/varswap'
import { autocallGreeks, priceAutocall, type AutocallInputs } from '../../src/engine/exotics/autocall'
import { numericGreeks } from '../../src/engine/exotics/numericGreeks'
import { makeNormal, mulberry32, simulateObsPath } from '../../src/engine/exotics/mc'
import { price as vanillaPrice } from '../../src/engine/bsm'
import type { OptionType } from '../../src/engine/types'
import { writeGolden } from './writeGolden'

function enc(x: unknown): unknown {
  if (typeof x === 'number') return Number.isFinite(x) ? x : String(x)
  if (Array.isArray(x)) return x.map(enc)
  if (x !== null && typeof x === 'object') {
    return Object.fromEntries(Object.entries(x).map(([k, v]) => [k, enc(v)]))
  }
  return x
}

const TYPES: OptionType[] = ['call', 'put']
const KINDS: BarrierKind[] = ['down-in', 'down-out', 'up-in', 'up-out']

function barrierGoldens() {
  const base = { T: 1, r: 0.05, q: 0.01, sigma: 0.2 }
  // Spots straddle both barriers (90 and 110), including right at them (breached branch).
  const spots = [80, 89.99, 90, 90.01, 91, 95, 100, 105, 109, 109.99, 110, 110.01, 120]
  const grid: unknown[] = []
  for (const type of TYPES)
    for (const kind of KINDS)
      for (const H of [90, 110])
        for (const K of [85, 100, 115])
          for (const S of spots) {
            const i: BarrierInputs = { ...base, S, K, H, type, kind }
            grid.push({ S, K, H, type, kind, price: barrierPrice(i) })
          }

  // Market edge cases at S = 100, K = 100 (T and σ floors, negative carry, high vol).
  const markets = [
    { T: 0, r: 0.05, q: 0.01, sigma: 0.2 },
    { T: 1 / 365, r: 0.05, q: 0.01, sigma: 0.2 },
    { T: 3, r: 0.05, q: 0.01, sigma: 0.2 },
    { T: 1, r: 0.05, q: 0.01, sigma: 0.6 },
    { T: 1, r: 0.05, q: 0.01, sigma: 0.01 },
    { T: 1, r: 0.05, q: 0.01, sigma: 0 },
    { T: 1, r: -0.005, q: 0.03, sigma: 0.2 },
    { T: 1, r: -0.005, q: 0.03, sigma: 0 },
    { T: 0.5, r: 0.043, q: 0.013, sigma: 0.146 },
  ]
  const edges: unknown[] = []
  for (const m of markets)
    for (const type of TYPES)
      for (const kind of KINDS)
        for (const K of [95, 100, 105]) {
          const H = kind.startsWith('down') ? 97 : 103
          edges.push({ ...m, S: 100, K, H, type, kind, price: barrierPrice({ ...m, S: 100, K, H, type, kind }) })
        }

  // Greeks by bumping, approaching the barrier from the live side, plus an SPX-level book.
  const greeks: unknown[] = []
  for (const type of TYPES)
    for (const kind of KINDS) {
      const down = kind.startsWith('down')
      const H = down ? 90 : 110
      const ss = down ? [90.5, 91, 95, 100, 110] : [109.5, 109, 105, 100, 90]
      for (const S of ss) {
        const i: BarrierInputs = { ...base, S, K: 100, H, type, kind }
        greeks.push({ inputs: i, greeks: barrierGreeks(i) })
      }
      const spx: BarrierInputs = {
        S: 6312.45, K: 6300, T: 0.5, r: 0.043, q: 0.013, sigma: 0.146, type, kind,
        H: down ? 5700 : 6900,
      }
      greeks.push({ inputs: spx, greeks: barrierGreeks(spx) })
      const expiry: BarrierInputs = { ...base, T: 0, S: 100, K: 100, H, type, kind }
      greeks.push({ inputs: expiry, greeks: barrierGreeks(expiry) })
    }

  return { base, grid, edges, greeks }
}

function digitalGoldens() {
  const prices: unknown[] = []
  const carries: [number, number][] = [[0.05, 0.02], [-0.005, 0.03]]
  for (const type of TYPES)
    for (const S of [80, 99, 100, 101, 120])
      for (const T of [0, 0.05, 1, 3])
        for (const sigma of [0, 0.2, 0.5])
          for (const [r, q] of carries) {
            const i: DigitalInputs = { S, K: 100, T, r, q, sigma, type, cash: 2.5 }
            prices.push({ inputs: i, cash: cashOrNothingPrice(i), asset: assetOrNothingPrice(i) })
          }
  for (const type of TYPES) {
    const i: DigitalInputs = { S: 6312.45, K: 6300, T: 30 / 365, r: 0.043, q: 0.013, sigma: 0.146, type, cash: 1 }
    prices.push({ inputs: i, cash: cashOrNothingPrice(i), asset: assetOrNothingPrice(i) })
  }

  const greeks: unknown[] = []
  for (const type of TYPES)
    for (const S of [98, 100, 102])
      for (const T of [0, 0.05, 1]) {
        const i: DigitalInputs = { S, K: 100, T, r: 0.05, q: 0.02, sigma: 0.2, type, cash: 1 }
        greeks.push({ inputs: i, greeks: digitalGreeks(i) })
      }

  const replication: unknown[] = []
  for (const type of TYPES)
    for (const S of [95, 100, 105])
      for (const width of [5, 2, 0.2, 0.02, 1e-12]) {
        const i: DigitalInputs = { S, K: 100, T: 1, r: 0.05, q: 0.02, sigma: 0.2, type, cash: 1 }
        replication.push({ inputs: i, width, price: callSpreadReplication(i, width) })
      }

  return { prices, greeks, replication }
}

// Vol smiles; tests/parity/test_exotics_parity.py defines the same functions by name.
const SMILES: Record<string, (K: number) => number> = {
  flat15: () => 0.15,
  flat20: () => 0.2,
  flat30: () => 0.3,
  linearSkew: (K) => Math.max(0.05, 0.2 - 0.0015 * (K - 100)),
  smile: (K) => {
    const k = Math.log(K / 100)
    return 0.2 - 0.12 * k + 0.25 * k * k
  },
  spxSkew: (K) => {
    const k = Math.log(K / 6312.45)
    return Math.max(0.05, 0.146 - 0.15 * k + 0.3 * k * k)
  },
}

function varswapGoldens() {
  const base = { S: 100, T: 1, r: 0.03, q: 0.01 }
  const cases = [
    { ...base, smile: 'flat15' },
    { ...base, smile: 'flat20' },
    { ...base, smile: 'flat30' },
    { ...base, smile: 'linearSkew' },
    { ...base, smile: 'smile', loMult: 0.5, hiMult: 2, nStrikes: 101 },
    { ...base, smile: 'smile', loMult: -0.1, hiMult: 2.5, nStrikes: 60 },
    { ...base, smile: 'linearSkew', nStrikes: 2 },
    { S: 6312.45, T: 30 / 365, r: 0.043, q: 0.013, smile: 'spxSkew' },
    { S: 6312.45, T: 2, r: 0.043, q: 0.013, smile: 'spxSkew', nStrikes: 250 },
  ]
  return cases.map((c) => {
    const res = priceVarianceSwap({ ...c, volFor: SMILES[c.smile] })
    // Keep the file small: every 20th strip point plus the last one.
    const idx = res.strip.map((_, j) => j).filter((j) => j % 20 === 0 || j === res.strip.length - 1)
    return {
      inputs: c,
      fairVariance: res.fairVariance,
      fairVol: res.fairVol,
      forward: res.forward,
      atmVol: res.atmVol,
      stripLength: res.strip.length,
      strip: idx.map((j) => ({ j, ...res.strip[j] })),
    }
  })
}

function autocallGoldens() {
  const base: AutocallInputs = {
    S: 100, S0: 100, sigma: 0.2, r: 0.04, q: 0.01, maturity: 3, nObs: 3, couponRate: 0.06,
    autocallBarrier: 1.0, couponBarrier: 0.7, protectionBarrier: 0.7, memory: true, notional: 100,
  }
  const sets: Record<string, AutocallInputs> = {
    base,
    noMemory: { ...base, memory: false },
    spxUi: {
      S: 6312.45, S0: 6312.45, sigma: 0.146, r: 0.043, q: 0.013, maturity: 3, nObs: 6, couponRate: 0.04,
      autocallBarrier: 1.0, couponBarrier: 0.7, protectionBarrier: 0.65, memory: true, notional: 100,
    },
    belowFixing: {
      ...base, S: 85, sigma: 0.3, nObs: 12, autocallBarrier: 0.95, couponBarrier: 0.8, protectionBarrier: 0.6,
    },
    singleObs: { ...base, maturity: 1, nObs: 1 },
    zeroCouponNoCall: { ...base, couponRate: 0, autocallBarrier: 10, memory: false },
    highVolLong: {
      ...base, sigma: 0.45, nObs: 24, autocallBarrier: 1.2, couponBarrier: 1.0, protectionBarrier: 0.5,
      couponRate: 0.015, notional: 1000,
    },
  }
  const prices: unknown[] = []
  for (const [name, i] of Object.entries(sets))
    for (const seed of [0x9e3779b1, 42, 20250624]) {
      prices.push({ name, inputs: i, paths: 4000, seed, result: priceAutocall(i, 4000, seed) })
    }
  // Library defaults (20 000 paths, default seed).
  for (const name of ['base', 'spxUi', 'belowFixing']) {
    prices.push({ name, inputs: sets[name], paths: null, seed: null, result: priceAutocall(sets[name]) })
  }

  const greeks = [
    { name: 'base', paths: 8000, seed: 42 },
    { name: 'spxUi', paths: 8000, seed: 0x9e3779b1 },
    { name: 'belowFixing', paths: 4000, seed: 7 },
    { name: 'noMemory', paths: null, seed: null },
  ].map(({ name, paths, seed }) => ({
    name,
    inputs: sets[name],
    paths,
    seed,
    greeks: paths === null ? autocallGreeks(sets[name]) : autocallGreeks(sets[name], paths, seed ?? undefined),
  }))

  return { sets, prices, greeks }
}

function mcGoldens() {
  const configs = [
    { S0: 100, r: 0.05, q: 0.01, sigma: 0.2, dt: 1 / 12, nSteps: 12, nPaths: 4, seed: 1 },
    { S0: 6312.45, r: 0.043, q: 0.013, sigma: 0.146, dt: 1 / 252, nSteps: 20, nPaths: 3, seed: 0xc0ffee },
    { S0: 50, r: -0.01, q: 0.0, sigma: 0.8, dt: 0.5, nSteps: 7, nPaths: 5, seed: 20250624 },
  ]
  return configs.map((c) => {
    const normal = makeNormal(mulberry32(c.seed))
    const paths: number[][] = []
    for (let p = 0; p < c.nPaths; p++) {
      const out: number[] = new Array(c.nSteps)
      simulateObsPath(c.S0, c.r, c.q, c.sigma, c.dt, c.nSteps, normal, out)
      paths.push(out)
    }
    return { ...c, paths }
  })
}

function numericGreeksGoldens() {
  // Bump greeks of a vanilla (a deterministic price function): pins the stencil and units.
  const rows: unknown[] = []
  const inputs = [
    { S: 100, K: 100, T: 1, q: 0.0 },
    { S: 100, K: 120, T: 0.25, q: 0.02 },
    { S: 6312.45, K: 6300, T: 30 / 365, q: 0.013 },
  ]
  for (const { S, K, T, q } of inputs)
    for (const type of TYPES) {
      const px = (s: number, sigma: number, t: number, r: number) =>
        vanillaPrice({ S: s, K, T: t, r, q, sigma }, type)
      rows.push({ S, K, T, q, r: 0.04, sigma: 0.2, type, greeks: numericGreeks(px, S, 0.2, T, 0.04) })
    }
  return rows
}

/**
 * Inputs the Python port REJECTS with a ValueError, although the TS does not validate them.
 * Each TS outcome is recorded as { value } or { throws } so the Python docstrings' account
 * of it (correct limits at S = 0 / K = 0, NaN, silent zeros, throws) stays pinned to fact.
 */
function invalidInputGoldens() {
  const outcome = <T>(f: () => T): { value: T } | { throws: string } => {
    try {
      return { value: f() }
    } catch (e) {
      return { throws: `${(e as Error).name}: ${(e as Error).message}` }
    }
  }
  // [S, K]: zero strike, zero spot (K ≤ H and K > H for an up barrier), both zero, negatives.
  const levels: [number, number][] = [[100, 0], [0, 100], [0, 120], [0, 0], [-1, 100], [100, -1]]
  const market = { T: 1, r: 0.05, q: 0.02, sigma: 0.2 }

  const digital: unknown[] = []
  for (const [S, K] of levels)
    for (const type of TYPES) {
      const i: DigitalInputs = { ...market, S, K, type, cash: 1 }
      digital.push({
        inputs: i,
        cash: outcome(() => cashOrNothingPrice(i)),
        asset: outcome(() => assetOrNothingPrice(i)),
      })
    }

  const barrier: unknown[] = []
  for (const [S, K] of levels)
    for (const kind of KINDS)
      for (const type of TYPES) {
        const i: BarrierInputs = { ...market, S, K, type, kind, H: kind.startsWith('down') ? 90 : 110 }
        barrier.push({ inputs: i, price: outcome(() => barrierPrice(i)) })
      }

  const vs = { S: 100, T: 0.5, r: 0.04, q: 0.01 }
  const varswap = [
    { ...vs, T: 0 },
    { ...vs, T: -0.1 },
    { ...vs, nStrikes: 1 },
    { ...vs, nStrikes: 0 },
    { ...vs, nStrikes: -3 },
  ].map((c) => ({
    inputs: c,
    result: outcome(() => {
      const res = priceVarianceSwap({ ...c, volFor: () => 0.2 })
      return { fairVariance: res.fairVariance, stripLength: res.strip.length }
    }),
  }))

  const ac: AutocallInputs = {
    S: 100, S0: 100, sigma: 0.2, r: 0.04, q: 0.01, maturity: 3, nObs: 3, couponRate: 0.06,
    autocallBarrier: 1.0, couponBarrier: 0.7, protectionBarrier: 0.7, memory: true, notional: 100,
  }
  const autocall = [
    { inputs: ac, paths: 0 },
    { inputs: { ...ac, nObs: 0 }, paths: 1000 },
    { inputs: { ...ac, nObs: -1 }, paths: 1000 },
    { inputs: { ...ac, maturity: 0 }, paths: 1000 },
    { inputs: { ...ac, maturity: 0, S: 90 }, paths: 1000 },
    { inputs: { ...ac, maturity: -1 }, paths: 1000 },
    { inputs: { ...ac, S0: 0 }, paths: 1000 },
    { inputs: { ...ac, S0: -100 }, paths: 1000 },
    { inputs: { ...ac, S0: 0, nObs: 1 }, paths: 1000 },
  ].map((c) => ({ ...c, result: outcome(() => priceAutocall(c.inputs, c.paths)) }))

  return { digital, barrier, varswap, autocall }
}

it('exports exotics goldens', () => {
  writeGolden(
    'exotics',
    enc({
      barrier: barrierGoldens(),
      digital: digitalGoldens(),
      varswap: varswapGoldens(),
      autocall: autocallGoldens(),
      mc: mcGoldens(),
      numericGreeks: numericGreeksGoldens(),
      invalidInputs: invalidInputGoldens(),
    }),
  )
})
