import { describe, it, expect } from 'vitest'
import {
  gbmLeverageProcess,
  MarketSimulator,
  realisedVol,
  volForStrike,
  DEFAULT_SIM_PARAMS,
  type MarketState,
} from '../market'
import { generateRFQ, singleOptionRfq, type RFQ } from '../rfq'
import { evaluateQuote } from '../quote'
import {
  emptyBook,
  addFill,
  hedgeToFlat,
  hedgeTrade,
  tradeOption,
  tradeStructure,
  flattenVega,
  flattenGamma,
  rfqFair,
  bookValue,
  bookGreeksRaw,
  type Book,
  type CostModel,
} from '../book'
import { pickWindow, replayState, windowSteps, type HistoryPoint } from '../replay'
import { adviseBook, rfqRiskImpact, jointHedge } from '../advisor'
import { attribute } from '../pnl'
import { mulberry32 } from '../../exotics/mc'
import { price as vanillaPrice } from '../../bsm'
import { buildPreset } from '../../presets'

const m0: MarketState = { t: 0, spot: 100, atmVol: 0.2, r: 0.03, q: 0.01 }
const fixedNormal = (vals: number[]) => {
  let i = 0
  return () => vals[i++ % vals.length]
}

describe('market simulation', () => {
  it('is reproducible with a fixed seed', () => {
    const a = new MarketSimulator(m0, DEFAULT_SIM_PARAMS, 123)
    const b = new MarketSimulator(m0, DEFAULT_SIM_PARAMS, 123)
    for (let i = 0; i < 10; i++) {
      expect(a.next().state.spot).toBe(b.next().state.spot)
    }
  })

  it('leverage: spot up ⇒ vol down, spot down ⇒ vol up', () => {
    const p = { ...DEFAULT_SIM_PARAMS, volMeanRev: 0, volOfVol: 0 }
    const up = gbmLeverageProcess.step(m0, p, fixedNormal([2, 0]))
    expect(up.spotReturn).toBeGreaterThan(0)
    expect(up.dVol).toBeLessThan(0)
    const dn = gbmLeverageProcess.step(m0, p, fixedNormal([-2, 0]))
    expect(dn.spotReturn).toBeLessThan(0)
    expect(dn.dVol).toBeGreaterThan(0)
  })

  it('keeps spot positive and vol within the floor/cap', () => {
    const sim = new MarketSimulator(m0, DEFAULT_SIM_PARAMS, 7)
    for (let i = 0; i < 300; i++) {
      const s = sim.next().state
      expect(s.spot).toBeGreaterThan(0)
      expect(s.atmVol).toBeGreaterThanOrEqual(0.05 - 1e-9)
      expect(s.atmVol).toBeLessThanOrEqual(1.2 + 1e-9)
    }
  })

  it('realised vol is ~0 for a constant-return path and positive for a noisy one', () => {
    const flat = Array.from({ length: 20 }, (_, k) => 100 * Math.exp(0.001 * k))
    expect(realisedVol(flat, 1 / 252)).toBeCloseTo(0, 6)
    const noisy = [100, 102, 99, 103, 98, 104, 97]
    expect(realisedVol(noisy, 1 / 252)).toBeGreaterThan(0)
    expect(realisedVol([100], 1 / 252)).toBeNull()
  })
})

describe('RFQ generation', () => {
  it('produces valid, reproducible single & structure requests', () => {
    const rng = mulberry32(99)
    let multiLeg = 0
    for (let n = 0; n < 80; n++) {
      const rfq = generateRFQ(100, 5, rng, n)
      expect(['buy', 'sell']).toContain(rfq.clientSide)
      expect(rfq.size).toBeGreaterThan(0)
      expect(rfq.legs.length).toBeGreaterThanOrEqual(1)
      if (rfq.legs.length > 1) multiLeg++
      for (const leg of rfq.legs) {
        expect(['call', 'put']).toContain(leg.type)
        expect(leg.K).toBeGreaterThan(0)
        expect(leg.T).toBeGreaterThan(0)
        expect(leg.ratio).toBeGreaterThan(0)
      }
    }
    expect(multiLeg).toBeGreaterThan(0) // some structures appear
    const r1 = generateRFQ(100, 5, mulberry32(1), 0)
    const r2 = generateRFQ(100, 5, mulberry32(1), 0)
    expect(r1).toEqual(r2)
  })
})

