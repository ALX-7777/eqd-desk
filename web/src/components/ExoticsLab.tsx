/**
 * ExoticsLab — Phase 3 view. A sub-selector switches between the four exotics,
 * each a self-contained view (controls + characteristic plot + education).
 */

import { useState } from 'react'
import type { ExoticKind } from './exoticsDocs'
import { BarrierView } from './exotics/BarrierView'
import { DigitalView } from './exotics/DigitalView'
import { AutocallView } from './exotics/AutocallView'
import { VarSwapView } from './exotics/VarSwapView'

const KINDS: { value: ExoticKind; label: string }[] = [
  { value: 'barrier', label: 'Barrier' },
  { value: 'digital', label: 'Digital' },
  { value: 'autocall', label: 'Autocallable' },
  { value: 'varswap', label: 'Variance swap' },
]

export function ExoticsLab() {
  const [kind, setKind] = useState<ExoticKind>('barrier')
  return (
    <div className="exotics-shell">
      <div className="exotics-subnav">
        {KINDS.map((k) => (
          <button
            key={k.value}
            className={`subtab ${kind === k.value ? 'active' : ''}`}
            onClick={() => setKind(k.value)}
          >
            {k.label}
          </button>
        ))}
      </div>
      {kind === 'barrier' && <BarrierView />}
      {kind === 'digital' && <DigitalView />}
      {kind === 'autocall' && <AutocallView />}
      {kind === 'varswap' && <VarSwapView />}
    </div>
  )
}
