/**
 * VarSwapView — variance swap. A controllable parametric smile (ATM level + skew
 * slope/curvature) feeds the model-free replication; the readout shows the fair
 * vol vs ATM (the convexity premium / VIX intuition), and the charts show the
 * 1/K² replication strip and the smile that drives it.
 */

import { useMemo, useState } from 'react'
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import { priceVarianceSwap } from '../../engine'
import { snapshot } from '../../data/snapshot'
import { LabeledSlider } from '../Controls'
import { ExoticInfo } from '../ExoticInfo'
import { fmtNum, fmtPct, fmtMoney } from '../format'
import { tooltipStyle, axisTick, axisStroke, gridStroke } from '../chartTheme'

export function VarSwapView() {
  const [S] = useState(snapshot.spot)
  const [T, setT] = useState(30 / 365)
  const [atmVol, setAtmVol] = useState(snapshot.atm_vol_30d)
  const [slope, setSlope] = useState(snapshot.skew.slope)
  const [curv, setCurv] = useState(snapshot.skew.curv)
  const r = snapshot.r
  const q = snapshot.q

  const F = S * Math.exp((r - q) * T)
  const volFor = useMemo(
    () => (K: number) => Math.max(0.03, atmVol + slope * Math.log(K / F) + curv * Math.log(K / F) ** 2),
    [atmVol, slope, curv, F],
  )

  const res = useMemo(() => priceVarianceSwap({ S, T, r, q, volFor }), [S, T, r, q, volFor])

  // Down-sample the strip for plotting and add the smile.
  const stripData = useMemo(
    () => res.strip.filter((_, idx) => idx % 3 === 0).map((p) => ({ K: p.K, contribution: p.contribution, vol: volFor(p.K) })),
    [res, volFor],
  )

  const premium = res.fairVol - res.atmVol

  return (
    <main className="layout">
      <section className="col col-left">
        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Variance swap</h2>
          </div>
          <LabeledSlider label="Tenor (T)" value={T} min={7 / 365} max={1} step={1 / 365} display={`${Math.round(T * 365)} d`} onChange={setT} />
          <LabeledSlider label="ATM vol" value={atmVol} min={0.05} max={0.6} step={0.0025} display={fmtPct(atmVol)} onChange={setAtmVol} />
          <LabeledSlider label="Skew slope" value={slope} min={-1.2} max={0.2} step={0.01} display={fmtNum(slope, 3)} onChange={setSlope} />
          <LabeledSlider label="Smile curvature" value={curv} min={0} max={2} step={0.02} display={fmtNum(curv, 3)} onChange={setCurv} />
          <div className="chart-caption dim" style={{ marginTop: 8 }}>
            Steepen the skew (more negative slope) and watch the fair vol pull above ATM — the
            replication overweights the now-richer downside puts.
          </div>
        </div>

        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Fair variance</h2>
            <span className="tag">VIX-style</span>
          </div>
          <div className="price-hero" style={{ cursor: 'default' }}>
            <div className="price-hero-main mono">{fmtPct(res.fairVol)}</div>
            <div className="price-hero-sub">
              <span>fair volatility</span>
              <span className="dim">√(fair variance)</span>
            </div>
          </div>
          <table className="greeks-table">
            <tbody>
              <tr className="greek-row" style={{ cursor: 'default' }}><td className="g-label">Fair variance</td><td className="g-value mono">{fmtNum(res.fairVariance, 5)}</td><td className="g-unit dim">annualised</td></tr>
              <tr className="greek-row" style={{ cursor: 'default' }}><td className="g-label">ATM vol</td><td className="g-value mono">{fmtPct(res.atmVol)}</td><td className="g-unit dim">at forward</td></tr>
              <tr className="greek-row" style={{ cursor: 'default' }}><td className="g-label">Convexity premium</td><td className={`g-value mono ${premium >= 0 ? 'pos' : 'neg'}`}>{premium >= 0 ? '+' : ''}{fmtPct(premium)}</td><td className="g-unit dim">fair − ATM</td></tr>
              <tr className="greek-row" style={{ cursor: 'default' }}><td className="g-label">Forward</td><td className="g-value mono">{fmtMoney(res.forward)}</td><td className="g-unit dim">{snapshot.currency}</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="col col-center">
        <div className="panel grow">
          <div className="panel-title-row">
            <h2 className="panel-title">Replication strip <span className="dim">(weighted 1/K²)</span></h2>
          </div>
          <div className="chart-wrap" style={{ height: 250 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={stripData} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={gridStroke} strokeDasharray="2 4" />
                <XAxis dataKey="K" type="number" domain={['dataMin', 'dataMax']} tickFormatter={(v) => v.toFixed(0)} stroke={axisStroke} tick={axisTick} />
                <YAxis tickFormatter={(v) => fmtNum(v, 3)} stroke={axisStroke} tick={axisTick} width={56} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => `Strike: ${Number(v).toFixed(0)}`} formatter={(v) => [fmtNum(Number(v), 5), 'contribution']} />
                <ReferenceLine x={res.forward} stroke="var(--accent)" strokeDasharray="4 3" label={{ value: 'F', fill: 'var(--accent)', fontSize: 11, position: 'top' }} />
                <Area type="monotone" dataKey="contribution" stroke="var(--line)" fill="var(--accent-dim)" strokeWidth={1.5} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-caption dim">
            Each OTM option's 1/K²-weighted contribution to fair variance. Puts (below F) carry more
            weight — the source of the convexity premium.
          </div>

          <h3 className="sub-head">Implied-vol smile</h3>
          <div className="chart-wrap short">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stripData} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={gridStroke} strokeDasharray="2 4" />
                <XAxis dataKey="K" type="number" domain={['dataMin', 'dataMax']} tickFormatter={(v) => v.toFixed(0)} stroke={axisStroke} tick={axisTick} />
                <YAxis tickFormatter={(v) => fmtPct(v, 0)} stroke={axisStroke} tick={axisTick} width={56} domain={['auto', 'auto']} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => `Strike: ${Number(v).toFixed(0)}`} formatter={(v) => [fmtPct(Number(v)), 'implied vol']} />
                <ReferenceLine x={res.forward} stroke="var(--accent)" strokeDasharray="4 3" />
                <Line type="monotone" dataKey="vol" stroke="var(--put)" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <section className="col col-right">
        <div className="panel grow">
          <ExoticInfo kind="varswap" showGreeks={false} />
        </div>
      </section>
    </main>
  )
}