describe('quote / fill logic', () => {
  const rfqBuy = singleOptionRfq('call', 100, 0.25, 10, 'buy', 1)

  it('client buys only if your ask beats their noisy value; edge > 0 on fill', () => {
    const fair = 10 // net == gross for a single positive-priced option
    const win = evaluateQuote(rfqBuy, fair, fair, 0.04, 0.1, 0.5)
    expect(win.filled).toBe(true)
    expect(win.youSide).toBe('sell')
    expect(win.edge).toBeGreaterThan(0)
    const lose = evaluateQuote(rfqBuy, fair, fair, 0.04, 0.1, 0.0)
    expect(lose.filled).toBe(false)
    expect(lose.edge).toBe(0)
  })

  it('wider spread needs a more favourable client to fill (lower fill probability)', () => {
    const z = 0.3
    const tight = evaluateQuote(rfqBuy, 10, 10, 0.04, 0.1, z) // threshold 0.2 < 0.3 → fills
    const wide = evaluateQuote(rfqBuy, 10, 10, 0.08, 0.1, z) // threshold 0.4 > 0.3 → misses
    expect(tight.filled).toBe(true)
    expect(wide.filled).toBe(false)
  })
})

describe('book accounting', () => {
  it('empty book has zero value and greeks', () => {
    const b = emptyBook()
    expect(bookValue(b, m0)).toBe(0)
    expect(bookGreeksRaw(b, m0).delta).toBe(0)
  })

  it('selling a call to a client ⇒ short delta, cash in, value ≈ edge', () => {
    const rfq = singleOptionRfq('call', 100, 0.25, 10, 'buy', 1)
    // Quote around the REAL BSM fair (the book marks at the same value).
    const fair = vanillaPrice({ S: 100, K: 100, T: 0.25, r: 0.03, q: 0.01, sigma: 0.2 }, 'call')
    const fill = evaluateQuote(rfq, fair, fair, 0.06, 0.1, 1.0) // fills (you sell at ask)
    expect(fill.filled).toBe(true)
    const b = addFill(emptyBook(), fill, rfq, m0)
    expect(bookGreeksRaw(b, m0).delta).toBeLessThan(0) // short a call
    // value ≈ the edge captured (you sold above fair)
    expect(bookValue(b, m0)).toBeCloseTo(fill.edge, 6)
  })

  it('hedge-to-flat zeroes net delta and is value-neutral', () => {
    const rfq = singleOptionRfq('call', 100, 0.25, 50, 'buy', 1)
    const fill = evaluateQuote(rfq, 5, 5, 0.06, 0.1, 1.0)
    const b = addFill(emptyBook(), fill, rfq, m0)
    const valueBefore = bookValue(b, m0)
    const hedged = hedgeToFlat(b, m0)
    expect(bookGreeksRaw(hedged, m0).delta).toBeCloseTo(0, 6)
    expect(bookValue(hedged, m0)).toBeCloseTo(valueBefore, 6) // frictionless
  })
})

