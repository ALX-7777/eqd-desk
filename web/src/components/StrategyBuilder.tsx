/**
 * StrategyBuilder — Phase 2 view. Compose vanilla legs into a structure (presets
 * or hand-edited), see the net premium, aggregate greeks, the P&L payoff diagram
 * and greek profiles, plus the desk rationale for the structure.
 */

import { useMemo, useRef, useState } from 'react'
import {
  analyzePosition,
  buildPreset,
  type Leg,
  type MarketParams,
  type PresetName,
} from '../engine'
import { snapshot } from '../data/snapshot'
import { surface } from '../data/volSurface'

import { StrategyControls } from './StrategyControls'
import { LegsEditor } from './LegsEditor'
import { PositionReadout } from './PositionReadout'
import { StrategyPlots, type StrategyXAxis } from './StrategyPlots'
import { StrategyEducation } from './StrategyEducation'
import type { GreekKey } from './education'

const DEFAULT_PRESET: PresetName = 'butterfly'

function strikeStepFor(spot: number): number {
  if (spot >= 2000) return 25
  if (spot >= 200) return 5
  return 1
}

function roundTo(x: number, step: number): number {
  return Math.round(x / step) * step
}

export function StrategyBuilder() {
  const step = strikeStepFor(snapshot.spot)
  const [market, setMarket] = useState<MarketParams>(() => ({
    S: snapshot.spot,
    r: snapshot.r,
    q: snapshot.q,
  }))
  const [baseTDays, setBaseTDays] = useState(30)
  const [widthPct, setWidthPct] = useState(0.05)
  const [selectedGreek, setSelectedGreek] = useState<GreekKey>('delta')
  const [xAxis, setXAxis] = useState<StrategyXAxis>('S')
  const [currentPreset, setCurrentPreset] = useState<PresetName | 'custom'>(DEFAULT_PRESET)

  const idRef = useRef(0)
  const makePreset = (name: PresetName, m: MarketParams, days: number, w: number): Leg[] =>
    buildPreset(name, {
      S: m.S,
      baseT: days / 365,
      widthPct: w,
      strikeStep: step,
      volFor: (K, T) => surface.getVol(K, T),
    })

  const [legs, setLegs] = useState<Leg[]>(() =>
    makePreset(DEFAULT_PRESET, { S: snapshot.spot, r: snapshot.r, q: snapshot.q }, 30, 0.05),
  )

  const analysis = useMemo(() => analyzePosition(legs, market), [legs, market])

  const applyPreset = (name: PresetName) => {
    setLegs(makePreset(name, market, baseTDays, widthPct))
    setCurrentPreset(name)
  }
  const onMarketChange = (patch: Partial<MarketParams>) => setMarket((m) => ({ ...m, ...patch }))
  const updateLeg = (id: string, patch: Partial<Leg>) => {
    setLegs((ls) => ls.map((l) => (l.id === id ? { ...l, ...patch } : l)))
    setCurrentPreset('custom')
  }
  const removeLeg = (id: string) => {
    setLegs((ls) => ls.filter((l) => l.id !== id))
    setCurrentPreset('custom')
  }
  const addLeg = () => {
    const K = roundTo(market.S, step)
    const T = baseTDays / 365
    setLegs((ls) => [
      ...ls,
      { id: `custom-${idRef.current++}`, type: 'call', side: 'long', quantity: 1, K, T, sigma: surface.getVol(K, T) },
    ])
    setCurrentPreset('custom')
  }
  const onReset = () => {
    const m = { S: snapshot.spot, r: snapshot.r, q: snapshot.q }
    setMarket(m)
    setBaseTDays(30)
    setWidthPct(0.05)
    setLegs(makePreset(DEFAULT_PRESET, m, 30, 0.05))
    setCurrentPreset(DEFAULT_PRESET)
  }

  return (
    <main className="layout">
      <section className="col col-left">
        <div className="panel">
          <StrategyControls
            market={market}
            onMarketChange={onMarketChange}
            baseTDays={baseTDays}
            widthPct={widthPct}
            onBaseTDaysChange={setBaseTDays}
            onWidthPctChange={setWidthPct}
            currentPreset={currentPreset}
            onApplyPreset={applyPreset}
            onReset={onReset}
            spot={snapshot.spot}
            currency={snapshot.currency}
          />
        </div>
        <div className="panel">
          <PositionReadout
            analysis={analysis}
            selectedGreek={selectedGreek}
            onSelectGreek={setSelectedGreek}
            currency={snapshot.currency}
          />
        </div>
      </section>

      <section className="col col-center">
        <div className="panel">
          <div className="panel-title-row">
            <h2 className="panel-title">Legs</h2>
            <span className="tag subtle">{legs.length} leg{legs.length === 1 ? '' : 's'}</span>
          </div>
          <LegsEditor legs={legs} onUpdate={updateLeg} onRemove={removeLeg} onAdd={addLeg} />
        </div>
        <div className="panel grow">
          <StrategyPlots
            legs={legs}
            market={market}
            selectedGreek={selectedGreek}
            xAxis={xAxis}
            onXAxisChange={setXAxis}
            spot={snapshot.spot}
          />
        </div>
      </section>

      <section className="col col-right">
        <div className="panel grow">
          <StrategyEducation
            currentPreset={currentPreset}
            selectedGreek={selectedGreek}
            onSelectGreek={setSelectedGreek}
          />
        </div>
      </section>
    </main>
  )
}
