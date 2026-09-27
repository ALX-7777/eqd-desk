/**
 * Number formatting for the trading-terminal readouts. Numbers are the product,
 * so formatting is adaptive: enough significant figures to be useful, exponential
 * notation only for the very small/large, em-dash for non-finite.
 */

/** Adaptive numeric format targeting ~`sig` significant figures. */
export function fmtNum(x: number, sig = 5): string {
  if (!Number.isFinite(x)) return '—'
  if (x === 0) return '0'
  const abs = Math.abs(x)
  if (abs >= 1e7 || abs < 1e-4) return x.toExponential(2)
  const intDigits = Math.floor(Math.log10(abs)) + 1
  const dp = Math.min(8, Math.max(0, sig - intDigits))
  return x.toFixed(dp)
}

/** Like fmtNum but always shows an explicit + / − sign. */
export function fmtSigned(x: number, sig = 5): string {
  if (!Number.isFinite(x)) return '—'
  const s = fmtNum(Math.abs(x), sig)
  if (x > 0) return `+${s}`
  if (x < 0) return `−${s}`
  return s
}

/** Currency-style format with thousands separators and fixed dp. */
export function fmtMoney(x: number, dp = 2): string {
  if (!Number.isFinite(x)) return '—'
  return x.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })
}

/** Percent format (input is a decimal: 0.146 → "14.60%"). */
export function fmtPct(x: number, dp = 2): string {
  if (!Number.isFinite(x)) return '—'
  return `${(x * 100).toFixed(dp)}%`
}

/** Sign class for colouring: 'pos' | 'neg' | 'zero'. */
export function signClass(x: number): 'pos' | 'neg' | 'zero' {
  if (!Number.isFinite(x) || x === 0) return 'zero'
  return x > 0 ? 'pos' : 'neg'
}