describe('P&L attribution', () => {
  // A 10-lot long call, no hedge.
  const book: Book = {
    trades: [{ id: 1, type: 'call', side: 'long', quantity: 10, K: 100, expiryTime: 0.5, tradedPrice: 5 }],
    underlyingQty: 0,
    cash: -50,
    realizedEdge: 0,
    totalCosts: 0,
    nextId: 2,
  }

  it('reconciles exactly: sum of terms + residual = total', () => {
    const after: MarketState = { t: 1 / 252, spot: 101.5, atmVol: 0.205, r: 0.03, q: 0.01 }
    const a = attribute(book, m0, after)
    const sum = a.delta + a.gamma + a.theta + a.vega + a.vanna + a.volga + a.residual
    expect(sum).toBeCloseTo(a.total, 9)
  })

  it('pure small spot move: delta+gamma explain it, residual is tiny', () => {
    const after: MarketState = { ...m0, spot: 100.5 } // dS only
    const a = attribute(book, m0, after)
    expect(Math.abs(a.residual)).toBeLessThan(1e-3 * Math.abs(a.total))
    expect(a.vega).toBeCloseTo(0, 12)
    expect(a.theta).toBeCloseTo(0, 12)
  })

  it('pure vol move: vega explains it, residual is tiny', () => {
    const after: MarketState = { ...m0, atmVol: 0.21 } // dVol only
    const a = attribute(book, m0, after)
    expect(a.delta).toBe(0)
    expect(Math.abs(a.vega)).toBeGreaterThan(0)
    expect(Math.abs(a.residual)).toBeLessThan(1e-2 * Math.abs(a.total))
  })

  it('long gamma + delta-hedged: P&L ≈ ½·Γ·ΔS² over a spot move', () => {
    const hedged = hedgeToFlat(book, m0) // delta-neutral
    const after: MarketState = { ...m0, spot: 103 }
    const a = attribute(hedged, m0, after)
    // delta term ~0 (hedged), gamma positive (long gamma), and it dominates
    expect(Math.abs(a.delta)).toBeLessThan(1e-6)
    expect(a.gamma).toBeGreaterThan(0)
    expect(a.total).toBeGreaterThan(0)
  })
})

const skewMarket: MarketState = { t: 0, spot: 100, atmVol: 0.2, r: 0.03, q: 0.01, skewSlope: -0.5, skewCurv: 0.4 }
const COSTS: CostModel = { underlyingHalfSpread: 0.0001, optionHalfSpread: 0.01 }

describe('skew surface', () => {
  it('downside puts price at higher vol than upside calls (equity skew)', () => {
    const F = 100 * Math.exp((0.03 - 0.01) * 0.25)
    const lowK = volForStrike(skewMarket, F * 0.9, 0.25)
    const atm = volForStrike(skewMarket, F, 0.25)
    const highK = volForStrike(skewMarket, F * 1.1, 0.25)
    expect(lowK).toBeGreaterThan(atm)
    expect(highK).toBeLessThan(atm)
    expect(atm).toBeCloseTo(0.2, 6)
  })
  it('flat surface ignores the strike', () => {
    const flat: MarketState = { t: 0, spot: 100, atmVol: 0.2, r: 0.03, q: 0.01 }
    expect(volForStrike(flat, 80, 0.5)).toBeCloseTo(0.2, 9)
    expect(volForStrike(flat, 120, 0.5)).toBeCloseTo(0.2, 9)
  })
})

describe('attribution reconciles with a live skew', () => {
  const book: Book = {
    trades: [
      { id: 1, type: 'put', side: 'short', quantity: 20, K: 90, expiryTime: 0.5, tradedPrice: 2 },
      { id: 2, type: 'call', side: 'long', quantity: 10, K: 110, expiryTime: 0.4, tradedPrice: 1.5 },
    ],
    underlyingQty: 5,
    cash: 0,
    realizedEdge: 0,
    totalCosts: 0,
    nextId: 3,
  }
  it('reconciles exactly; Taylor terms dominate the residual; vanna P&L is real', () => {
    const after: MarketState = { ...skewMarket, t: 1 / 252, spot: 99, atmVol: 0.21 }
    const a = attribute(book, skewMarket, after)
    expect(a.delta + a.gamma + a.theta + a.vega + a.vanna + a.volga + a.residual).toBeCloseTo(a.total, 9)
    const explained = Math.abs(a.delta) + Math.abs(a.gamma) + Math.abs(a.theta) + Math.abs(a.vega) + Math.abs(a.vanna) + Math.abs(a.volga)
    expect(Math.abs(a.residual)).toBeLessThan(0.2 * explained)
    expect(a.vanna).not.toBe(0) // skew ⇒ spot-vol cross P&L
  })
})

