/**
 * Desk advisor — reads the live book and the market and returns ranked, explained
 * hedging advice. Each actionable item carries a concrete HEDGE PLAN: the exact
 * instrument, side and quantity to trade, and why that instrument is the right
 * tool (future for delta, ATM for vega, short-dated ATM for gamma). Pure and
 * deterministic, so it is unit-tested.
 */

import { bookGreeks, bookGreeksRaw, type Book } from './book'
import { volForStrike, type MarketState } from './market'
import { rawGreeks } from '../greeks'
import type { OptionType } from '../types'
import type { RFQ } from './rfq'

export type AdviceAction = 'flatten-delta' | 'flatten-vega' | 'flatten-gamma' | null
export type Severity = 'high' | 'medium' | 'low' | 'ok'

/** A concrete trade that flattens the greek the advice is about. */
export interface HedgePlan {
  instrument: 'future' | 'option'
  side: 'buy' | 'sell'
  /** Suggested quantity (contracts / future units); round before trading. */
  quantity: number
  optionType?: OptionType
  K?: number
  tenorDays?: number
  /** Plain-language "what to do and why". */
  rationale: string
}

export interface Advice {
  severity: Severity
  title: string
  detail: string
  action: AdviceAction
  /** The concrete hedge to apply (load into the ticket). */
  plan?: HedgePlan
}

const RANK: Record<Severity, number> = { high: 0, medium: 1, low: 2, ok: 3 }
const money = (x: number) => Math.round(x).toLocaleString('en-US')
/** A signed dollar amount with the sign BEFORE the currency: -$644, $1,235. */
const signedDollars = (x: number) => {
  const v = Math.round(x)
  return `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString('en-US')}`
}
const pct = (x: number) => `${(x * 100).toFixed(1)}%`

/** How winning an RFQ (you take the opposite side) would move your net risk. */
export interface RiskImpact {
  dDelta: number
  dVega: number
  dGamma: number
  /** Whether winning it reduces, increases, or barely touches your dominant risk. */
  verdict: 'hedges' | 'adds' | 'neutral'
  /** One-line note + lean guidance. */
  note: string
}

/**
 * The cheapest hedge is offsetting client flow. For a live RFQ, compute the
 * greeks you'd pick up if you WON it, and judge whether that flattens your book
 * (lean in to win it) or piles on (quote wide / pass).
 */
export function rfqRiskImpact(rfq: RFQ, book: Book, market: MarketState): RiskImpact {
  const net = bookGreeksRaw(book, market)
  let dDelta = 0
  let dVega = 0
  let dGamma = 0
  for (const leg of rfq.legs) {
    // your signed direction if you win (opposite of the client on each leg)
    const yourSign = (rfq.clientSide === 'buy' ? -1 : 1) * (leg.side === 'long' ? 1 : -1)
    const qty = yourSign * leg.ratio * rfq.size
    const sigma = volForStrike(market, leg.K, leg.T)
    const g = rawGreeks({ S: market.spot, K: leg.K, T: leg.T, r: market.r, q: market.q, sigma }, leg.type)
    dDelta += qty * g.delta
    dVega += qty * g.vega
    dGamma += qty * g.gamma
  }

  const vegaMatters = Math.abs(net.vega) > 50
  const gammaMatters = Math.abs(net.gamma) > 1e-5
  const cutsVega = vegaMatters && Math.sign(dVega) !== Math.sign(net.vega) && Math.abs(dVega) > 0.08 * Math.abs(net.vega)
  const addsVega = vegaMatters && Math.sign(dVega) === Math.sign(net.vega) && Math.abs(dVega) > 0.08 * Math.abs(net.vega)
  const cutsGamma = gammaMatters && Math.sign(dGamma) !== Math.sign(net.gamma) && Math.abs(dGamma) > 0.08 * Math.abs(net.gamma)

  const winSide = rfq.clientSide === 'buy' ? 'lower your ask' : 'raise your bid'
  let verdict: RiskImpact['verdict'] = 'neutral'
  let note = 'Little impact on your book — price it for the edge.'
  if (cutsVega) {
    verdict = 'hedges'
    note = `Cuts your ${net.vega < 0 ? 'short' : 'long'} vega by ~${money(Math.abs(dVega) / 100)}/pt — lean in (${winSide}) to win it and get PAID to hedge.`
  } else if (cutsGamma) {
    verdict = 'hedges'
    note = `Brings ${net.gamma < 0 ? 'long' : 'short'} gamma that offsets your book — lean in (${winSide}) to win it.`
  } else if (addsVega) {
    verdict = 'adds'
    note = `Adds to your ${net.vega < 0 ? 'short' : 'long'} vega — quote it wide (defensive) or pass unless the edge is fat.`
  }
  return { dDelta, dVega, dGamma, verdict, note }
}

