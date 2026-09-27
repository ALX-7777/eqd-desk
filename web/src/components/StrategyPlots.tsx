/**
 * StrategyPlots — two charts for the whole structure:
 *   1. P&L payoff vs terminal spot: at the front expiry (the classic diagram,
 *      correct for calendars too) and the smooth current mark-to-market. Both net
 *      of premium, so they cross zero at the break-evens.
 *   2. The selected aggregate greek swept across spot, a parallel vol shift, or
 *      elapsed calendar time.
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
import {
  analyzePosition,
  payoffProfile,
  frontExpiry,
  GREEK_UNITS,
  type Leg,
  type MarketParams,
} from '../engine'
import { fmtNum } from './format'
import { GREEK_DOCS, type GreekKey } from './education'

export type StrategyXAxis = 'S' | 'vol' | 'time'

interface StrategyPlotsProps {
  legs: Leg[]
  market: MarketParams
  selectedGreek: GreekKey
  xAxis: StrategyXAxis
  onXAxisChange: (x: StrategyXAxis) => void
  spot: number
}

const N = 120

export function StrategyPlots({
  legs,
  market,
  selectedGreek,
  xAxis,
  onXAxisChange,
  spot,
}: StrategyPlotsProps) {
  const unit = GREEK_UNITS[selectedGreek]
  const sLo = spot * 0.7
  const sHi = spot * 1.3

  const payoff = useMemo(
    () => payoffProfile(legs, market, sLo, sHi, N),
    [legs, market, sLo, sHi],
  )

  const strikes = useMemo(() => Array.from(new Set(legs.map((l) => l.K))), [legs])

  const meta = useMemo(() => buildAxisMeta(xAxis, legs, market, spot), [xAxis, legs, market, spot])

  const greekData = useMemo(() => {
    const pts: { x: number; y: number }[] = []
    for (let i = 0; i <= N; i++) {
      const x = meta.lo + ((meta.hi - meta.lo) * i) / N
      pts.push({ x, y: meta.evalGreek(x)[selectedGreek] })
    }
    return pts
  }, [meta, selectedGreek])

  return (
    <div className="plots">
      <h3 className="sub-head">P&amp;L at expiry vs spot</h3>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={payoff} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" />
            <XAxis
              dataKey="S"
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
              formatter={(value, name) => [
                fmtNum(Number(value)),
                name === 'expiryPnl' ? 'At expiry' : 'Now',
              ]}
            />
            <ReferenceLine y={0} stroke="var(--axis)" />
            <ReferenceLine x={market.S} stroke="var(--accent)" strokeDasharray="4 3" />
            {strikes.map((k) => (
              <ReferenceLine key={k} x={k} stroke="var(--text-dim)" strokeDasharray="1 4" />
            ))}
            <Line
              type="monotone"
              dataKey="nowPnl"
              stroke="var(--accent)"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="expiryPnl"
              stroke="var(--line)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-caption dim">
        Solid: P&amp;L at the front expiry. Thin: P&amp;L now (mark-to-market). Dashed: spot;
        dotted: strikes. Crosses zero at the break-evens.
      </div>

      <div className="panel-title-row" style={{ marginTop: 14 }}>
        <h3 className="sub-head" style={{ margin: 0 }}>
          Net {unit.label} <span className="dim">vs</span>{' '}
          <span className="accent">{meta.label.toLowerCase()}</span>
        </h3>
        <div className="seg small" role="group" aria-label="x axis">
          {(['S', 'vol', 'time'] as StrategyXAxis[]).map((k) => (
            <button
              key={k}
              className={`seg-btn ${xAxis === k ? 'active' : ''}`}
              onClick={() => onXAxisChange(k)}
            >
              {k === 'S' ? 'Spot' : k === 'vol' ? 'Vol' : 'Time'}
            </button>
          ))}
        </div>
      </div>
      <div className="chart-wrap short">
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
              formatter={(value) => [fmtNum(Number(value)), `Net ${unit.label}`]}
            />
            <ReferenceLine y={0} stroke="var(--axis)" />
            <ReferenceLine x={meta.current} stroke="var(--accent)" strokeDasharray="4 3" />
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
      <div className="chart-caption dim">{GREEK_DOCS[selectedGreek].measures}</div>
    </div>
  )
}

interface AxisMeta {
  label: string
  lo: number
  hi: number
  current: number
  tick: (v: number) => string
  evalGreek: (x: number) => Record<GreekKey, number>
}

function buildAxisMeta(
  xAxis: StrategyXAxis,
  legs: Leg[],
  market: MarketParams,
  spot: number,
): AxisMeta {
  if (xAxis === 'vol') {
    return {
      label: 'Vol shift',
      lo: -0.1,
      hi: 0.1,
      current: 0,
      tick: (v) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}pt`,
      evalGreek: (shift) =>
        analyzePosition(
          legs.map((l) => ({ ...l, sigma: Math.max(0.01, l.sigma + shift) })),
          market,
        ).reported,
    }
  }
  if (xAxis === 'time') {
    const hi = Math.max(frontExpiry(legs) - 1e-4, 1 / 365)
    return {
      label: 'Time elapsed',
      lo: 0,
      hi,
      current: 0,
      tick: (v) => `${Math.round(v * 365)}d`,
      evalGreek: (t) =>
        analyzePosition(
          legs.map((l) => ({ ...l, T: Math.max(1e-6, l.T - t) })),
          market,
        ).reported,
    }
  }
  return {
    label: 'Spot',
    lo: spot * 0.7,
    hi: spot * 1.3,
    current: market.S,
    tick: (v) => v.toFixed(0),
    evalGreek: (S) => analyzePosition(legs, { ...market, S }).reported,
  }
}

const tooltipStyle: CSSProperties = {
  background: 'var(--panel-2)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  fontSize: 12,
  fontFamily: 'var(--mono)',
  color: 'var(--text)',
}