describe('transaction costs & market hedges', () => {
  it('costed hedge-to-flat zeroes delta and reduces value by the spread', () => {
    const rfq = singleOptionRfq('call', 100, 0.25, 50, 'buy', 1)
    const fair = vanillaPrice({ S: 100, K: 100, T: 0.25, r: 0.03, q: 0.01, sigma: 0.2 }, 'call')
    const b = addFill(emptyBook(), evaluateQuote(rfq, fair, fair, 0.06, 0.1, 1.0), rfq, m0)
    const before = bookValue(b, m0)
    const hedged = hedgeToFlat(b, m0, COSTS)
    expect(bookGreeksRaw(hedged, m0).delta).toBeCloseTo(0, 6)
    expect(bookValue(hedged, m0)).toBeLessThan(before)
    expect(hedged.totalCosts).toBeGreaterThan(0)
  })

  it('trading an option in the market costs exactly the spread (no edge)', () => {
    const b = tradeOption(emptyBook(), { type: 'call', side: 'long', quantity: 10, K: 100, T: 0.25 }, m0, COSTS)
    expect(bookValue(b, m0)).toBeCloseTo(-b.totalCosts, 6)
    expect(b.totalCosts).toBeGreaterThan(0)
    expect(b.trades).toHaveLength(1)
  })

  it('flattenVega zeroes net vega; flattenGamma zeroes net gamma', () => {
    const rfq = singleOptionRfq('put', 95, 0.5, 30, 'sell', 1)
    const fair = vanillaPrice({ S: 100, K: 95, T: 0.5, r: 0.03, q: 0.01, sigma: 0.2 }, 'put')
    const b = addFill(emptyBook(), evaluateQuote(rfq, fair, fair, 0.06, 0.1, -1.0), rfq, m0)
    expect(bookGreeksRaw(flattenVega(b, m0, 0.25, COSTS), m0).vega).toBeCloseTo(0, 4)
    expect(bookGreeksRaw(flattenGamma(b, m0, 0.25, COSTS), m0).gamma).toBeCloseTo(0, 6)
  })

  it('tradeStructure books every leg of a structure and charges each cost', () => {
    const legs = buildPreset('straddle', { S: 100, baseT: 0.25, widthPct: 0.05, strikeStep: 5, volFor: () => 0.2 })
    const orders = legs.map((l) => ({ type: l.type, side: l.side, quantity: l.quantity * 5, K: l.K, T: l.T }))
    const b = tradeStructure(emptyBook(), orders, m0, COSTS)
    expect(b.trades).toHaveLength(2)
    expect(b.totalCosts).toBeGreaterThan(0)
    expect(bookGreeksRaw(b, m0).vega).toBeGreaterThan(0) // long straddle ⇒ long vega
  })
})

