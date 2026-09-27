/**
 * BarrierView — single-barrier option. Inputs (incl. barrier H and kind), a
 * price/greeks readout vs the vanilla, and the selected metric swept against spot
 * with the barrier and strike marked — so the gamma explosion at the barrier is
 * visible.
 */

import { useMemo, useState } from 'react'
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
  barrierGreeks,
  price as vanillaPrice,
  GREEK_UNITS,
  type BarrierInputs,
  type BarrierKind,
  type OptionType,
} from '../../engine'
import { snapshot } from '../../data/snapshot'
import { surface } from '../../data/volSurface'
import { LabeledSlider, Segmented } from '../Controls'
import { ExoticInfo } from '../ExoticInfo'
import { fmtNum, fmtMoney, fmtPct, signClass } from '../format'
import { tooltipStyle, axisTick, axisStroke, gridStroke } from '../chartTheme'
import type { ExoticMetric } from '../exoticsDocs'

const step = snapshot.spot >= 2000 ? 25 : 5
const round = (x: number) => Math.round(x / step) * step

function seed(): BarrierInputs {
  const K = round(snapshot.spot)
  return {
    S: snapshot.spot,
    K,
    H: round(snapshot.spot * 0.9),
    T: 0.5,
    r: snapshot.r,
    q: snapshot.q,
    sigma: snapshot.atm_vol_30d,
    type: 'call',
    kind: 'down-out',
  }
}

const KINDS: { value: BarrierKind; label: string }[] = [
  { value: 'down-out', label: 'Down-out' },
  { value: 'down-in', label: 'Down-in' },
  { value: 'up-out', label: 'Up-out' },
  { value: 'up-in', label: 'Up-in' },
]

