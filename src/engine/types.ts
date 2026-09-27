/**
 * Shared types for the pricing/greeks engine.
 *
 * The engine is pure: every function here is a documented mathematical map from
 * `BsmInputs` to numbers. No UI, no I/O, no global state.
 */

/** Vanilla European option flavour. */
export type OptionType = 'call' | 'put'

/**
 * Inputs to Black–Scholes–Merton with a continuous dividend yield.
 *
 * Units:
 *  - `S`, `K`     : price level (same currency as the option premium).
 *  - `T`          : time to expiry as a YEAR FRACTION (e.g. 0.25 = 3 months).
 *  - `r`, `q`     : continuously-compounded rate / dividend yield, as decimals
 *                   (0.05 = 5%).
 *  - `sigma`      : volatility as a decimal (0.20 = 20% annualised).
 */
export interface BsmInputs {
  /** Spot price of the underlying (> 0). */
  S: number
  /** Strike (> 0). */
  K: number
  /** Time to expiry in years (>= 0). */
  T: number
  /** Continuously-compounded risk-free rate (decimal). */
  r: number
  /** Continuously-compounded dividend yield (decimal). */
  q: number
  /** Volatility (decimal, >= 0). */
  sigma: number
}

/**
 * Greeks in their RAW mathematical units — exact partial derivatives of the BSM
 * price, before any reporting convention is applied. The reporting layer
 * (`reporting.ts`) is the single place that rescales these to desk units.
 *
 * Raw units (per the natural variable):
 *  - delta : ∂V/∂S            per $1 of spot
 *  - gamma : ∂²V/∂S²          per $1 of spot, of delta
 *  - vega  : ∂V/∂σ            per 1.00 of vol (i.e. per 100 vol points)
 *  - theta : ∂V/∂t = −∂V/∂T   per 1.0 YEAR of calendar time (time-decay sign)
 *  - rho   : ∂V/∂r            per 1.00 of rate (i.e. per 100 bp... per 1.00)
 *  - vanna : ∂Δ/∂σ = ∂vega/∂S per 1.00 of vol
 *  - volga : ∂vega/∂σ         per 1.00 of vol
 *  - charm : ∂Δ/∂t = −∂Δ/∂T   per 1.0 year (delta decay)
 *  - speed : ∂Γ/∂S            per $1 of spot
 *  - color : ∂Γ/∂t = −∂Γ/∂T   per 1.0 year (gamma decay)
 */
export interface RawGreeks {
  /** Option premium (the price itself, carried alongside the greeks). */
  price: number
  delta: number
  gamma: number
  vega: number
  theta: number
  rho: number
  vanna: number
  volga: number
  charm: number
  speed: number
  color: number
}

/**
 * Greeks rescaled to conventional desk reporting units (see `reporting.ts` and
 * WORKLOG for the exact scale factors). Same field set as {@link RawGreeks}; the
 * numbers differ only by the documented unit conventions.
 */
export type ReportedGreeks = RawGreeks

/** A full analysis bundle: identical math, two unit conventions. */
export interface OptionAnalysis {
  inputs: BsmInputs
  type: OptionType
  raw: RawGreeks
  reported: ReportedGreeks
}
