/**
 * Golden values for the market-data layer: the underlying presets, the validated seed
 * snapshot, validateSnapshot on accepted / rejected variants (with the exact error
 * messages; incl. raw JSON text whose JSON.stringify / String() rendering differs from
 * Python's, and non-finite numbers), seedInputs (incl. Math.round ties), the vol surface (atmVol + getVol over a
 * strike x tenor grid, for the committed snapshot and custom snapshots that exercise the
 * T floor, VOL_FLOOR and the interpolation branches) and the historical replay series.
 */
import { UNDERLYINGS, DEFAULT_UNDERLYING } from '../../src/data/config'
import { snapshot, validateSnapshot, seedInputs } from '../../src/data/snapshot'
import type { MarketSnapshot } from '../../src/data/snapshot'
import { buildSurface, surface, VOL_FLOOR } from '../../src/data/volSurface'
import { historySeries, historyMeta } from '../../src/data/history'
import { writeGolden } from './writeGolden'

/** Deep plain copy (the raw JSON shape) we can freely edit. */
function base(): Record<string, unknown> {
  return JSON.parse(JSON.stringify(snapshot)) as Record<string, unknown>
}

function without(key: string): Record<string, unknown> {
  const b = base()
  delete b[key]
  return b
}

it('exports data goldens', () => {
  // --- validateSnapshot: accepted variants -------------------------------------------
  const accepted: { label: string; raw: unknown }[] = [
    { label: 'committed', raw: base() },
    { label: 'skew.atm missing', raw: { ...base(), skew: { slope: -0.3, curv: 0.4 } } },
    { label: 'skew.atm null', raw: { ...base(), skew: { atm: null, slope: -0.3, curv: 0.4 } } },
    { label: 'realized_vol null', raw: { ...base(), realized_vol: null } },
    { label: 'realized_vol missing', raw: without('realized_vol') },
    { label: 'term_structure not an array', raw: { ...base(), term_structure: 'abc' } },
    { label: 'term_structure empty', raw: { ...base(), term_structure: [] } },
    { label: 'source_notes missing', raw: without('source_notes') },
    { label: 'source_notes not an array', raw: { ...base(), source_notes: { a: 1 } } },
    { label: 'tickers missing', raw: without('tickers') },
    { label: 'tickers null', raw: { ...base(), tickers: null } },
    { label: 'tickers partial', raw: { ...base(), tickers: { vol_ticker: '^VIX' } } },
    {
      label: 'strings missing',
      raw: (() => {
        const b = base()
        for (const k of ['asof', 'underlying', 'name', 'currency']) delete b[k]
        return b
      })(),
    },
    { label: 'strings null', raw: { ...base(), asof: null, name: null } },
    { label: 'integer numbers', raw: { ...base(), spot: 5000, r: 0, q: 0, atm_vol_30d: 1 } },
    { label: 'negative r and q', raw: { ...base(), r: -0.005, q: -0.01 } },
    { label: 'extra keys ignored', raw: { ...base(), extra: 123, skew: { atm: 0.2, slope: -0.1, curv: 0.2, x: 1 } } },
  ]
  const validated = accepted.map(({ label, raw }) => ({ label, raw, snapshot: validateSnapshot(raw) }))

  // --- validateSnapshot: rejected variants -------------------------------------------
  const rejectedRaw: { label: string; raw: unknown }[] = [
    { label: 'null', raw: null },
    { label: 'string', raw: 'snapshot' },
    { label: 'number', raw: 42 },
    { label: 'boolean', raw: true },
    { label: 'spot negative', raw: { ...base(), spot: -1 } },
    { label: 'spot zero', raw: { ...base(), spot: 0 } },
    { label: 'spot missing', raw: without('spot') },
    { label: 'spot string', raw: { ...base(), spot: '6000' } },
    { label: 'spot boolean', raw: { ...base(), spot: true } },
    { label: 'spot null', raw: { ...base(), spot: null } },
    { label: 'atm_vol_30d string', raw: { ...base(), atm_vol_30d: 'x' } },
    { label: 'atm_vol_30d zero', raw: { ...base(), atm_vol_30d: 0 } },
    { label: 'atm_vol_30d negative', raw: { ...base(), atm_vol_30d: -0.1 } },
    { label: 'r undefined', raw: { ...base(), r: undefined } },
    { label: 'q null', raw: { ...base(), q: null } },
    { label: 'q array', raw: { ...base(), q: [0.01] } },
    { label: 'realized_vol string', raw: { ...base(), realized_vol: 'x' } },
    { label: 'skew null', raw: { ...base(), skew: null } },
    { label: 'skew missing', raw: without('skew') },
    { label: 'skew.atm string', raw: { ...base(), skew: { atm: 'hi', slope: -0.3, curv: 0.4 } } },
    { label: 'skew.curv missing', raw: { ...base(), skew: { atm: 0.2, slope: -0.3 } } },
    {
      label: 'term_structure[1].atm_iv string',
      raw: { ...base(), term_structure: [{ t: 0.1, atm_iv: 0.2 }, { t: 0.5, atm_iv: '0.2' }] },
    },
    { label: 'term_structure[0].t missing', raw: { ...base(), term_structure: [{ atm_iv: 0.2 }] } },
    { label: 'term_structure[0] empty object', raw: { ...base(), term_structure: [{}] } },
  ]
  const rejected = rejectedRaw.map(({ label, raw }) => {
    try {
      validateSnapshot(raw)
      throw new Error(`golden: expected ${label} to be rejected`)
    } catch (e) {
      return { label, raw: raw === undefined ? null : raw, error: (e as Error).message }
    }
  })

  // --- validateSnapshot on raw JSON TEXT ----------------------------------------------
  // Values whose JSON.parse / JSON.stringify / String() handling differs from Python's
  // json + str() (5.0 vs 5, 1e-7 vs 1e-07, true vs True, "€" vs "€", huge integer
  // literals = Infinity, JS object key order...). The TEXT is exported, so both sides parse
  // the same bytes. `@name@` placeholders are replaced by the raw JSON text given.
  const textOf = (obj: unknown, raws: Record<string, string>): string => {
    let text = JSON.stringify(obj)
    for (const [ph, raw] of Object.entries(raws)) text = text.replace(`"@${ph}@"`, raw)
    return text
  }
  const huge = '1' + '0'.repeat(400) // > max double: JSON.parse gives Infinity
  const rejectedTextRaw: { label: string; text: string }[] = [
    { label: 'q [5.0]', text: textOf({ ...base(), q: '@v@' }, { v: '[5.0]' }) },
    { label: 'q [1e-7]', text: textOf({ ...base(), q: '@v@' }, { v: '[1e-7]' }) },
    {
      label: 'q number layouts',
      text: textOf(
        { ...base(), q: '@v@' },
        { v: '[1e21, 1e20, 0.000001, 1e-7, -0.0, 0.1, 1.5e300, 5e-324, 123456789012345678901234]' },
      ),
    },
    { label: 'q non-finite literals', text: textOf({ ...base(), q: '@v@' }, { v: `[1e400, -1e400, ${huge}]` }) },
    { label: 'r huge integer literal', text: textOf({ ...base(), r: '@v@' }, { v: huge }) },
    { label: 'r 1e400', text: textOf({ ...base(), r: '@v@' }, { v: '1e400' }) },
    { label: 'spot -1e400', text: textOf({ ...base(), spot: '@v@' }, { v: '-1e400' }) },
    { label: 'spot non-ASCII string', text: textOf({ ...base(), spot: '€ é 😀' }, {}) },
    {
      label: 'spot string with escapes',
      text: textOf({ ...base(), spot: 'a"b\\c\n\t\u0001\u007f\u2028' }, {}),
    },
    { label: 'spot lone surrogate', text: textOf({ ...base(), spot: '@v@' }, { v: '"\\ud800x"' }) },
    {
      label: 'q object key order',
      text: textOf(
        { ...base(), q: '@v@' },
        { v: '{"b": 1, "10": 2, "2": 3, "a": [true, null, 2.50], "01": 4, "4294967295": 5, "4294967294": 6, "": 7}' },
      ),
    },
    { label: 'realized_vol false', text: textOf({ ...base(), realized_vol: false }, {}) },
    {
      label: 'skew.slope nested',
      text: textOf({ ...base(), skew: { atm: 0.2, slope: '@v@', curv: 0.4 } }, { v: '{"x": {"y": [1.50, "z", {}]}}' }),
    },
    {
      label: 'term_structure[0].atm_iv huge integer',
      text: textOf({ ...base(), term_structure: [{ t: 0.1, atm_iv: '@v@' }] }, { v: huge }),
    },
  ]
  const rejectedText = rejectedTextRaw.map(({ label, text }) => {
    try {
      validateSnapshot(JSON.parse(text))
      throw new Error(`golden: expected ${label} to be rejected`)
    } catch (e) {
      return { label, text, error: (e as Error).message }
    }
  })
  const validatedText = [
    {
      label: 'String() coercions',
      text: textOf(
        {
          ...base(),
          asof: '@asof@',
          underlying: '@und@',
          name: '@name@',
          currency: '@ccy@',
          tickers: '@tk@',
          source_notes: '@notes@',
        },
        {
          asof: 'true',
          und: 'false',
          name: '1.0',
          ccy: '[1, [2, null], 3.50]',
          tk: '{"index_ticker": 5.0, "vol_ticker": [], "options_proxy": {"a": 1}}',
          notes:
            '[true, false, 1.0, null, 1e21, 1e-7, 0.000001, -0.0, [1, [2, null]], {"a": 1}, "é€😀", 1e400, ' +
            huge +
            ', 123456789012345678901234]',
        },
      ),
    },
    {
      label: 'integral floats and huge-but-finite integers',
      text: textOf(
        { ...base(), spot: '@spot@', r: '@r@', atm_vol_30d: '@atm@' },
        { spot: '5000.0', r: '0.0', atm: '1' + '0'.repeat(300) },
      ),
    },
  ].map(({ label, text }) => ({ label, text, snapshot: validateSnapshot(JSON.parse(text)) }))

  // --- non-finite numbers (not expressible as JSON text) ------------------------------
  // `value` names the JS number; Python builds it with float(value).
  const nonFiniteRaw: { label: string; path: string[]; value: 'NaN' | 'Infinity' | '-Infinity' }[] = [
    { label: 'spot NaN', path: ['spot'], value: 'NaN' },
    { label: 'spot Infinity', path: ['spot'], value: 'Infinity' },
    { label: 'r Infinity', path: ['r'], value: 'Infinity' },
    { label: 'q -Infinity', path: ['q'], value: '-Infinity' },
    { label: 'atm_vol_30d NaN', path: ['atm_vol_30d'], value: 'NaN' },
    { label: 'realized_vol Infinity', path: ['realized_vol'], value: 'Infinity' },
    { label: 'skew.atm NaN', path: ['skew', 'atm'], value: 'NaN' },
    { label: 'skew.curv -Infinity', path: ['skew', 'curv'], value: '-Infinity' },
  ]
  const nonFinite = nonFiniteRaw.map(({ label, path, value }) => {
    const raw = base()
    const parent = (path.length === 1 ? raw : raw[path[0]]) as Record<string, unknown>
    parent[path[path.length - 1]] = Number(value)
    try {
      validateSnapshot(raw)
      throw new Error(`golden: expected ${label} to be rejected`)
    } catch (e) {
      return { label, path, value, error: (e as Error).message }
    }
  })
  const nonFiniteNotes = {
    values: ['NaN', 'Infinity', '-Infinity'],
    notes: validateSnapshot({ ...base(), source_notes: [NaN, Infinity, -Infinity] }).source_notes,
  }

  // --- seedInputs ---------------------------------------------------------------------
  const seedSpots = [6312.45, 6312.5, 6337.5, 6287.5, 5000, 100.5, 99.5, 12.5, 7.49, 1234.567]
  const seedSteps = [25, 1, 5, 10, 50, 100, 0.5, 7, 0.1]
  const seeds = [{ spot: snapshot.spot, step: 25, inputs: seedInputs() }]
  for (const spot of seedSpots)
    for (const step of seedSteps) {
      const s: MarketSnapshot = { ...snapshot, spot }
      seeds.push({ spot, step, inputs: seedInputs(s, step) })
    }

  // --- vol surface --------------------------------------------------------------------
  const Ts = [
    -1, 0, 1e-7, 1e-6, 2e-6, 0.01, 1 / 12, 0.0833, 0.1, 30 / 365, 0.1667, 0.25, 0.3, 0.5, 0.75, 1,
    1.5, 2, 50,
  ]
  const mults = [0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1, 1.01, 1.05, 1.1, 1.2, 1.5, 2, 5]
  const customs: { label: string; snap: MarketSnapshot }[] = [
    { label: 'committed', snap: snapshot },
    { label: 'empty term structure', snap: { ...snapshot, term_structure: [] } },
    { label: 'single knot', snap: { ...snapshot, term_structure: [{ t: 0.25, atm_iv: 0.2 }] } },
    {
      label: 'knot at t=0 (T floor)',
      snap: { ...snapshot, term_structure: [{ t: 0, atm_iv: 0.1 }, { t: 1, atm_iv: 0.2 }] },
    },
    {
      label: 'vol floor (tiny ATM)',
      snap: {
        ...snapshot,
        atm_vol_30d: 0.005,
        skew: { atm: 0.005, slope: 0, curv: 0 },
        term_structure: [{ t: 0.25, atm_iv: 0.005 }],
      },
    },
    {
      label: 'vol floor (concave wings)',
      snap: { ...snapshot, skew: { atm: 0.146, slope: -0.5, curv: -2 } },
    },
    {
      label: 'custom 5000 (TS test)',
      snap: {
        ...snapshot,
        spot: 5000,
        atm_vol_30d: 0.2,
        skew: { atm: 0.2, slope: -0.5, curv: 0.5 },
        term_structure: [{ t: 0.25, atm_iv: 0.2 }],
      },
    },
  ]
  const surfaces = customs.map(({ label, snap }) => {
    const sf = buildSurface(snap)
    const Ks = mults.map((m) => snap.spot * m)
    return {
      label,
      snapshot: snap,
      spot: sf.spot,
      Ts,
      Ks,
      atm: Ts.map((T) => sf.atmVol(T)),
      vol: Ks.map((K) => Ts.map((T) => sf.getVol(K, T))),
    }
  })
  const defaultSurface = {
    spot: surface.spot,
    atm: Ts.map((T) => surface.atmVol(T)),
    vol: mults.map((m) => Ts.map((T) => surface.getVol(snapshot.spot * m, T))),
  }

  // --- history ------------------------------------------------------------------------
  const sampled: { index: number; point: (typeof historySeries)[number] }[] = []
  for (let i = 0; i < historySeries.length; i += 25) sampled.push({ index: i, point: historySeries[i] })
  const lastIdx = historySeries.length - 1
  if (lastIdx % 25 !== 0) sampled.push({ index: lastIdx, point: historySeries[lastIdx] })

  writeGolden('data', {
    config: { underlyings: UNDERLYINGS, defaultUnderlying: DEFAULT_UNDERLYING },
    snapshot,
    validated,
    rejected,
    validatedText,
    rejectedText,
    nonFinite,
    nonFiniteNotes,
    seeds,
    volFloor: VOL_FLOOR,
    mults,
    surfaces,
    defaultSurface,
    history: { meta: historyMeta, length: historySeries.length, sampled },
  })
})
