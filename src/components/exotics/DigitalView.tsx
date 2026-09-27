/**
 * DigitalView — cash-or-nothing binary. Shows the digital price/greeks, its
 * replicating tight call spread (and the (Q/Δ) size that blows up as Δ→0), and a
 * plot overlaying the digital with the call-spread approximation — the pin-risk
 * step that sharpens as expiry approaches.
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
  cashOrNothingPrice,
  callSpreadReplication,
  digitalGreeks,
  GREEK_UNITS,
  type DigitalInputs,
  type OptionType,
} from '../../engine'
import { snapshot } from '../../data/snapshot'
import { LabeledSlider, Segmented } from '../Controls'
import { ExoticInfo } from '../ExoticInfo'
import { fmtNum, fmtMoney, fmtPct, signClass } from '../format'
import { tooltipStyle, axisTick, axisStroke, gridStroke } from '../chartTheme'
import type { ExoticMetric } from '../exoticsDocs'

const step = snapshot.spot >= 2000 ? 25 : 5
const round = (x: number) => Math.round(x / step) * step

function seed(): DigitalInputs {
  return {
    S: snapshot.spot,
    K: round(snapshot.spot),
    T: 0.25,
    r: snapshot.r,
    q: snapshot.q,
    sigma: snapshot.atm_vol_30d,
    type: 'call',
    cash: 100,
  }
}

export function DigitalView() {
  const [i, setI] = useState<DigitalInputs>(seed)
  const [width, setWidth] = useState(() => round(snapshot.spot * 0.02))
  const [metric, setMetric] = useState<ExoticMetric>('price')
  const set = (patch: Partial<DigitalInputs>) => setI((p) => ({ ...p, ...patch }))

  const greeks = useMemo(() => digitalGreeks(i), [i])
  const repl = useMemo(() => callSpreadReplication(i, width), [i, width])

  const data = useMemo(() => {
    const lo = snapshot.spot * 0.7
    const hi = snapshot.spot * 1.3
    const pts: { x: number; digital: number; repl: number; greek: number }[] = []
    for (let k = 0; k <= 140; k++) {
      const S = lo + ((hi - lo) * k) / 140
      const di = { ...i, S }
      pts.push({
        x: S,
        digital: cashOrNothingPrice(di),
        repl: callSpreadReplication(di, width),
        greek: digitalGreeks(di)[metric],
      })
    }
    return pts
  }, [i, width, metric])

  const isPrice = metric === 'price'

  return (
    <main className="layout">
      <section className="col col-left">
        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Digital</h2>
            <div className="seg" role="group" aria-label="type">
              <button className={`seg-btn ${i.type === 'call' ? 'active call' : ''}`} onClick={() => set({ type: 'call' })}>CALL</button>
              <button className={`seg-btn ${i.type === 'put' ? 'active put' : ''}`} onClick={() => set({ type: 'put' as OptionType })}>PUT</button>
            </div>
          </div>
          <LabeledSlider label="Spot (S)" value={i.S} min={round(snapshot.spot * 0.6)} max={round(snapshot.spot * 1.4)} step={step / 5} display={fmtMoney(i.S)} onChange={(v) => set({ S: v })} />
          <LabeledSlider label="Strike (K)" value={i.K} min={round(snapshot.spot * 0.6)} max={round(snapshot.spot * 1.4)} step={step / 5} display={fmtMoney(i.K)} onChange={(v) => set({ K: v })} />
          <LabeledSlider label="Time (T)" value={i.T} min={0.005} max={1.5} step={0.005} display={`${i.T.toFixed(3)} y · ${Math.round(i.T * 365)} d`} onChange={(v) => set({ T: v })} />
          <LabeledSlider label="Vol (σ)" value={i.sigma} min={0.05} max={0.8} step={0.0025} display={fmtPct(i.sigma)} onChange={(v) => set({ sigma: v })} />
          <LabeledSlider label="Cash payout (Q)" value={i.cash} min={10} max={500} step={10} display={fmtMoney(i.cash)} onChange={(v) => set({ cash: v })} />
          <LabeledSlider label="Replication width (Δ)" value={width} min={step / 5} max={round(snapshot.spot * 0.1)} step={step / 5} display={fmtMoney(width)} onChange={setWidth} />
        </div>

        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Price &amp; Greeks</h2>
          </div>
          <div className="price-hero" style={{ cursor: 'default' }}>
            <div className="price-hero-main mono">{fmtMoney(greeks.price)}</div>
            <div className="price-hero-sub">
              <span>digital premium ({snapshot.currency})</span>
              <span className="dim">spread {fmtMoney(repl)} · size {fmtNum(i.cash / width, 3)}×</span>
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
              {isPrice ? 'Value' : GREEK_UNITS[metric].label} <span className="dim">vs spot</span>
            </h2>
            <Segmented
              options={(['price', 'delta', 'gamma'] as ExoticMetric[]).map((m) => ({ value: m, label: GREEK_UNITS[m].label }))}
              value={metric === 'vega' || metric === 'theta' || metric === 'rho' ? 'price' : metric}
              onChange={setMetric}
            />
          </div>
          <div className="chart-wrap" style={{ height: 420 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={gridStroke} strokeDasharray="2 4" />
                <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} tickFormatter={(v) => v.toFixed(0)} stroke={axisStroke} tick={axisTick} />
                <YAxis tickFormatter={(v) => fmtNum(v, 3)} stroke={axisStroke} tick={axisTick} width={56} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => `Spot: ${Number(v).toFixed(0)}`} />
                <ReferenceLine y={0} stroke={axisStroke} />
                <ReferenceLine x={i.K} stroke="var(--text-dim)" strokeDasharray="1 4" />
                <ReferenceLine x={i.S} stroke="var(--accent)" strokeDasharray="4 3" />
                {isPrice ? (
                  <>
                    <Line type="monotone" dataKey="repl" stroke="var(--put)" strokeWidth={1.5} dot={false} isAnimationActive={false} name="call spread" />
                    <Line type="monotone" dataKey="digital" stroke="var(--line)" strokeWidth={2} dot={false} isAnimationActive={false} name="digital" />
                  </>
                ) : (
                  <Line type="monotone" dataKey="greek" stroke="var(--line)" strokeWidth={2} dot={false} isAnimationActive={false} />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-caption dim">
            {isPrice
              ? 'Blue: the digital. Orange: the replicating call spread of width Δ — shrink Δ (or T) and it converges to the digital step. The (Q/Δ) size needed is the un-hedgeable bit.'
              : 'The delta/gamma spike at the strike sharpens as T → 0 — the digital cannot be hedged exactly at expiry.'}
          </div>
        </div>
      </section>

      <section className="col col-right">
        <div className="panel grow">
          <ExoticInfo kind="digital" metric={metric} onSelectMetric={setMetric} />
        </div>
      </section>
    </main>
  )
}
