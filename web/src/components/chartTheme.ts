/** Shared Recharts styling tokens so every chart reads the same. */
import type { CSSProperties } from 'react'

export const tooltipStyle: CSSProperties = {
  background: 'var(--panel-2)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  fontSize: 12,
  fontFamily: 'var(--mono)',
  color: 'var(--text)',
}

export const axisTick = { fontSize: 11, fill: 'var(--text-dim)' } as const
export const axisStroke = 'var(--axis)'
export const gridStroke = 'var(--grid)'