describe('desk advisor', () => {
  it('an empty book is balanced (ok)', () => {
    const a = adviseBook(emptyBook(), m0, 0.2)
    expect(a).toHaveLength(1)
    expect(a[0].severity).toBe('ok')
  })

  it('a large net delta yields a flatten-delta recommendation', () => {
    const b: Book = { ...emptyBook(), underlyingQty: 300 }
    const a = adviseBook(b, m0, 0.2)
    expect(a.some((x) => x.action === 'flatten-delta')).toBe(true)
  })

  it('short vega at low implied vol is a HIGH vega warning', () => {
    const lowVol: MarketState = { ...m0, atmVol: 0.1 }
    const b: Book = { ...emptyBook(), trades: [{ id: 1, type: 'call', side: 'short', quantity: 500, K: 100, expiryTime: 0.5, tradedPrice: 0 }] }
    const vega = adviseBook(b, lowVol, 0.08).find((x) => x.action === 'flatten-vega')
    expect(vega?.severity).toBe('high')
  })

  it('short gamma while realised > implied is the top (high) warning', () => {
    const b: Book = { ...emptyBook(), trades: [{ id: 1, type: 'call', side: 'short', quantity: 200, K: 100, expiryTime: 0.25, tradedPrice: 0 }] }
    const a = adviseBook(b, m0, 0.35) // realised 35% > implied 20%
    expect(a[0].severity).toBe('high')
    expect(a.some((x) => x.title.includes('Short gamma'))).toBe(true)
  })

  it('actionable advice carries a concrete hedge plan', () => {
    // long delta ⇒ a FUTURE plan to sell ≈ |delta|
    const dPlan = adviseBook({ ...emptyBook(), underlyingQty: 300 }, m0, 0.2, 5).find((x) => x.action === 'flatten-delta')?.plan
    expect(dPlan?.instrument).toBe('future')
    expect(dPlan?.side).toBe('sell')
    expect(dPlan?.quantity).toBeCloseTo(300, 0)
    // short vega ⇒ buy a 60-day ATM option
    const vBook: Book = { ...emptyBook(), trades: [{ id: 1, type: 'call', side: 'short', quantity: 500, K: 100, expiryTime: 0.5, tradedPrice: 0 }] }
    const vPlan = adviseBook(vBook, { ...m0, atmVol: 0.1 }, 0.08, 5).find((x) => x.action === 'flatten-vega')?.plan
    expect(vPlan?.instrument).toBe('option')
    expect(vPlan?.tenorDays).toBe(60)
    expect(vPlan?.side).toBe('buy')
    expect(vPlan?.quantity).toBeGreaterThan(0)
  })

  it('flags offsetting client flow as the cheapest hedge (axe)', () => {
    const shortVol: Book = {
      ...emptyBook(),
      trades: [
        { id: 1, type: 'call', side: 'short', quantity: 100, K: 100, expiryTime: 0.5, tradedPrice: 0 },
        { id: 2, type: 'put', side: 'short', quantity: 100, K: 100, expiryTime: 0.5, tradedPrice: 0 },
      ],
    }
    expect(bookGreeksRaw(shortVol, m0).vega).toBeLessThan(0) // short vol
    const legs = [
      { type: 'call' as const, side: 'long' as const, ratio: 1, K: 100, T: 0.5 },
      { type: 'put' as const, side: 'long' as const, ratio: 1, K: 100, T: 0.5 },
    ]
    // client SELLS you the straddle ⇒ you buy ⇒ long vega ⇒ offsets your short vega
    const sell: RFQ = { id: 9, label: 'Straddle', legs, size: 50, clientSide: 'sell', bornDay: 0 }
    // client BUYS the straddle ⇒ you sell ⇒ more short vega
    const buy: RFQ = { id: 10, label: 'Straddle', legs, size: 50, clientSide: 'buy', bornDay: 0 }
    expect(rfqRiskImpact(sell, shortVol, m0).verdict).toBe('hedges')
    expect(rfqRiskImpact(buy, shortVol, m0).verdict).toBe('adds')
  })

  it('combined hedge flattens delta, gamma and vega together', () => {
    // short straddle: short gamma AND short vega, plus some residual delta
    const book: Book = {
      ...emptyBook(),
      underlyingQty: 40,
      trades: [
        { id: 1, type: 'call', side: 'short', quantity: 100, K: 100, expiryTime: 0.5, tradedPrice: 0 },
        { id: 2, type: 'put', side: 'short', quantity: 80, K: 100, expiryTime: 0.5, tradedPrice: 0 },
      ],
    }
    const before = bookGreeksRaw(book, m0)
    expect(before.gamma).toBeLessThan(0)
    expect(before.vega).toBeLessThan(0)

    const jh = jointHedge(book, m0, 5)
    expect(jh.feasible).toBe(true)
    expect(jh.legs).toHaveLength(3)

    // apply the exact suggested legs and confirm all three greeks collapse to ~0
    let b = book
    for (const leg of jh.legs) {
      if (leg.instrument === 'option') {
        b = tradeOption(b, { type: leg.optionType!, side: leg.side === 'buy' ? 'long' : 'short', quantity: leg.quantity, K: leg.K!, T: leg.tenorDays! / 365 }, m0)
      } else {
        b = hedgeTrade(b, (leg.side === 'buy' ? 1 : -1) * leg.quantity, m0)
      }
    }
    const after = bookGreeksRaw(b, m0)
    expect(after.gamma).toBeCloseTo(0, 6)
    expect(after.vega).toBeCloseTo(0, 4)
    expect(after.delta).toBeCloseTo(0, 4)
  })
})

