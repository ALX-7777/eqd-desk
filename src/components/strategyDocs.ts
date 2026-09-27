/**
 * Education content for Phase 2 structures — the VIEW each one expresses, its
 * leg structure, greek signature, and the main risk. Desk-flavoured and concise.
 */

import type { PresetName } from '../engine'

export interface StrategyDoc {
  name: PresetName
  /** The market view it expresses. */
  view: string
  /** What the legs are. */
  structure: string
  /** Greek signature — what risks you actually own. */
  greeks: string
  /** The principal risk / max loss shape. */
  risk: string
}

export const STRATEGY_DOCS: Record<PresetName, StrategyDoc> = {
  'call-vertical': {
    name: 'call-vertical',
    view: 'Moderately bullish, with a budget. You want upside but refuse to pay full premium for an outright call.',
    structure: 'Long a lower-strike call, short a higher-strike call (same expiry). A debit spread.',
    greeks:
      'Positive delta that fades to zero above the short strike (your upside is capped). Net vega and gamma are small — you sold most of the convexity back. Theta is mild.',
    risk: 'Defined: max loss = the net debit; max gain = the strike width − debit. You trade unlimited upside for a cheaper entry.',
  },
  'put-vertical': {
    name: 'put-vertical',
    view: 'Moderately bearish with defined risk — the mirror of the bull call spread.',
    structure: 'Long a higher-strike put, short a lower-strike put (same expiry). A debit spread.',
    greeks:
      'Negative delta that flattens below the short strike. Small net vega/gamma; the short leg finances the long. Mild theta.',
    risk: 'Defined: max loss = the net debit; max gain = the strike width − debit.',
  },
  straddle: {
    name: 'straddle',
    view: 'You expect a big move but not its direction — a bet that REALISED vol will beat the implied vol you pay.',
    structure: 'Long a call and a long put at the same (ATM) strike and expiry.',
    greeks:
      'Delta ≈ 0 at the strike, long gamma and long vega (you own convexity and the vol level), and you pay for it with negative theta every day.',
    risk: 'Max loss = the premium paid, if spot pins the strike. The classic gamma-scalping / long-vol position.',
  },
  strangle: {
    name: 'strangle',
    view: 'A cheaper straddle: still a long-vol, big-move bet, but you need a LARGER move to pay off.',
    structure: 'Long an out-of-the-money put and a long out-of-the-money call (same expiry).',
    greeks:
      'Delta ≈ 0 between the strikes, long gamma and long vega, negative theta. Less premium than a straddle, but a wider dead zone.',
    risk: 'Max loss = the premium paid, across the whole zone between the strikes.',
  },
  'risk-reversal': {
    name: 'risk-reversal',
    view: 'Bullish AND a pure SKEW bet. You sell the (expensive) downside put to fund the (cheaper) upside call — you are short skew.',
    structure: 'Long an out-of-the-money call, short an out-of-the-money put. Often near-zero cost.',
    greeks:
      'Positive delta, and most importantly a big VANNA: with equity skew (spot down → vol up) your delta-hedge moves exactly when the market gaps. Low net premium but real tail risk.',
    risk: 'The short put gives unlimited downside if the market sells off — you are paid the skew to take that risk.',
  },
  butterfly: {
    name: 'butterfly',
    view: 'A pin / low-vol bet: you expect spot to sit near the body strike at expiry. A bet on the smile (vol-of-vol).',
    structure: 'Long one wing, short two body, long the other wing (all calls or all puts), wings symmetric.',
    greeks:
      'Near the body you are short gamma and long theta (time works for you); cheap and defined. Sensitive to the curvature of the vol smile.',
    risk: 'Defined: max loss = the small net debit; max gain peaks if spot lands exactly on the body strike at expiry.',
  },
  'iron-condor': {
    name: 'iron-condor',
    view: 'Range-bound: you collect premium betting spot stays between the short strikes. A short-vol / income structure.',
    structure: 'Short a put spread below and short a call spread above (long wings further out). A net credit.',
    greeks:
      'Short vega and short gamma with positive theta — you are paid to wait, and hurt by a big move in either direction.',
    risk: 'Defined: max gain = the credit; max loss = a wing width − credit if spot breaks through a short strike.',
  },
  calendar: {
    name: 'calendar',
    view: 'A TERM-STRUCTURE bet: sell rich front-month decay, own back-month vega. Profits if spot sits near the strike at the front expiry.',
    structure: 'Short the front-month option, long the back-month option at the same strike. A debit.',
    greeks:
      'Long vega (the back month dominates) and positive theta (the front decays faster). Value peaks at the strike at the front expiry — hence the tent-shaped payoff.',
    risk: 'Max loss ≈ the debit. Hurt by a large spot move away from the strike, or by back-month implied vol falling.',
  },
}
