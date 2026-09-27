/**
 * Two-way quoting and fill logic on a package (single or multi-leg). You quote
 * around the NET fair, with the spread and your lean sized off the GROSS premium
 * (Σ|leg premium|) so credit/zero-cost structures (e.g. risk reversals) still
 * have a well-defined width.
 *
 *   client BUYS  ⇒ fills if your ask ≤ trueValue  (you go SHORT the package)
 *   client SELLS ⇒ fills if your bid ≥ trueValue  (you go LONG  the package)
 *
 * trueValue = netFair + noiseFrac·gross·Z. Wider spread = more edge per fill,
 * lower fill probability. `lean` shifts your mid (as a fraction of gross) to skew
 * your price toward the flow you want — leaning past fair gives up edge.
 */

import type { RFQ } from './rfq'

export type YourSide = 'buy' | 'sell'

export interface FillResult {
  filled: boolean
  youSide: YourSide | null
  /** Traded NET package price. */
  price: number
  /** Edge captured vs net fair (× size); 0 if not filled (can be < 0 if you lean past fair). */
  edge: number
  bid: number
  ask: number
  /** Net fair the quote was built around. */
  fairValue: number
}

export function evaluateQuote(
  rfq: RFQ,
  netFair: number,
  gross: number,
  spreadFrac: number,
  noiseFrac: number,
  z: number,
  lean = 0,
): FillResult {
  const halfWidth = (spreadFrac / 2) * gross
  const mid = netFair + lean * gross
  const ask = mid + halfWidth
  const bid = mid - halfWidth
  const trueValue = netFair + noiseFrac * gross * z

  if (rfq.clientSide === 'buy') {
    const filled = ask <= trueValue
    return { filled, youSide: filled ? 'sell' : null, price: ask, edge: filled ? (ask - netFair) * rfq.size : 0, bid, ask, fairValue: netFair }
  }
  const filled = bid >= trueValue
  return { filled, youSide: filled ? 'buy' : null, price: bid, edge: filled ? (netFair - bid) * rfq.size : 0, bid, ask, fairValue: netFair }
}