export function adviseBook(
  book: Book,
  market: MarketState,
  realisedVol: number | null,
  strikeStep = 1,
): Advice[] {
  const { reported, raw } = bookGreeks(book, market)
  const out: Advice[] = []
  const step = strikeStep > 0 ? strikeStep : 1
  const atmK = Math.round(market.spot / step) * step

  // Per-contract greeks of an ATM hedge option at a given tenor (raw units).
  const legGreeks = (tenorYears: number) => {
    const sigma = volForStrike(market, atmK, tenorYears)
    return rawGreeks({ S: market.spot, K: atmK, T: tenorYears, r: market.r, q: market.q, sigma }, 'call')
  }

  // 1) Directional risk — delta. Hedge with the future (cheapest, pure delta).
  const per1pct = reported.delta * market.spot * 0.01
  if (Math.abs(per1pct) > 150) {
    const longMkt = reported.delta > 0
    out.push({
      severity: Math.abs(per1pct) > 1200 ? 'high' : 'medium',
      title: `Directional risk — net Δ ${reported.delta.toFixed(1)}`,
      detail: `You're ${longMkt ? 'long' : 'short'} the market: a 1% ${longMkt ? 'drop' : 'rally'} costs roughly $${money(Math.abs(per1pct))}. Delta is the cheapest greek to remove — flatten it first, then look at your vol risk.`,
      action: 'flatten-delta',
      plan: {
        instrument: 'future',
        side: longMkt ? 'sell' : 'buy',
        quantity: Math.abs(reported.delta),
        rationale: `Use the index FUTURE, not options: it's delta-1 with no gamma, vega or theta and the tightest spread, so it kills pure directional risk without adding new greeks. ${longMkt ? 'Sell' : 'Buy'} ≈ ${money(Math.abs(reported.delta))} future units to bring net Δ ≈ 0.`,
      },
    })
  }

  // 2) Vol level — vega. Hedge with an ATM option (most vega per lot).
  if (Math.abs(reported.vega) > 100) {
    const shortVega = reported.vega < 0
    const lowVol = market.atmVol < 0.13
    let detail = `Vega ${reported.vega.toFixed(0)} → you ${shortVega ? 'lose' : 'gain'} about $${money(Math.abs(reported.vega))} per vol point. `
    if (shortVega && lowVol) detail += `Implied vol is low (${pct(market.atmVol)}); a sell-off would spike vol right when you're short it (leverage). Buy some vega back.`
    else if (shortVega) detail += `You're short vol — fine while calm, painful on a spike.`
    else detail += `You're long vol — you profit if implied rises, bleed if it drifts lower.`
    const lg = legGreeks(60 / 365)
    const n = lg.vega > 1e-9 ? Math.abs(raw.vega / lg.vega) : 0
    const buy = shortVega
    const signedDelta = (buy ? 1 : -1) * n * lg.delta
    out.push({
      severity: shortVega && lowVol ? 'high' : 'medium',
      title: `Vol exposure — vega ${reported.vega.toFixed(0)}/pt`,
      detail,
      action: 'flatten-vega',
      plan: n > 0 ? {
        instrument: 'option', optionType: 'call', K: atmK, tenorDays: 60, side: buy ? 'buy' : 'sell', quantity: n,
        rationale: `Vega is densest at-the-money, and a ~60-day ATM option is liquid and vega-rich (~$${(lg.vega / 100).toFixed(1)}/vol-pt per lot). ${buy ? 'Buy' : 'Sell'} ≈ ${money(n)} ATM ${atmK} call${n >= 2 ? 's' : ''} to offset your ${shortVega ? 'short' : 'long'} vega. Note it also brings some ${buy ? 'long' : 'short'} gamma and about ${money(signedDelta)} delta — clean that up with the future afterward.`,
      } : undefined,
    })
  }

  // 3) Gamma vs realised-vs-implied. Hedge with a SHORT-dated ATM option.
  if (Math.abs(raw.gamma) > 1e-7 && realisedVol != null) {
    const shortGamma = raw.gamma < 0
    const hotter = realisedVol > market.atmVol
    const lg = legGreeks(21 / 365)
    const n = lg.gamma > 1e-12 ? Math.abs(raw.gamma / lg.gamma) : 0
    const buy = shortGamma
    const signedVega = ((buy ? 1 : -1) * n * lg.vega) / 100
    const signedDelta = (buy ? 1 : -1) * n * lg.delta
    const gammaPlan: HedgePlan | undefined = n > 0 ? {
      instrument: 'option', optionType: 'call', K: atmK, tenorDays: 21, side: buy ? 'buy' : 'sell', quantity: n,
      rationale: `Gamma concentrates in SHORT-dated at-the-money options, so a ~21-day ATM option flattens gamma with the least vega baggage. ${buy ? 'Buy' : 'Sell'} ≈ ${money(n)} ATM ${atmK} call${n >= 2 ? 's' : ''}. It brings about ${signedDollars(signedVega)}/vol-pt of vega and ≈ ${money(signedDelta)} delta — re-hedge that delta with the future.`,
    } : undefined

    if (shortGamma && hotter) {
      out.push({
        severity: 'high',
        title: 'Short gamma into a moving market',
        detail: `Realised vol (${pct(realisedVol)}) is running ABOVE implied (${pct(market.atmVol)}) while you're short gamma — your delta-hedged P&L ≈ ½·Γ·S²·(realised²−implied²) is negative, so you bleed on every move. Buy gamma back, or widen your re-hedge band and quote wider.`,
        action: 'flatten-gamma',
        plan: gammaPlan,
      })
    } else if (!shortGamma && !hotter) {
      out.push({
        severity: 'low',
        title: 'Long gamma in a quiet tape',
        detail: `Realised (${pct(realisedVol)}) is below implied (${pct(market.atmVol)}) and you're long gamma — you're paying more theta than you scalp back. Accept it for the convexity, or trim.`,
        action: 'flatten-gamma',
        plan: gammaPlan,
      })
    } else if (shortGamma) {
      out.push({
        severity: 'medium',
        title: 'Short gamma — exposed to a jump',
        detail: `You're short gamma. It's quiet now (realised ${pct(realisedVol)} vs implied ${pct(market.atmVol)}), but a sudden move forces you to hedge into it at a loss. Keep size modest or buy a little gamma back.`,
        action: 'flatten-gamma',
        plan: gammaPlan,
      })
    }
  }

  // 4) Theta context (no direct hedge — it's the consequence of gamma/vega).
  if (Math.abs(reported.theta) > 40) {
    out.push({
      severity: 'low',
      title: `Time decay ${reported.theta.toFixed(0)}/day`,
      detail:
        reported.theta < 0
          ? `You pay $${money(Math.abs(reported.theta))}/day in theta — the rent for being long gamma/vega. Worth it only if the market moves enough to scalp it back.`
          : `You collect $${money(reported.theta)}/day, but that usually means short gamma: one big move can erase many days of decay.`,
      action: null,
    })
  }

  // 5) Hedging costs eating the edge.
  if (book.realizedEdge > 0 && book.totalCosts > 0.5 * book.realizedEdge) {
    out.push({
      severity: 'medium',
      title: 'Hedging is eating your edge',
      detail: `You've paid $${money(book.totalCosts)} in hedge costs against $${money(book.realizedEdge)} of captured edge. Every option hedge crosses the spread — prefer the cheaper future for delta and don't over-trim small greeks.`,
      action: null,
    })
  }

  // 6) Axe via flow — the cheapest hedge of all is offsetting client flow.
  if (Math.abs(reported.vega) > 100 || Math.abs(raw.gamma) > 1e-6) {
    const dominantVol = Math.abs(reported.vega) > 100
    const shortVega = reported.vega < 0
    const shortGamma = raw.gamma < 0
    const what = dominantVol
      ? shortVega
        ? 'a client SELLING you vol (a straddle / strangle / option you buy)'
        : 'a client BUYING vol from you'
      : shortGamma
        ? 'a client selling you short-dated options (you go long gamma)'
        : 'a client buying short-dated options from you'
    const lean = dominantVol
      ? shortVega
        ? 'lean your prices UP to win client SELLS'
        : 'lean DOWN to win client BUYS'
      : 'lean toward the side that lengthens your gamma'
    out.push({
      severity: 'low',
      title: 'Cheapest hedge: axe your quotes to the flow you want',
      detail: `Paying up in the market costs the spread every time. The cheapest hedge is the next client trade that offsets you — you cut risk AND get PAID the edge (a negative-cost hedge) instead of paying it. Wait for ${what}, and ${lean}. Each live RFQ in your queue is tagged ↓ (helps) or ↑ (hurts) so you can lean into the right flow.`,
      action: null,
    })
  }

  if (out.length === 0) {
    out.push({
      severity: 'ok',
      title: 'Book looks balanced',
      detail: `Net greeks are small — no pressing risk. Keep quoting two-way and capturing edge; re-check after a few fills or a market move.`,
      action: null,
    })
  }

  return out.sort((a, b) => RANK[a.severity] - RANK[b.severity])
}

