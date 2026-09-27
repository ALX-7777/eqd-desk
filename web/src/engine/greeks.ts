/**
 * Analytic greeks for vanilla European options under BSM with continuous
 * dividend yield `q`. Every function is the exact partial derivative of the
 * pricer in bsm.ts, in RAW units (see types.ts / reporting.ts for unit scaling).
 *
 * Sign convention for the time greeks (theta, charm, color): we report
 * ∂/∂t = −∂/∂T, i.e. the change as CALENDAR TIME advances and time-to-expiry
 * shrinks. A long option therefore has negative theta in normal conditions.
 *
 * Each greek is validated against a central finite-difference bump of the
 * pricer in greeks.test.ts — that cross-check, not the algebra below, is the
 * source of truth for the sign conventions.
 *
 * Symmetric greeks (gamma, vega, vanna, volga, speed, color) are identical for
 * calls and puts — a consequence of put-call parity, whose extra term is linear
 * in S and constant in σ/T, so its higher derivatives vanish. Those functions
 * take no `type` argument by design.
 */

import { normCdf, normPdf } from './mathUtils'
import { bsmCore } from './bsm'
import type { BsmCore } from './bsm'
import type { BsmInputs, OptionType, RawGreeks } from './types'

// --- core-based implementations (compute bsmCore once, reuse everywhere) -----

function priceFromCore(c: BsmCore, i: BsmInputs, type: OptionType): number {
  return type === 'call'
    ? i.S * c.dfQ * normCdf(c.d1) - i.K * c.dfR * normCdf(c.d2)
    : i.K * c.dfR * normCdf(-c.d2) - i.S * c.dfQ * normCdf(-c.d1)
}

/** Δ = ∂V/∂S. Call: e^(−qT)·N(d1). Put: −e^(−qT)·N(−d1). */
function deltaFromCore(c: BsmCore, type: OptionType): number {
  return type === 'call' ? c.dfQ * normCdf(c.d1) : -c.dfQ * normCdf(-c.d1)
}

/** Γ = ∂²V/∂S² = e^(−qT)·φ(d1)/(S·σ·√T). Same for call and put; always ≥ 0. */
function gammaFromCore(c: BsmCore, S: number): number {
  return (c.dfQ * normPdf(c.d1)) / (S * c.volSqrtT)
}

/** vega = ∂V/∂σ = S·e^(−qT)·φ(d1)·√T (per 1.00 of vol). Same call/put; ≥ 0. */
function vegaFromCore(c: BsmCore, S: number): number {
  return S * c.dfQ * normPdf(c.d1) * c.sqrtT
}

/**
 * Θ = ∂V/∂t = −∂V/∂T (per year). Three terms: the always-negative time-value
 * bleed (same for call/put), a dividend-carry term, and a discount term.
 */
function thetaFromCore(c: BsmCore, i: BsmInputs, type: OptionType): number {
  const bleed = -(i.S * c.dfQ * normPdf(c.d1) * c.sigmaEff) / (2 * c.sqrtT)
  if (type === 'call') {
    return bleed + i.q * i.S * c.dfQ * normCdf(c.d1) - i.r * i.K * c.dfR * normCdf(c.d2)
  }
  return bleed - i.q * i.S * c.dfQ * normCdf(-c.d1) + i.r * i.K * c.dfR * normCdf(-c.d2)
}

/** ρ = ∂V/∂r (per 1.00 of rate). Call: K·T·e^(−rT)·N(d2). Put: −K·T·e^(−rT)·N(−d2). */
function rhoFromCore(c: BsmCore, i: BsmInputs, type: OptionType): number {
  return type === 'call'
    ? i.K * c.Teff * c.dfR * normCdf(c.d2)
    : -i.K * c.Teff * c.dfR * normCdf(-c.d2)
}

/** vanna = ∂Δ/∂σ = ∂vega/∂S = −e^(−qT)·φ(d1)·d2/σ. Same call/put. */
function vannaFromCore(c: BsmCore): number {
  return (-c.dfQ * normPdf(c.d1) * c.d2) / c.sigmaEff
}

/** volga (vomma) = ∂vega/∂σ = vega·d1·d2/σ. Same call/put. */
function volgaFromCore(c: BsmCore, S: number): number {
  const vega = vegaFromCore(c, S)
  return (vega * c.d1 * c.d2) / c.sigmaEff
}

