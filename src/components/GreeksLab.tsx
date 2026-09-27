/**
 * GreeksLab — Phase 1 view: a single vanilla option with live price, all greeks,
 * selectable greek/payoff plots, and the education panel. Holds its own state.
 */

import { useMemo, useState } from 'react'
import { analyzeOption } from '../engine'
import type { BsmInputs, OptionType } from '../engine'
import { snapshot, seedInputs } from '../data/snapshot'
import { surface } from '../data/volSurface'

import { InputPanel } from './InputPanel'
import { GreeksReadout } from './GreeksReadout'
import { PlotsPanel, type XAxisKey } from './PlotsPanel'
import { EducationPanel } from './EducationPanel'
import type { GreekKey } from './education'

export function GreeksLab() {
  const [inputs, setInputs] = useState<BsmInputs>(() => seedInputs(snapshot))
  const [type, setType] = useState<OptionType>('call')
  const [selectedGreek, setSelectedGreek] = useState<GreekKey>('delta')
  const [xAxis, setXAxis] = useState<XAxisKey>('S')

  const analysis = useMemo(() => analyzeOption(inputs, type), [inputs, type])

  const onChange = (patch: Partial<BsmInputs>) => setInputs((prev) => ({ ...prev, ...patch }))
  const onReset = () => {
    setInputs(seedInputs(snapshot))
    setType('call')
  }

  return (
    <main className="layout">
      <section className="col col-left">
        <div className="panel">
          <InputPanel
            inputs={inputs}
            type={type}
            spot={snapshot.spot}
            currency={snapshot.currency}
            onChange={onChange}
            onTypeChange={setType}
            onReset={onReset}
            surfaceVol={(K, T) => surface.getVol(K, T)}
          />
        </div>
        <div className="panel">
          <GreeksReadout
            analysis={analysis}
            selectedGreek={selectedGreek}
            onSelectGreek={setSelectedGreek}
            currency={snapshot.currency}
          />
        </div>
      </section>

      <section className="col col-center">
        <div className="panel grow">
          <PlotsPanel
            inputs={inputs}
            type={type}
            selectedGreek={selectedGreek}
            xAxis={xAxis}
            onXAxisChange={setXAxis}
            spot={snapshot.spot}
          />
        </div>
      </section>

      <section className="col col-right">
        <div className="panel grow">
          <EducationPanel selectedGreek={selectedGreek} onSelectGreek={setSelectedGreek} />
        </div>
      </section>
    </main>
  )
}
