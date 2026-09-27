/**
 * Education content — plain-language, desk-flavoured explanations for each greek
 * plus the key relationships a trainee must internalise. This is a first-class
 * feature (a visible panel, not tooltips). Kept as data so the UI can render it
 * consistently and the plot/readout can deep-link to the relevant entry.
 */

export type GreekKey =
  | 'price'
  | 'delta'
  | 'gamma'
  | 'vega'
  | 'theta'
  | 'rho'
  | 'vanna'
  | 'volga'
  | 'charm'
  | 'speed'
  | 'color'

/** The greeks in display order. */
export const GREEK_KEYS: GreekKey[] = [
  'price',
  'delta',
  'gamma',
  'vega',
  'theta',
  'rho',
  'vanna',
  'volga',
  'charm',
  'speed',
  'color',
]

/** Greeks the user can plot / explore (price is included — it's the premium curve). */
export const PLOTTABLE_KEYS: GreekKey[] = GREEK_KEYS

export interface GreekDoc {
  key: GreekKey
  /** e.g. "Delta (Δ)". */
  title: string
  /** Order of the derivative, for grouping. */
  order: 'value' | 'first' | 'second' | 'third'
  /** What it measures, in one line. */
  measures: string
  /** Sign and size intuition. */
  intuition: string
  /** When it is large / matters most. */
  whenLarge: string
  /** How a market-maker actually uses or hedges it. */
  desk: string
}

export const GREEK_DOCS: Record<GreekKey, GreekDoc> = {
  price: {
    key: 'price',
    title: 'Price (Premium)',
    order: 'value',
    measures: 'The fair value of the option today under Black–Scholes–Merton.',
    intuition:
      'Intrinsic value (how in-the-money you are, discounted) plus time value (the optionality). Always ≥ the discounted intrinsic; the gap is what you pay for convexity and the chance of finishing further ITM.',
    whenLarge:
      'Highest for deep ITM and for long-dated / high-vol options. Time value peaks around the money.',
    desk: 'The number you quote. You make a two-way market around it: bid a bit below, offer a bit above, and manage the risk you are left with.',
  },
  delta: {
    key: 'delta',
    title: 'Delta (Δ)',
    order: 'first',
    measures: 'Sensitivity of the option price to a $1 move in spot — the hedge ratio.',
    intuition:
      'Call delta runs 0 → e^(−qT) (≈0 → 1); put delta runs −e^(−qT) → 0. ATM ≈ ±0.5. It is also a rough risk-neutral probability of finishing ITM. Buy a call → positive delta (long the market).',
    whenLarge:
      'Approaches ±1 deep ITM near expiry, ~0 deep OTM. The transition is sharpest ATM as T → 0 (that steepness IS gamma).',
    desk: 'You hedge delta by trading the underlying (an index future proxy): short Δ units of the index against a long call to be delta-neutral, then re-hedge as Δ drifts.',
  },
  gamma: {
    key: 'gamma',
    title: 'Gamma (Γ)',
    order: 'second',
    measures: 'How fast delta itself changes as spot moves (convexity of the position).',
    intuition:
      'Long options are long gamma (Γ ≥ 0): your delta grows as spot rises and shrinks as it falls, so a delta-hedge mechanically buys low and sells high. That re-hedging harvests realised volatility — paid for with theta.',
    whenLarge:
      'Sharply peaked at-the-money and explodes as T → 0. A long-dated option has low, broad gamma; a 1-day ATM option has enormous gamma.',
    desk: 'Gamma scalping: long gamma + delta-hedging profits when realised vol beats the implied vol you paid. Near expiry, ATM gamma creates pin risk — delta whips between 0 and 1 around the strike.',
  },
  vega: {
    key: 'vega',
    title: 'Vega (ν)',
    order: 'first',
    measures: 'Sensitivity to a 1-point change in implied volatility.',
    intuition:
      'Long options are long vega (ν ≥ 0): higher implied vol → richer optionality → higher premium. Vega is the pure implied-vol exposure, independent of whether spot actually moves.',
    whenLarge:
      'Largest at-the-money and for LONG-dated options (vega scales with √T). Short-dated options have little vega but lots of gamma.',
    desk: 'Vega is the implied-vol play. You express a view on the level of the vol surface (the VIX/VSTOXX gauge) with longer-dated structures; you warehouse vega and hedge it with other options, not the underlying.',
  },
  theta: {
    key: 'theta',
    title: 'Theta (Θ)',
    order: 'first',
    measures: 'Time decay — how much value the option loses as one calendar day passes.',
    intuition:
      'Long options usually have negative theta: optionality bleeds away as expiry approaches. It is the rent you pay to be long gamma. Reported per calendar day (the engine uses ∂/∂t = −∂/∂T).',
    whenLarge:
      'Most negative for at-the-money, short-dated options — exactly where gamma is largest. The two are locked together by the BSM PDE.',
    desk: 'Theta vs gamma is the core trade-off: you collect/pay θ each day and earn/lose ½ΓS²·(realised² − implied²). Short-dated ATM = max theta and max gamma.',
  },
  rho: {
    key: 'rho',
    title: 'Rho (ρ)',
    order: 'first',
    measures: 'Sensitivity to a 1-point change in the risk-free rate.',
    intuition:
      'Calls are rho-positive, puts rho-negative (higher rates lift the forward). Usually the quietest greek for short-dated index options, but real for long-dated structures and for the carry (r − q) embedded in the forward.',
    whenLarge:
      'Grows with maturity and moneyness (scales with K·T·e^(−rT)). Matters for LEAPS and rate-sensitive books; small for weeklies.',
    desk: 'Index desks watch rho mostly through the forward and the financing/dividend basis (r − q); pure rate risk is hedged with rates instruments when a long-dated book accumulates it.',
  },
  vanna: {
    key: 'vanna',
    title: 'Vanna',
    order: 'second',
    measures: 'Cross-greek: how delta moves when vol moves (= how vega moves when spot moves).',
    intuition:
      'The link between spot risk and vol risk. Sign depends on moneyness (it flips through the money). With equity skew — where spot down tends to push vol up — vanna means your delta-hedge needs adjusting precisely when the market gaps.',
    whenLarge:
      'Largest in the wings (away from ATM, where d2 is sizeable) and for shorter maturities. Zero where d2 = 0.',
    desk: 'Vanna is the heart of skew/risk-reversal trading. A risk reversal (long call vs short put) is essentially a vanna position — a bet on how the surface tilts as spot moves.',
  },
  volga: {
    key: 'volga',
    title: 'Volga (Vomma)',
    order: 'second',
    measures: 'Convexity in volatility — how vega changes as implied vol changes (vol-of-vol).',
    intuition:
      'Long volga = long the wings: strangles and far-OTM options gain vega as vol rises, so they benefit from an unstable, moving vol surface. It is exactly zero where d1·d2 = 0.',
    whenLarge:
      'Largest for out-of-the-money options (where d1·d2 is big); near zero around the money.',
    desk: 'Volga prices the smile. A butterfly (long wings, short body) is a volga / vol-of-vol bet: it pays if implied vol is itself volatile.',
  },
  charm: {
    key: 'charm',
    title: 'Charm (Delta Decay)',
    order: 'second',
    measures: 'How delta drifts as one calendar day passes, with spot unchanged.',
    intuition:
      'Your hedge does not stand still in time: even on a flat day, delta moves. Charm tells you how much to re-hedge purely because the clock ticked.',
    whenLarge:
      'Largest for near-ATM options approaching expiry; notable across weekends (three days of decay at once).',
    desk: 'Desks pre-hedge charm into Friday/over weekends and around expiry so they are not forced to chase a drifting delta on Monday.',
  },
  speed: {
    key: 'speed',
    title: 'Speed',
    order: 'third',
    measures: 'Third-order: how gamma changes as spot moves (∂Γ/∂S).',
    intuition:
      'The rate of change of your convexity. For a single vanilla it is small, but across a large book — or near barriers and on big gap moves — speed governs how quickly your gamma profile shifts under you.',
    whenLarge: 'Largest near the money for short maturities, where gamma is most sharply peaked.',
    desk: 'Watched on big or path-dependent books: when gamma is itself moving fast, a static delta/gamma hedge degrades quickly and must be refreshed.',
  },
  color: {
    key: 'color',
    title: 'Color (Gamma Decay)',
    order: 'third',
    measures: 'How gamma changes as one calendar day passes (∂Γ/∂t).',
    intuition:
      'Gamma is not static in time: as expiry nears, an ATM option’s gamma concentrates and spikes, while away-from-money gamma fades. Color is that re-shaping of the gamma profile day by day.',
    whenLarge: 'Largest at-the-money close to expiry — the same region where pin risk lives.',
    desk: 'Tells you how your gamma (and therefore your scalping P&L and pin risk) will look tomorrow, so you can plan re-hedging into expiry.',
  },
}