/**
 * charm = ∂Δ/∂t = −∂Δ/∂T (delta decay, per year).
 *
 * Building block: ∂Δ_call/∂T = −q·e^(−qT)·N(d1) + `common`, where
 *   common = e^(−qT)·φ(d1)·[2(r−q)T − d2·σ√T] / (2T·σ√T) = e^(−qT)·φ(d1)·∂d1/∂T.
 * Negating for the time-decay convention gives the forms below (the dividend
 * term flips sign between call and put; `common` is shared). Validated by FD.
 */
function charmFromCore(c: BsmCore, i: BsmInputs, type: OptionType): number {
  const common =
    (c.dfQ * normPdf(c.d1) * (2 * (i.r - i.q) * c.Teff - c.d2 * c.volSqrtT)) /
    (2 * c.Teff * c.volSqrtT)
  return type === 'call'
    ? i.q * c.dfQ * normCdf(c.d1) - common
    : -i.q * c.dfQ * normCdf(-c.d1) - common
}

/** speed = ∂Γ/∂S = ∂³V/∂S³ = −(Γ/S)·(d1/(σ√T) + 1). Same call/put. */
function speedFromCore(c: BsmCore, S: number): number {
  const gamma = gammaFromCore(c, S)
  return (-gamma / S) * (c.d1 / c.volSqrtT + 1)
}

/**
 * color = ∂Γ/∂t = −∂Γ/∂T (gamma decay, per year)
 *   = e^(−qT)·φ(d1)/(2·S·T·σ√T) · [ 2qT + 1 + (2(r−q)T − d2·σ√T)·d1/(σ√T) ]
 * Same for call and put. The sign is already that of ∂/∂t — do not negate again.
 */
function colorFromCore(c: BsmCore, i: BsmInputs): number {
  const bracket =
    2 * i.q * c.Teff +
    1 +
    ((2 * (i.r - i.q) * c.Teff - c.d2 * c.volSqrtT) * c.d1) / c.volSqrtT
  return ((c.dfQ * normPdf(c.d1)) / (2 * i.S * c.Teff * c.volSqrtT)) * bracket
}

// --- public single-greek API ------------------------------------------------

export function delta(i: BsmInputs, type: OptionType): number {
  return deltaFromCore(bsmCore(i), type)
}
export function gamma(i: BsmInputs): number {
  return gammaFromCore(bsmCore(i), i.S)
}
export function vega(i: BsmInputs): number {
  return vegaFromCore(bsmCore(i), i.S)
}
export function theta(i: BsmInputs, type: OptionType): number {
  return thetaFromCore(bsmCore(i), i, type)
}
export function rho(i: BsmInputs, type: OptionType): number {
  return rhoFromCore(bsmCore(i), i, type)
}
export function vanna(i: BsmInputs): number {
  return vannaFromCore(bsmCore(i))
}
export function volga(i: BsmInputs): number {
  return volgaFromCore(bsmCore(i), i.S)
}
export function charm(i: BsmInputs, type: OptionType): number {
  return charmFromCore(bsmCore(i), i, type)
}
export function speed(i: BsmInputs): number {
  return speedFromCore(bsmCore(i), i.S)
}
export function color(i: BsmInputs): number {
  return colorFromCore(bsmCore(i), i)
}

/**
 * Compute price + every greek in one pass (one `bsmCore` evaluation). This is
 * what the UI calls on each input change. Returns RAW units; pass through
 * reporting.ts to get desk units.
 */
export function rawGreeks(i: BsmInputs, type: OptionType): RawGreeks {
  const c = bsmCore(i)
  return {
    price: priceFromCore(c, i, type),
    delta: deltaFromCore(c, type),
    gamma: gammaFromCore(c, i.S),
    vega: vegaFromCore(c, i.S),
    theta: thetaFromCore(c, i, type),
    rho: rhoFromCore(c, i, type),
    vanna: vannaFromCore(c),
    volga: volgaFromCore(c, i.S),
    charm: charmFromCore(c, i, type),
    speed: speedFromCore(c, i.S),
    color: colorFromCore(c, i),
  }
}