export function BarrierView() {
  const [i, setI] = useState<BarrierInputs>(seed)
  const [metric, setMetric] = useState<ExoticMetric>('gamma')
  const set = (patch: Partial<BarrierInputs>) => setI((p) => ({ ...p, ...patch }))

  const greeks = useMemo(() => barrierGreeks(i), [i])
  const vanilla = useMemo(
    () => vanillaPrice({ S: i.S, K: i.K, T: i.T, r: i.r, q: i.q, sigma: i.sigma }, i.type),
    [i],
  )

  const data = useMemo(() => {
    const lo = snapshot.spot * 0.55
    const hi = snapshot.spot * 1.45
    const pts: { x: number; y: number }[] = []
    for (let k = 0; k <= 120; k++) {
      const S = lo + ((hi - lo) * k) / 120
      const g = barrierGreeks({ ...i, S })
      pts.push({ x: S, y: g[metric] })
    }
    return pts
  }, [i, metric])

  const pct = vanilla !== 0 ? greeks.price / vanilla : 0

  return (
    <main className="layout">
      <section className="col col-left">
        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Barrier</h2>
            <div className="seg" role="group" aria-label="type">
              <button className={`seg-btn ${i.type === 'call' ? 'active call' : ''}`} onClick={() => set({ type: 'call' })}>CALL</button>
              <button className={`seg-btn ${i.type === 'put' ? 'active put' : ''}`} onClick={() => set({ type: 'put' as OptionType })}>PUT</button>
            </div>
          </div>
          <div style={{ marginBottom: 12 }}>
            <Segmented options={KINDS} value={i.kind} onChange={(v) => set({ kind: v })} ariaLabel="barrier kind" />
          </div>
          <LabeledSlider label="Spot (S)" value={i.S} min={round(snapshot.spot * 0.6)} max={round(snapshot.spot * 1.4)} step={step / 5} display={fmtMoney(i.S)} onChange={(v) => set({ S: v })} />
          <LabeledSlider label="Strike (K)" value={i.K} min={round(snapshot.spot * 0.6)} max={round(snapshot.spot * 1.4)} step={step / 5} display={fmtMoney(i.K)} onChange={(v) => set({ K: v })} />
          <LabeledSlider label="Barrier (H)" value={i.H} min={round(snapshot.spot * 0.5)} max={round(snapshot.spot * 1.5)} step={step / 5} display={fmtMoney(i.H)} onChange={(v) => set({ H: v })} />
          <LabeledSlider label="Time (T)" value={i.T} min={0.02} max={2} step={0.01} display={`${i.T.toFixed(2)} y`} onChange={(v) => set({ T: v })} />
          <LabeledSlider label="Vol (σ)" value={i.sigma} min={0.05} max={0.8} step={0.0025} display={fmtPct(i.sigma)} onChange={(v) => set({ sigma: v })} />
          <button className="btn" style={{ width: '100%', marginTop: 4 }} onClick={() => { set({ sigma: surface.getVol(i.K, i.T) }) }}>σ ← surface</button>
        </div>

        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Price &amp; Greeks</h2>
            <span className="tag">{Math.round(pct * 100)}% of vanilla</span>
          </div>
          <div className="price-hero" style={{ cursor: 'default' }}>
            <div className="price-hero-main mono">{fmtMoney(greeks.price)}</div>
            <div className="price-hero-sub">
              <span>barrier premium ({snapshot.currency})</span>
              <span className="dim">vanilla {fmtMoney(vanilla)}</span>
            </div>
          </div>
          <table className="greeks-table">
            <tbody>
              {(['delta', 'gamma', 'vega', 'theta', 'rho'] as ExoticMetric[]).map((k) => (
                <tr key={k} className={`greek-row ${metric === k ? 'sel' : ''}`} onClick={() => setMetric(k)}>
                  <td className="g-label">{GREEK_UNITS[k].label}</td>
                  <td className={`g-value mono ${signClass(greeks[k])}`}>{fmtNum(greeks[k])}</td>
                  <td className="g-unit dim">{GREEK_UNITS[k].unit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="col col-center">
        <div className="panel grow">
          <div className="panel-title-row">
            <h2 className="panel-title">
              {GREEK_UNITS[metric].label} <span className="dim">vs spot</span>
            </h2>
            <Segmented
              options={(['price', 'delta', 'gamma', 'vega'] as ExoticMetric[]).map((m) => ({ value: m, label: GREEK_UNITS[m].label }))}
              value={metric === 'theta' || metric === 'rho' ? 'price' : metric}
              onChange={setMetric}
            />
          </div>
          <div className="chart-wrap" style={{ height: 420 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={gridStroke} strokeDasharray="2 4" />
                <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} tickFormatter={(v) => v.toFixed(0)} stroke={axisStroke} tick={axisTick} />
                <YAxis tickFormatter={(v) => fmtNum(v, 3)} stroke={axisStroke} tick={axisTick} width={56} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => `Spot: ${Number(v).toFixed(0)}`} formatter={(v) => [fmtNum(Number(v)), GREEK_UNITS[metric].label]} />
                <ReferenceLine y={0} stroke={axisStroke} />
                <ReferenceLine x={i.H} stroke="var(--neg)" strokeDasharray="5 3" label={{ value: 'H', fill: 'var(--neg)', fontSize: 11, position: 'top' }} />
                <ReferenceLine x={i.K} stroke="var(--text-dim)" strokeDasharray="1 4" />
                <ReferenceLine x={i.S} stroke="var(--accent)" strokeDasharray="4 3" />
                <Line type="monotone" dataKey="y" stroke="var(--line)" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-caption dim">
            Red dashed = barrier H, dotted = strike K, accent = current spot. Watch gamma spike as
            spot nears the barrier — that is where a knock-out hedge is hardest.
          </div>
        </div>
      </section>

      <section className="col col-right">
        <div className="panel grow">
          <ExoticInfo kind="barrier" metric={metric} onSelectMetric={setMetric} />
        </div>
      </section>
    </main>
  )
}
