/**
 * Typed loader + light runtime validation for the seed snapshot. The app builds
 * its initial market state from this; all data fetching lives in
 * scripts/fetch_snapshot.py and stays OUT of the reactive loop.
 */

import snapshotJson from './snapshot.json'
import type { BsmInputs } from '../engine'

/** Quadratic skew in log-moneyness: iv(k) ≈ atm + slope·k + curv·k², k = ln(K/S). */
export interface SkewParams {
  atm: number
  slope: number
  curv: number
}

/** One ATM point of the term structure. */
export interface TermPoint {
  /** Tenor in years. */
  t: number
  /** ATM implied vol at that tenor (decimal). */
  atm_iv: number
}

/** The seed market snapshot (mirror of fetch_snapshot.py's JSON shape). */
export interface MarketSnapshot {
  asof: string
  underlying: string
  name: string
  currency: string
  spot: number
  r: number
  q: number
  realized_vol: number | null
  atm_vol_30d: number
  skew: SkewParams
  term_structure: TermPoint[]
  source_notes: string[]
  tickers: { index_ticker: string; vol_ticker: string; options_proxy: string }
}

function num(v: unknown, path: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) {
    throw new Error(`snapshot: expected finite number at "${path}", got ${JSON.stringify(v)}`)
  }
  return v
}

/** Validate the imported JSON and narrow it to MarketSnapshot. */
export function validateSnapshot(raw: unknown): MarketSnapshot {
  if (typeof raw !== 'object' || raw === null) throw new Error('snapshot: not an object')
  const s = raw as Record<string, unknown>
  const skew = (s.skew ?? {}) as Record<string, unknown>
  const spot = num(s.spot, 'spot')
  if (spot <= 0) throw new Error('snapshot: spot must be > 0')
  const atm = num(s.atm_vol_30d, 'atm_vol_30d')
  if (atm <= 0) throw new Error('snapshot: atm_vol_30d must be > 0')
  const term = Array.isArray(s.term_structure) ? (s.term_structure as TermPoint[]) : []
  return {
    asof: String(s.asof ?? ''),
    underlying: String(s.underlying ?? ''),
    name: String(s.name ?? ''),
    currency: String(s.currency ?? ''),
    spot,
    r: num(s.r, 'r'),
    q: num(s.q, 'q'),
    realized_vol: s.realized_vol == null ? null : num(s.realized_vol, 'realized_vol'),
    atm_vol_30d: atm,
    skew: {
      atm: num(skew.atm ?? atm, 'skew.atm'),
      slope: num(skew.slope, 'skew.slope'),
      curv: num(skew.curv, 'skew.curv'),
    },
    term_structure: term.map((p, i) => ({
      t: num(p.t, `term_structure[${i}].t`),
      atm_iv: num(p.atm_iv, `term_structure[${i}].atm_iv`),
    })),
    source_notes: Array.isArray(s.source_notes) ? s.source_notes.map(String) : [],
    tickers: {
      index_ticker: String((s.tickers as Record<string, unknown>)?.index_ticker ?? ''),
      vol_ticker: String((s.tickers as Record<string, unknown>)?.vol_ticker ?? ''),
      options_proxy: String((s.tickers as Record<string, unknown>)?.options_proxy ?? ''),
    },
  }
}

/** The validated seed snapshot, ready to import across the app. */
export const snapshot: MarketSnapshot = validateSnapshot(snapshotJson)

/**
 * Seed a default Greeks-Lab option from a snapshot: ATM-ish 30-day option,
 * strike rounded to a round index level, vol/r/q from the snapshot.
 */
export function seedInputs(s: MarketSnapshot = snapshot, strikeStep = 25): BsmInputs {
  return {
    S: s.spot,
    K: Math.round(s.spot / strikeStep) * strikeStep,
    T: 30 / 365,
    r: s.r,
    q: s.q,
    sigma: s.atm_vol_30d,
  }
}
