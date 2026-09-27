/**
 * StrategyControls — preset picker, shared market params (S, r, q), and the
 * preset-build params (tenor, wing width). Presets rebuild the legs from spot and
 * the vol surface; editing legs by hand switches the structure to "custom".
 */

import type { MarketParams, PresetName } from '../engine'
import { PRESETS } from '../engine'
import { fmtPct } from './format'

interface StrategyControlsProps {
  market: MarketParams
  onMarketChange: (patch: Partial<MarketParams>) => void
  baseTDays: number
  widthPct: number
  onBaseTDaysChange: (d: number) => void
  onWidthPctChange: (w: number) => void
  currentPreset: PresetName | 'custom'
  onApplyPreset: (name: PresetName) => void
  onReset: () => void
  spot: number
  currency: string
}

interface CompactFieldProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  display: string
  onChange: (v: number) => void
}

function CompactField({ label, value, min, max, step, display, onChange }: CompactFieldProps) {
  const handle = (raw: string) => {
    const v = Number(raw)
    if (Number.isFinite(v)) onChange(v)
  }
  return (
    <div className="field compact">
      <div className="field-head">
        <span className="field-label">{label}</span>
        <span className="field-display mono">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => handle(e.target.value)}
        aria-label={label}
      />
    </div>
  )
}

export function StrategyControls({
  market,
  onMarketChange,
  baseTDays,
  widthPct,
  onBaseTDaysChange,
  onWidthPctChange,
  currentPreset,
  onApplyPreset,
  onReset,
  spot,
  currency,
}: StrategyControlsProps) {
  return (
    <div className="strategy-controls">
      <div className="panel-title-row">
        <h2 className="panel-title">Structure</h2>
        <span className="tag subtle">{currentPreset === 'custom' ? 'custom' : 'preset'}</span>
      </div>

      <div className="preset-grid">
        {PRESETS.map((p) => (
          <button
            key={p.name}
            className={`preset-btn ${currentPreset === p.name ? 'active' : ''}`}
            onClick={() => onApplyPreset(p.name)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="build-params">
        <label className="bp">
          <span className="dim">Tenor</span>
          <input
            type="number"
            className="mono num"
            min={1}
            step={1}
            value={baseTDays}
            onChange={(e) => onBaseTDaysChange(Math.max(1, Math.round(Number(e.target.value) || baseTDays)))}
          />
          <span className="dim">d</span>
        </label>
        <label className="bp">
          <span className="dim">Wing</span>
          <input
            type="number"
            className="mono num"
            min={1}
            step={1}
            value={Math.round(widthPct * 100)}
            onChange={(e) => onWidthPctChange(Math.max(1, Number(e.target.value) || widthPct * 100) / 100)}
          />
          <span className="dim">%</span>
        </label>
      </div>

      <CompactField
        label="Spot (S)"
        value={market.S}
        min={Math.round(spot * 0.6)}
        max={Math.round(spot * 1.4)}
        step={spot >= 2000 ? 1 : 0.5}
        display={`${market.S.toLocaleString('en-US', { maximumFractionDigits: 2 })} ${currency}`}
        onChange={(v) => onMarketChange({ S: v })}
      />
      <CompactField
        label="Rate (r)"
        value={market.r}
        min={-0.02}
        max={0.1}
        step={0.0005}
        display={fmtPct(market.r)}
        onChange={(v) => onMarketChange({ r: v })}
      />
      <CompactField
        label="Dividend yield (q)"
        value={market.q}
        min={0}
        max={0.06}
        step={0.0005}
        display={fmtPct(market.q)}
        onChange={(v) => onMarketChange({ q: v })}
      />

      <button className="btn" onClick={onReset} title="Reset market & rebuild the current preset">
        ⟲ Reset
      </button>
    </div>
  )
}
