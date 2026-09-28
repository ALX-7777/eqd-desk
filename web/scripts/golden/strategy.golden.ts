/**
 * Golden values for the strategy builder engine (strategy.ts + presets.ts): every preset
 * built over a few spot / tenor / width / strike-grid configurations (incl. an index-level
 * grid and a rounding tie), each analysed at two spots (aggregate price, raw + reported
 * greeks, and the per-leg breakdown), plus the payoff profile, front expiry, premium and
 * leg/position values at several calendar times. A hand-built mixed-expiry position (with
 * an already-expired leg and fractional quantities) and the empty position cover the edges.
 */
import {
  analyzePosition,
  frontExpiry,
  legValueAt,
  payoffProfile,
  positionPremium,
  positionValueAt,
  type Leg,
  type MarketParams,
  type PositionAnalysis,
} from '../../src/engine/strategy'
import { buildPreset, PRESETS, type PresetParams } from '../../src/engine/presets'
import { writeGolden } from './writeGolden'

/**
 * Deterministic skew + term-structure vol provider centred on S0. Reproduced verbatim (same
 * operation order) in tests/parity/test_strategy_parity.py.
 */
const skewTermVol = (S0: number) => (K: number, T: number) =>
  0.18 - 0.25 * Math.log(K / S0) + 0.03 * Math.sqrt(T)

/** Aggregate outputs; the per-leg breakdown only when `withLegs` (keeps the file small). */
function analysisOut(a: PositionAnalysis, withLegs = true) {
  return {
    price: a.price,
    raw: a.raw,
    reported: a.reported,
    legs: withLegs
      ? a.legs.map((la) => ({ signedQty: la.signedQty, inputs: la.inputs, unit: la.unit }))
      : [],
  }
}

function payoffOut(legs: Leg[], m: MarketParams, sLo: number, sHi: number, n: number) {
  const pts = payoffProfile(legs, m, sLo, sHi, n)
  return {
    sLo,
    sHi,
    n,
    S: pts.map((p) => p.S),
    expiryPnl: pts.map((p) => p.expiryPnl),
    nowPnl: pts.map((p) => p.nowPnl),
  }
}

/** Leg-by-leg and total values on a small (spot × calendar-time) grid. */
function valuesOut(legs: Leg[], m: MarketParams) {
  const front = frontExpiry(legs)
  const times = [0, front / 2, front, front + 30 / 365]
  const spots = [0.9 * m.S, m.S, 1.1 * m.S]
  return times.flatMap((atT) =>
    spots.map((S) => ({
      S,
      atT,
      total: positionValueAt(legs, S, atT, m),
      perLeg: legs.map((l) => legValueAt(l, S, atT, m)),
    })),
  )
}

function positionOut(legs: Leg[], m: MarketParams, n: number) {
  const shifted: MarketParams = { ...m, S: 0.97 * m.S }
  return {
    market: m,
    legs,
    frontExpiry: frontExpiry(legs),
    premium: positionPremium(legs, m),
    analysis: analysisOut(analyzePosition(legs, m)),
    shiftedMarket: shifted,
    shiftedAnalysis: analysisOut(analyzePosition(legs, shifted), false),
    payoff: payoffOut(legs, m, 0.7 * m.S, 1.3 * m.S, n),
    values: valuesOut(legs, m),
  }
}

it('exports strategy goldens', () => {
  const configs: { params: Omit<PresetParams, 'volFor'>; r: number; q: number }[] = [
    { params: { S: 100, baseT: 0.25, widthPct: 0.05, strikeStep: 5 }, r: 0.04, q: 0.01 },
    { params: { S: 100, baseT: 30 / 365, widthPct: 0.03, strikeStep: 1 }, r: 0.04, q: 0.01 },
    { params: { S: 6312.45, baseT: 30 / 365, widthPct: 0.05, strikeStep: 25 }, r: 0.043, q: 0.013 },
    { params: { S: 6312.45, baseT: 0.5, widthPct: 0.02, strikeStep: 25 }, r: 0.043, q: 0.013 },
    // 6312.5 / 25 = 252.5 exactly: a rounding tie (JS Math.round → up → atm 6325)
    { params: { S: 6312.5, baseT: 0.25, widthPct: 0.04, strikeStep: 25 }, r: -0.005, q: 0.03 },
  ]

  const presets = configs.flatMap(({ params, r, q }) =>
    PRESETS.map(({ name }) => {
      const legs = buildPreset(name, { ...params, volFor: skewTermVol(params.S) })
      const m: MarketParams = { S: params.S, r, q }
      return { name, params, ...positionOut(legs, m, 30) }
    }),
  )

  // Hand-built: mixed expiries, fractional quantities, an already-expired leg (T = 0), a
  // near-zero-vol leg, and a leg that expires inside the front-expiry horizon of the others.
  const custom: Leg[] = [
    { id: 'c0', type: 'call', side: 'long', quantity: 1.5, K: 102, T: 0.4, sigma: 0.22 },
    { id: 'c1', type: 'put', side: 'short', quantity: 2, K: 95, T: 0.1, sigma: 0.27 },
    { id: 'c2', type: 'put', side: 'long', quantity: 0.25, K: 110, T: 0, sigma: 0.2 },
    { id: 'c3', type: 'call', side: 'short', quantity: 3, K: 90, T: 1.25, sigma: 1e-9 },
    { id: 'c4', type: 'put', side: 'long', quantity: 1, K: 100, T: 2, sigma: 0.35 },
  ]
  const customPos = positionOut(custom, { S: 100, r: 0.05, q: 0.02 }, 40)
  // The same book without the expired leg, so the front expiry (0.1) is non-trivial.
  const alive = positionOut(
    custom.filter((l) => l.T > 0),
    { S: 100, r: 0.05, q: 0.02 },
    40,
  )

  const emptyM: MarketParams = { S: 100, r: 0.04, q: 0.01 }
  const empty = {
    market: emptyM,
    frontExpiry: frontExpiry([]),
    premium: positionPremium([], emptyM),
    analysis: analysisOut(analyzePosition([], emptyM)),
    payoff: payoffOut([], emptyM, 80, 120, 4),
  }

  writeGolden('strategy', {
    presetList: PRESETS,
    presets,
    custom: customPos,
    customAlive: alive,
    empty,
  })
})
