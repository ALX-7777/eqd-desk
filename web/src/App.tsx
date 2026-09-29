/**
 * App — the shell: top bar (brand, view tabs, market strip) and the active view.
 * Phase 1 = Greeks Lab (single option); Phase 2 = Strategy Builder (multi-leg).
 */

import { useState } from 'react'
import './App.css'

import { snapshot } from './data/snapshot'
import { UNDERLYINGS } from './data/config'
import { GreeksLab } from './components/GreeksLab'
import { StrategyBuilder } from './components/StrategyBuilder'
import { ExoticsLab } from './components/ExoticsLab'
import { SimulatorView } from './components/SimulatorView'
import { fmtPct } from './components/format'

type View = 'lab' | 'builder' | 'exotics' | 'simulator'

export default function App() {
  const [view, setView] = useState<View>('lab')
  const cfg = UNDERLYINGS[snapshot.underlying as keyof typeof UNDERLYINGS] ?? UNDERLYINGS.spx

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">◤</span>
          <div>
            <div className="brand-title">EQD Desk</div>
            <div className="brand-sub dim">
              {snapshot.name} · BSM with dividend yield
            </div>
          </div>
        </div>

        <nav className="view-tabs" role="group" aria-label="view">
          <button className={`tab ${view === 'lab' ? 'active' : ''}`} onClick={() => setView('lab')}>
            Greeks Lab
          </button>
          <button
            className={`tab ${view === 'builder' ? 'active' : ''}`}
            onClick={() => setView('builder')}
          >
            Strategy Builder
          </button>
          <button
            className={`tab ${view === 'exotics' ? 'active' : ''}`}
            onClick={() => setView('exotics')}
          >
            Exotics
          </button>
          <button
            className={`tab ${view === 'simulator' ? 'active' : ''}`}
            onClick={() => setView('simulator')}
          >
            Simulator
          </button>
        </nav>

        <div className="market-strip mono">
          <Stat label={cfg.indexTicker} value={snapshot.spot.toLocaleString('en-US')} />
          <Stat label={`${cfg.volIndexTicker} (ATM 30d)`} value={fmtPct(snapshot.atm_vol_30d)} />
          <Stat label="r" value={fmtPct(snapshot.r)} />
          <Stat label="q" value={fmtPct(snapshot.q)} />
          <span className="seed-badge" title={snapshot.source_notes.join('\n')}>
            STATIC SEED · {snapshot.asof}
          </span>
        </div>
      </header>

      {view === 'lab' && <GreeksLab />}
      {view === 'builder' && <StrategyBuilder />}
      {view === 'exotics' && <ExoticsLab />}
      {/* The simulator stays mounted (hidden) so its book / P&L / session survive
          while you visit other tabs; it auto-pauses when you navigate away. */}
      <div className={`sim-host ${view === 'simulator' ? '' : 'hidden'}`}>
        <SimulatorView active={view === 'simulator'} />
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="stat">
      <span className="stat-label dim">{label}</span>
      <span className="stat-value">{value}</span>
    </span>
  )
}
