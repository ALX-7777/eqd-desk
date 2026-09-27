/**
 * Shared numeric (bump) greeks for the exotics. The spec allows exotic greeks "by
 * bumping"; this is the one place we do it, so every exotic just supplies a price
 * function of (S, σ, T, r) with its other parameters captured.
 *
 * Returned greeks are in the SAME desk-reporting units as the vanilla engine:
 *   delta, gamma  — per $1 of spot
 *   vega          — per 1 vol point   (raw ∂/∂σ ÷ 100)
 *   theta         — per calendar day  (−∂/∂T ÷ 365)
 *   rho           — per 1 rate point  (raw ∂/∂r ÷ 100)
 *
 * For Monte-Carlo pricers, pass a price function that reuses a FIXED seed so the
 * same random draws are used across bumps (common random numbers) — otherwise the
 * sampling noise swamps the finite differences.
 */

export interface ExoticGreeks {
  price: number
  delta: number
  gamma: number
  vega: number
  theta: number
  rho: number
}

/** Price as a function of the four bumped market variables (other params captured). */
export type PriceFn = (S: number, sigma: number, T: number, r: number) => number

export function numericGreeks(
  price: PriceFn,
  S: number,
  sigma: number,
  T: number,
  r: number,
): ExoticGreeks {
  const hS = 1e-4 * S
  const hSig = 1e-4
  const hT = 1e-5
  const hr = 1e-6

  const p0 = price(S, sigma, T, r)
  const delta = (price(S + hS, sigma, T, r) - price(S - hS, sigma, T, r)) / (2 * hS)
  const gamma =
    (price(S + hS, sigma, T, r) - 2 * p0 + price(S - hS, sigma, T, r)) / (hS * hS)
  const vegaRaw = (price(S, sigma + hSig, T, r) - price(S, sigma - hSig, T, r)) / (2 * hSig)
  // theta = ∂/∂t = −∂/∂T; guard T so we never bump below ~0.
  const hTeff = Math.min(hT, T / 2)
  const thetaRaw =
    -(price(S, sigma, T + hTeff, r) - price(S, sigma, T - hTeff, r)) / (2 * hTeff)
  const rhoRaw = (price(S, sigma, T, r + hr) - price(S, sigma, T, r - hr)) / (2 * hr)

  return {
    price: p0,
    delta,
    gamma,
    vega: vegaRaw / 100,
    theta: thetaRaw / 365,
    rho: rhoRaw / 100,
  }
}
