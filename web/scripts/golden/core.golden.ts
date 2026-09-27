/**
 * Golden values for the vanilla core: normal CDF/PDF, bsmCore intermediates, BSM prices
 * and every raw greek over a grid of inputs covering ATM/ITM/OTM, short/long expiries,
 * q = 0 and q ≠ 0, and the T → 0 / σ → 0 floors. Plus the seeded RNG streams.
 */
import { normCdf, normPdf } from '../../src/engine/mathUtils'
import { bsmCore } from '../../src/engine/bsm'
import { rawGreeks } from '../../src/engine/greeks'
import { mulberry32, makeNormal } from '../../src/engine/exotics/mc'
import type { BsmInputs, OptionType } from '../../src/engine/types'
import { writeGolden } from './writeGolden'

it('exports core goldens', () => {
  const xs: number[] = []
  for (let x = -40; x <= 40; x += 0.73) xs.push(x)
  xs.push(0, -1e-9, 1e-9, 7.07106781186547, -7.07106781186547, 37, -37, 37.5, -37.5)

  const inputs: BsmInputs[] = []
  const spots = [60, 95, 100, 105, 160, 6312.45]
  const strikes = [100, 6300]
  const expiries = [0, 1 / 365, 30 / 365, 1, 3]
  const vols = [0, 0.146, 0.2, 0.6]
  const carries: [number, number][] = [[0.05, 0], [0.043, 0.013], [-0.005, 0.03]]
  for (const S of spots)
    for (const K of strikes)
      for (const T of expiries)
        for (const sigma of vols)
          for (const [r, q] of carries) {
            // keep the grid meaningful: pair index-level spots with index-level strikes
            if ((S > 1000) !== (K > 1000)) continue
            inputs.push({ S, K, T, r, q, sigma })
          }

  const types: OptionType[] = ['call', 'put']
  const options = inputs.flatMap((i) =>
    types.map((type) => {
      const raw = rawGreeks(i, type)
      return { inputs: i, type, raw }
    }),
  )
  const cores = inputs.map((i) => ({ inputs: i, core: bsmCore(i) }))

  const rngStreams = [0, 1, 42, 0x5eed, 123456789, 4294967295, -7].map((seed) => {
    const u = mulberry32(seed)
    const uniforms = Array.from({ length: 64 }, () => u())
    const nrm = makeNormal(mulberry32(seed))
    const normals = Array.from({ length: 257 }, () => nrm())
    return { seed, uniforms, normals }
  })

  writeGolden('core', {
    norm: xs.map((x) => ({ x, cdf: normCdf(x), pdf: normPdf(x) })),
    cores,
    options,
    rng: rngStreams,
  })
})
