/**
 * PlotsPanel — the visual half of the lab. Two charts:
 *   1. The selected greek (or price) swept against spot / vol / time, with the
 *      current level and the strike marked.
 *   2. Payoff at expiry vs the current option value (so time value is visible).
 *
 * Sweeps re-run the engine across the x-range each render (cheap: ~100 analytic
 * evaluations), memoised on the inputs that matter.
 */

import { useMemo, type CSSProperties } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import { analyzeOption } from '../engine'
import { GREEK_UNITS } from '../engine'
import type { BsmInputs, OptionType } from '../engine'
import { fmtNum } from './format'
import { GREEK_DOCS, type GreekKey } from './education'

export type XAxisKey = 'S' | 'sigma' | 'T'

interface PlotsPanelProps {
  inputs: BsmInputs
  type: OptionType
  selectedGreek: GreekKey
  xAxis: XAxisKey
  onXAxisChange: (x: XAxisKey) => void
  spot: number
}

const N = 100

const X_META: Record<
  XAxisKey,
  { label: string; tick: (v: number) => string; range: (spot: number) => [number, number] }
> = {
  S: { label: 'Spot', tick: (v) => v.toFixed(0), range: (s) => [s * 0.6, s * 1.4] },
  sigma: { label: 'Implied vol', tick: (v) => `${(v * 100).toFixed(0)}%`, range: () => [0.02, 0.8] },
  T: { label: 'Time to expiry (yrs)', tick: (v) => v.toFixed(2), range: () => [0.003, 2] },
}

export function PlotsPanel({
  inputs,
  type,
  selectedGreek,
  xAxis,
  onXAxisChange,
  spot,
}: PlotsPanelProps) {
  const meta = X_META[xAxis]
  const unit = GREEK_UNITS[selectedGreek]

  const greekData = useMemo(() => {
    const [lo, hi] = meta.range(spot)
    const pts: { x: number; y: number }[] = []
    for (let i = 0; i <= N; i++) {
      const x = lo + ((hi - lo) * i) / N
      const a = analyzeOption({ ...inputs, [xAxis]: x }, type)
      pts.push({ x, y: a.reported[selectedGreek] })
    }
    return pts
  }, [inputs, type, selectedGreek, xAxis, spot, meta])

  const payoffData = useMemo(() => {
    const lo = spot * 0.6
    const hi = spot * 1.4
    const pts: { x: number; expiry: number; value: number }[] = []
    for (let i = 0; i <= N; i++) {
      const S = lo + ((hi - lo) * i) / N
      const expiry = type === 'call' ? Math.max(S - inputs.K, 0) : Math.max(inputs.K - S, 0)
      const value = analyzeOption({ ...inputs, S }, type).reported.price
      pts.push({ x: S, expiry, value })
    }
    return pts
  }, [inputs, type, spot])

  const currentX = inputs[xAxis]

  return (
    <div className="plots">
      <div className="panel-title-row">
        <h2 className="panel-title">
          {unit.label} <span className="dim">vs</span>{' '}
          <span className="accent">{meta.label.toLowerCase()}</span>
        </h2>
        <div className="seg small" role="group" aria-label="x axis">
          {(Object.keys(X_META) as XAxisKey[]).map((k) => (
            <button
              key={k}
              className={`seg-btn ${xAxis === k ? 'active' : ''}`}
              onClick={() => onXAxisChange(k)}
            >
              {k === 'S' ? 'Spot' : k === 'sigma' ? 'Vol' : 'Time'}
            </button>
          ))}
        </div>
      </div>

      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={greekData} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" />
            <XAxis
              dataKey="x"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={meta.tick}
              stroke="var(--axis)"
              tick={{ fontSize: 11, fill: 'var(--text-dim)' }}
            />
            <YAxis
              tickFormatter={(v) => fmtNum(v, 3)}
              stroke="var(--axis)"
              tick={{ fontSize: 11, fill: 'var(--text-dim)' }}
              width={56}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(v) => `${meta.label}: ${meta.tick(Number(v))}`}
              formatter={(value) => [fmtNum(Number(value)), unit.label]}
            />
            <ReferenceLine x={currentX} stroke="var(--accent)" strokeDasharray="4 3" />
            {xAxis === 'S' && <ReferenceLine x={inputs.K} stroke="var(--text-dim)" strokeDasharray="1 4" />}
            <Line
              type="monotone"
              dataKey="y"
              stroke="var(--line)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-caption dim">
        {GREEK_DOCS[selectedGreek].measures}
        {xAxis === 'S' && ' — dashed: current spot; dotted: strike.'}
        {xAxis !== 'S' && ` — dashed: current ${xAxis === 'sigma' ? 'vol' : 'tenor'}.`}
      </div>

      <h3 className="sub-head">Payoff at expiry</h3>
      <div className="chart-wrap short">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={payoffData} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" />
            <XAxis
              dataKey="x"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(v) => v.toFixed(0)}
              stroke="var(--axis)"
              tick={{ fontSize: 11, fill: 'var(--text-dim)' }}
            />
            <YAxis
              tickFormatter={(v) => fmtNum(v, 3)}
              stroke="var(--axis)"
              tick={{ fontSize: 11, fill: 'var(--text-dim)' }}
              width={56}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(v) => `Spot: ${Number(v).toFixed(0)}`}
              formatter={(value, name) => [fmtNum(Number(value)), name === 'expiry' ? 'At expiry' : 'Now']}
            />
            <ReferenceLine x={inputs.S} stroke="var(--accent)" strokeDasharray="4 3" />
            <ReferenceLine x={inputs.K} stroke="var(--text-dim)" strokeDasharray="1 4" />
            <ReferenceLine y={0} stroke="var(--axis)" />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--accent)"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="expiry"
              stroke="var(--line)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-caption dim">
        Solid: value at expiry (intrinsic). Thin: value now (premium) — the gap is time value.
      </div>
    </div>
  )
}

const tooltipStyle: CSSProperties = {
  background: 'var(--panel-2)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  fontSize: 12,
  fontFamily: 'var(--mono)',
  color: 'var(--text)',
}
