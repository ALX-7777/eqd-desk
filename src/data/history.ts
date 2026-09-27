/**
 * Historical replay data loader. Wraps the committed `history.json` (real daily
 * ^GSPC + ^VIX from scripts/fetch_history.py) as a typed series the simulator can
 * replay. Data only — kept out of the reactive loop.
 */

import historyJson from './history.json'
import type { HistoryPoint } from '../engine'

interface HistoryFile {
  asof: string
  source: string
  count: number
  series: HistoryPoint[]
}

const data = historyJson as HistoryFile

export const historySeries: HistoryPoint[] = Array.isArray(data.series) ? data.series : []
export const historyMeta = {
  asof: data.asof ?? '',
  source: data.source ?? '',
  count: historySeries.length,
}
