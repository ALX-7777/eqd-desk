/**
 * AutocallView — Phoenix autocallable. Many structural inputs, a Monte-Carlo
 * price with its diagnostics (early-redemption probability, capital-loss
 * probability, expected life) and greeks, and a sample-paths plot with the
 * autocall / coupon / protection barriers drawn — to make path-dependence visible.
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
  priceAutocall,
  autocallGreeks,
  mulberry32,
  makeNormal,
  GREEK_UNITS,
  type AutocallInputs,
} from '../../engine'
import { snapshot } from '../../data/snapshot'
import { LabeledSlider } from '../Controls'
import { ExoticInfo } from '../ExoticInfo'
import { fmtNum, fmtMoney, fmtPct, signClass } from '../format'
import { tooltipStyle, axisTick, axisStroke, gridStroke } from '../chartTheme'
import type { ExoticMetric } from '../exoticsDocs'

const S0 = snapshot.spot

function seed(): AutocallInputs {
  return {
    S: S0,
    S0,
    sigma: snapshot.atm_vol_30d,
    r: snapshot.r,
    q: snapshot.q,
    maturity: 3,
    nObs: 6,
    couponRate: 0.04,
    autocallBarrier: 1.0,
    couponBarrier: 0.7,
    protectionBarrier: 0.65,
    memory: true,
    notional: 100,
  }
}

const N_PATHS = 8
const PATH_STEPS = 60

export function AutocallView() {
  const [i, setI] = useState<AutocallInputs>(seed)
  const [metric, setMetric] = useState<ExoticMetric>('delta')
  const set = (patch: Partial<AutocallInputs>) => setI((p) => ({ ...p, ...patch }))

  const res = useMemo(() => priceAutocall(i, 12000), [i])
  const greeks = useMemo(() => autocallGreeks(i, 16000), [i])

  const paths = useMemo(() => {
    const normal = makeNormal(mulberry32(0xc0ffee))
    const dt = i.maturity / PATH_STEPS
    const drift = (i.r - i.q - 0.5 * i.sigma * i.sigma) * dt
    const vol = i.sigma * Math.sqrt(dt)
    const rows: Record<string, number>[] = []
    const series: number[][] = []
    for (let p = 0; p < N_PATHS; p++) {
      const s: number[] = [i.S]
      for (let k = 1; k <= PATH_STEPS; k++) s.push(s[k - 1] * Math.exp(drift + vol * normal()))
      series.push(s)
    }
    for (let k = 0; k <= PATH_STEPS; k++) {
      const row: Record<string, number> = { t: (k / PATH_STEPS) * i.maturity }
      for (let p = 0; p < N_PATHS; p++) row[`p${p}`] = series[p][k]
      rows.push(row)
    }
    return rows
  }, [i])

  const AB = i.autocallBarrier * S0
  const CB = i.couponBarrier * S0
  const PB = i.protectionBarrier * S0

  return (
    <main className="layout">
      <section className="col col-left">
        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Autocallable</h2>
            <button className={`mini-toggle ${i.memory ? 'long' : ''}`} style={{ width: 'auto', padding: '0 8px' }} onClick={() => set({ memory: !i.memory })} title="Memory (snowball) coupon">
              {i.memory ? 'MEM' : 'no mem'}
            </button>
          </div>
          <LabeledSlider label="Spot (S)" value={i.S} min={Math.round(S0 * 0.4)} max={Math.round(S0 * 1.5)} step={S0 / 200} display={`${fmtMoney(i.S)} · ${Math.round((i.S / S0) * 100)}%`} onChange={(v) => set({ S: v })} />
          <LabeledSlider label="Maturity" value={i.maturity} min={1} max={6} step={0.5} display={`${i.maturity} y`} onChange={(v) => set({ maturity: v })} />
          <LabeledSlider label="Observations" value={i.nObs} min={1} max={24} step={1} display={`${i.nObs}`} onChange={(v) => set({ nObs: Math.round(v) })} />
          <LabeledSlider label="Coupon / period" value={i.couponRate} min={0} max={0.08} step={0.0025} display={fmtPct(i.couponRate)} onChange={(v) => set({ couponRate: v })} />
          <LabeledSlider label="Autocall barrier" value={i.autocallBarrier} min={0.8} max={1.2} step={0.01} display={fmtPct(i.autocallBarrier)} onChange={(v) => set({ autocallBarrier: v })} />
          <LabeledSlider label="Coupon barrier" value={i.couponBarrier} min={0.4} max={1} step={0.01} display={fmtPct(i.couponBarrier)} onChange={(v) => set({ couponBarrier: v })} />
          <LabeledSlider label="Protection barrier" value={i.protectionBarrier} min={0.3} max={1} step={0.01} display={fmtPct(i.protectionBarrier)} onChange={(v) => set({ protectionBarrier: v })} />
          <LabeledSlider label="Vol (σ)" value={i.sigma} min={0.05} max={0.6} step={0.0025} display={fmtPct(i.sigma)} onChange={(v) => set({ sigma: v })} />
        </div>

        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Value &amp; Greeks</h2>
            <span className="tag subtle">MC ±{fmtNum(res.stderr, 2)}</span>
          </div>
          <div className="price-hero" style={{ cursor: 'default' }}>
            <div className="price-hero-main mono">{fmtMoney(res.price)}</div>
            <div className="price-hero-sub">
              <span>note value (par {i.notional})</span>
              <span className="dim">{fmtNum((res.price / i.notional) * 100, 4)}% of par</span>
            </div>
          </div>
          <table className="greeks-table">
            <tbody>
              <tr className="group-row"><td colSpan={3}>Diagnostics</td></tr>
              <tr className="greek-row" style={{ cursor: 'default' }}><td className="g-label">P(autocall)</td><td className="g-value mono">{fmtPct(res.probAutocall, 1)}</td><td className="g-unit dim">early redeem</td></tr>
              <tr className="greek-row" style={{ cursor: 'default' }}><td className="g-label">P(capital loss)</td><td className="g-value mono neg">{fmtPct(res.probCapitalLoss, 1)}</td><td className="g-unit dim">at maturity</td></tr>
              <tr className="greek-row" style={{ cursor: 'default' }}><td className="g-label">Expected life</td><td className="g-value mono">{fmtNum(res.expectedLife, 3)}</td><td className="g-unit dim">years</td></tr>
              <tr className="group-row"><td colSpan={3}>Greeks (MC)</td></tr>
              {(['delta', 'vega', 'theta', 'rho'] as ExoticMetric[]).map((k) => (
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
            <h2 className="panel-title">Sample paths <span className="dim">&amp; barriers</span></h2>
            <span className="tag subtle">{N_PATHS} GBM paths</span>
          </div>
          <div className="chart-wrap" style={{ height: 420 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={paths} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={gridStroke} strokeDasharray="2 4" />
                <XAxis dataKey="t" type="number" domain={[0, i.maturity]} tickFormatter={(v) => `${v.toFixed(1)}y`} stroke={axisStroke} tick={axisTick} />
                <YAxis tickFormatter={(v) => v.toFixed(0)} stroke={axisStroke} tick={axisTick} width={56} domain={['auto', 'auto']} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => `t = ${Number(v).toFixed(2)}y`} formatter={(v) => [fmtNum(Number(v), 4), 'level']} />
                <ReferenceLine y={AB} stroke="var(--accent)" strokeDasharray="5 3" label={{ value: 'autocall', fill: 'var(--accent)', fontSize: 10, position: 'insideTopRight' }} />
                <ReferenceLine y={CB} stroke="var(--put)" strokeDasharray="4 4" label={{ value: 'coupon', fill: 'var(--put)', fontSize: 10, position: 'insideTopRight' }} />
                <ReferenceLine y={PB} stroke="var(--neg)" strokeDasharray="5 3" label={{ value: 'protection', fill: 'var(--neg)', fontSize: 10, position: 'insideBottomRight' }} />
                {Array.from({ length: N_PATHS }, (_, p) => (
                  <Line key={p} type="monotone" dataKey={`p${p}`} stroke="var(--line)" strokeOpacity={0.55} strokeWidth={1} dot={false} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-caption dim">
            Each path either crosses the autocall line on an observation date (early redemption at
            par) or runs to maturity — where finishing below the protection line means a capital
            loss. The payoff depends on the whole path, so the note is priced by Monte Carlo.
          </div>
        </div>
      </section>

      <section className="col col-right">
        <div className="panel grow">
          <ExoticInfo kind="autocall" metric={metric} onSelectMetric={setMetric} />
        </div>
      </section>
    </main>
  )
}
