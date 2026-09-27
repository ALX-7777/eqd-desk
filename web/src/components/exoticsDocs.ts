/**
 * Education content for the Phase 3 exotics — what each instrument is, the
 * behaviour that makes it interesting (and dangerous), and the key risk. These
 * are the teaching points the spec calls out: digital pin risk, barrier gamma
 * explosion, autocall path-dependence, and the variance-swap / VIX link.
 */

export type ExoticKind = 'digital' | 'barrier' | 'autocall' | 'varswap'

/** The price + greeks an exotic computes (subset of the vanilla greeks). */
export type ExoticMetric = 'price' | 'delta' | 'gamma' | 'vega' | 'theta' | 'rho'

export const EXOTIC_METRICS: ExoticMetric[] = ['price', 'delta', 'gamma', 'vega', 'theta', 'rho']

export interface ExoticDoc {
  kind: ExoticKind
  title: string
  /** What the instrument is and what view it expresses. */
  what: string
  /** The behaviour that matters — the teaching point. */
  behaviour: string
  /** The principal risk / why it's hard to hedge. */
  risk: string
}

export const EXOTIC_DOCS: Record<ExoticKind, ExoticDoc> = {
  digital: {
    kind: 'digital',
    title: 'Digital (binary) option',
    what: 'Pays a fixed cash amount if the underlying finishes beyond the strike — a bet on a LEVEL, not a magnitude. The building block of structured coupons (an autocall coupon is a digital).',
    behaviour:
      'A digital is the limit of an infinitely tight call spread: replicate it with (Q/Δ) call spreads of width Δ and let Δ → 0. Right at the strike near expiry, delta and gamma spike toward infinity — drag the spot across the strike and the payout flips from 0 to Q.',
    risk: 'Un-hedgeable pin risk at expiry: an arbitrarily small move across the strike changes the payout by the full Q. Desks over-hedge with a FINITE call spread and charge the spread width as a cushion — you cannot hold the exact digital delta near expiry.',
  },
  barrier: {
    kind: 'barrier',
    title: 'Barrier option',
    what: 'A vanilla that switches on (knock-in) or off (knock-out) if the underlying touches a barrier H. Cheaper than the vanilla — you give up the knocked-out states — so it is a popular way to cheapen a directional view. Closed-form under continuous monitoring; knock-in + knock-out = vanilla.',
    behaviour:
      'Near the barrier a knock-out’s value and delta collapse toward zero, so GAMMA EXPLODES there: the hedge flips violently as spot approaches H. That barrier region is where a barrier book lives or dies.',
    risk: 'Barrier / gap risk: a jump through the barrier can leave you badly mis-hedged. The closed form assumes continuous monitoring; real contracts monitor discretely, which is worth a continuity correction (the price sits between the discrete and continuous values).',
  },
  autocall: {
    kind: 'autocall',
    title: 'Autocallable (Phoenix)',
    what: 'A yield product: it pays periodic CONDITIONAL coupons and redeems early (autocalls) at par if the underlying is above the autocall barrier on an observation date. If it survives to maturity you are long the downside below a protection barrier.',
    behaviour:
      'Path-dependent — the cashflows depend on the whole observation path, not just the final spot — so it is priced by Monte Carlo. The early-redemption probability and the EXPECTED LIFE matter as much as the price; the yield comes from an embedded short down-and-in put.',
    risk: 'You are effectively short a put: a sell-off below the protection barrier turns the coupon stream into a capital loss (par·S/S0). The greeks shift as spot approaches the autocall and coupon barriers — discontinuously around the autocall level.',
  },
  varswap: {
    kind: 'varswap',
    title: 'Variance swap',
    what: 'Pays realised variance minus a fixed strike (the fair variance) — PURE exposure to realised volatility, with constant vega in variance terms and no path-dependent delta to manage.',
    behaviour:
      'Its fair variance is model-free: replicate the log contract with a STATIC strip of OTM options weighted 1/K². The 1/K² weighting overweights low-strike puts, so with equity skew the fair vol prints ABOVE the ATM vol. VIX² is essentially the fair variance of a 30-day S&P variance swap.',
    risk: 'You own the whole smile: a jump or a spike in realised vol is your P&L. The replication needs a continuum of strikes, so wing liquidity and strike truncation cause real-world tracking error (and make a true var swap behave differently from a vol swap in a crash).',
  },
}
