/**
 * Monte-Carlo primitives for the path-dependent exotics. Everything is driven by
 * a SEEDED RNG so prices are reproducible and bump-greeks can reuse the same
 * draws (common random numbers) — without that, sampling noise swamps the
 * finite differences.
 */

/** mulberry32 — a small, fast, well-distributed seeded PRNG returning [0,1). */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Standard-normal sampler (Marsaglia polar method) over a uniform RNG. */
export function makeNormal(rng: () => number): () => number {
  let spare: number | null = null
  return function (): number {
    if (spare !== null) {
      const v = spare
      spare = null
      return v
    }
    let u = 0
    let v = 0
    let s = 0
    do {
      u = 2 * rng() - 1
      v = 2 * rng() - 1
      s = u * u + v * v
    } while (s >= 1 || s === 0)
    const mul = Math.sqrt((-2 * Math.log(s)) / s)
    spare = v * mul
    return u * mul
  }
}

/**
 * Simulate the underlying at `nSteps` equally-spaced dates of length `dt` under
 * risk-neutral GBM: S_{t+dt} = S_t·exp((r−q−σ²/2)·dt + σ√dt·Z). Returns the level
 * at each step (the exact distribution at those dates — fine for discretely
 * observed payoffs).
 */
export function simulateObsPath(
  S0: number,
  r: number,
  q: number,
  sigma: number,
  dt: number,
  nSteps: number,
  normal: () => number,
  out: number[],
): void {
  const drift = (r - q - 0.5 * sigma * sigma) * dt
  const vol = sigma * Math.sqrt(dt)
  let s = S0
  for (let i = 0; i < nSteps; i++) {
    s = s * Math.exp(drift + vol * normal())
    out[i] = s
  }
}