describe('structure RFQs', () => {
  const straddle: RFQ = {
    id: 1,
    label: 'Straddle',
    legs: [
      { type: 'call', side: 'long', ratio: 1, K: 100, T: 0.25 },
      { type: 'put', side: 'long', ratio: 1, K: 100, T: 0.25 },
    ],
    size: 10,
    clientSide: 'buy',
    bornDay: 0,
  }

  it('net/gross fair, a filled package books all legs, value ≈ edge', () => {
    const { net, gross } = rfqFair(straddle, m0)
    expect(net).toBeGreaterThan(0)
    expect(gross).toBeGreaterThanOrEqual(net - 1e-9)
    const fill = evaluateQuote(straddle, net, gross, 0.06, 0.1, 1.0)
    expect(fill.filled).toBe(true)
    const b = addFill(emptyBook(), fill, straddle, m0)
    expect(b.trades).toHaveLength(2)
    expect(bookGreeksRaw(b, m0).vega).toBeLessThan(0) // client bought ⇒ you short vol
    expect(bookValue(b, m0)).toBeCloseTo(fill.edge, 6)
  })

  it('a credit structure (risk reversal) still quotes via gross', () => {
    const rr: RFQ = {
      id: 2,
      label: 'Risk reversal',
      legs: [
        { type: 'put', side: 'short', ratio: 1, K: 90, T: 0.5 },
        { type: 'call', side: 'long', ratio: 1, K: 110, T: 0.5 },
      ],
      size: 10,
      clientSide: 'buy',
      bornDay: 0,
    }
    const { net, gross } = rfqFair(rr, m0)
    expect(gross).toBeGreaterThan(Math.abs(net)) // gross defined even if net ≈ 0
    const fill = evaluateQuote(rr, net, gross, 0.08, 0.1, 2.0)
    expect(fill.filled).toBe(true)
    expect(addFill(emptyBook(), fill, rr, m0).trades).toHaveLength(2)
  })
})

describe('historical replay', () => {
  const series: HistoryPoint[] = Array.from({ length: 200 }, (_, k) => ({ date: `d${k}`, spot: 3000 + k * 5, vix: 15 + (k % 10) }))
  const base = { r: 0.03, q: 0.01, skewSlope: -0.4, skewCurv: 0.5, dt: 1 / 252 }

  it('picks a window and maps points to market states (VIX/100 = ATM vol)', () => {
    const win = pickWindow(series, 60, 0.5)
    expect(windowSteps(win)).toBe(60)
    const s0 = replayState(win, 0, base)
    expect(s0.spot).toBe(win.points[0].spot)
    expect(s0.atmVol).toBeCloseTo(win.points[0].vix / 100, 9)
    expect(s0.skewSlope).toBe(-0.4)
    expect(replayState(win, 5, base).t).toBeCloseTo(5 / 252, 9)
    // clamps past the end
    expect(replayState(win, 999, base).spot).toBe(win.points[win.points.length - 1].spot)
  })
})