export interface Relationship {
  title: string
  body: string
}

export const KEY_RELATIONSHIPS: Relationship[] = [
  {
    title: 'Gamma ↔ Theta (the BSM PDE)',
    body: 'They are two sides of one coin: Θ + ½σ²S²Γ + (r−q)SΔ − rV = 0. A delta-hedged option’s P&L over a small step is ≈ ½·Γ·S²·((ΔS/S)² − σ²·dt) — i.e. ½·Γ·S²·(realised vol² − implied vol²). Long gamma makes money when the market moves MORE than the implied vol you paid in theta; it loses when the market is calmer than implied.',
  },
  {
    title: 'Gamma vs Vega across maturities',
    body: 'Short-dated options are a gamma / realised-vol play: huge gamma, tiny vega — you live or die on day-to-day moves. Long-dated options are a vega / implied-vol play: little gamma, lots of vega — you live or die on the level of the vol surface. The same volatility view is expressed with a different instrument depending on the horizon.',
  },
  {
    title: 'Pin risk near expiry',
    body: 'As T → 0, ATM gamma, charm and color all blow up. Delta snaps between 0 and 1 across the strike, so a tiny spot move flips your hedge from flat to fully long/short. Hedging becomes violent and expensive — that is pin risk, and it is why the acceptance test watches ATM gamma spike as T shrinks.',
  },
  {
    title: 'Why the surface must move with spot',
    body: 'Equity skew is real: spot down → vol up (the leverage effect). That co-movement is what makes vanna (∂Δ/∂σ) and volga bite — your delta-hedge has to change exactly when the market gaps and vol jumps. A static surface would make skew cosmetic and teach the wrong lessons; later phases evolve the whole surface with the simulated path.',
  },
]
