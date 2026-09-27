/**
 * Underlying presets. The app is built around a config object, not a hardcoded
 * index, so the whole simulator can be re-pointed with a single flag. S&P 500 is
 * the default (richest free data, deepest options proxy in SPY).
 */

export type UnderlyingKey = 'spx' | 'sx5e'

export interface UnderlyingConfig {
  key: UnderlyingKey
  /** Display name. */
  name: string
  /** Real index ticker (spot + realized vol source). */
  indexTicker: string
  /** Vol-gauge ticker that anchors the ATM level (VIX / VSTOXX). */
  volIndexTicker: string
  /** Listed ETF proxy whose option chain gives the skew shape (SPY / FEZ). */
  optionsProxy: string
  /** Premium currency. */
  currency: string
  /** Fallback continuous dividend yield if not estimated. */
  defaultDivYield: number
}

export const UNDERLYINGS: Record<UnderlyingKey, UnderlyingConfig> = {
  spx: {
    key: 'spx',
    name: 'S&P 500',
    indexTicker: '^GSPC',
    volIndexTicker: '^VIX',
    optionsProxy: 'SPY',
    currency: 'USD',
    defaultDivYield: 0.013,
  },
  sx5e: {
    key: 'sx5e',
    name: 'Euro Stoxx 50',
    indexTicker: '^STOXX50E',
    volIndexTicker: 'V2TX.DE',
    optionsProxy: 'FEZ',
    currency: 'EUR',
    defaultDivYield: 0.03,
  },
}

/** S&P 500 is the default underlying. */
export const DEFAULT_UNDERLYING: UnderlyingKey = 'spx'