/** One leg of a combined hedge. */
export interface JointLeg {
  instrument: 'future' | 'option'
  side: 'buy' | 'sell'
  quantity: number
  optionType?: OptionType
  K?: number
  tenorDays?: number
}

export interface JointHedge {
  feasible: boolean
  legs: JointLeg[]
  rationale: string
}

/**
 * A combined hedge that flattens DELTA, GAMMA and VEGA together, instead of one
 * greek at a time. Because an option moves all three at once, hedging greek-by-
 * greek chases its tail. We solve the 2×2 system for the quantities of a
 * SHORT-dated ATM (gamma-rich) and a LONG-dated ATM (vega-rich) that zero gamma
 * and vega simultaneously, then add the FUTURE (the only clean single-greek tool)
 * to mop up the residual delta — so the future always goes LAST.
 */
export function jointHedge(book: Book, market: MarketState, strikeStep = 1): JointHedge {
  const net = bookGreeksRaw(book, market)
  const step = strikeStep > 0 ? strikeStep : 1
  const atmK = Math.round(market.spot / step) * step
  const leg = (tenorYears: number) => {
    const sigma = volForStrike(market, atmK, tenorYears)
    return rawGreeks({ S: market.spot, K: atmK, T: tenorYears, r: market.r, q: market.q, sigma }, 'call')
  }
  const g1 = leg(21 / 365) // gamma-rich
  const g2 = leg(180 / 365) // vega-rich
  const det = g1.gamma * g2.vega - g2.gamma * g1.vega
  if (!Number.isFinite(det) || Math.abs(det) < 1e-14) return { feasible: false, legs: [], rationale: '' }

  // Solve [g1.γ g2.γ; g1.ν g2.ν]·[n1; n2] = [−net.γ; −net.ν]
  const n1 = (-net.gamma * g2.vega + net.vega * g2.gamma) / det
  const n2 = (-net.vega * g1.gamma + net.gamma * g1.vega) / det
  const nf = -(net.delta + n1 * g1.delta + n2 * g2.delta) // residual delta → future

  const f = (x: number) => Math.round(x).toLocaleString('en-US')
  const legs: JointLeg[] = [
    { instrument: 'option', optionType: 'call', K: atmK, tenorDays: 21, side: n1 >= 0 ? 'buy' : 'sell', quantity: Math.abs(n1) },
    { instrument: 'option', optionType: 'call', K: atmK, tenorDays: 180, side: n2 >= 0 ? 'buy' : 'sell', quantity: Math.abs(n2) },
    { instrument: 'future', side: nf >= 0 ? 'buy' : 'sell', quantity: Math.abs(nf) },
  ]
  const rationale = `Hedges interact — one option moves delta, gamma AND vega at once, so flattening greeks one at a time chases your tail. Solve them together: a SHORT-dated ATM (gamma-rich) and a LONG-dated ATM (vega-rich) zero your gamma and vega at the same time, then the FUTURE mops up the leftover delta and adds nothing else, so it goes last. Suggested: ${n1 >= 0 ? 'buy' : 'sell'} ${f(Math.abs(n1))} × 21d ATM ${atmK}, ${n2 >= 0 ? 'buy' : 'sell'} ${f(Math.abs(n2))} × 180d ATM ${atmK}, then ${nf >= 0 ? 'buy' : 'sell'} ${f(Math.abs(nf))} × future.`
  return { feasible: true, legs, rationale }
}
