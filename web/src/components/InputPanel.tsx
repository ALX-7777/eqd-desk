/**
 * InputPanel — the control surface for the option. Paired slider + numeric field
 * for each BSM input, a call/put toggle, reset-to-snapshot, and a convenience
 * "σ ← surface" button that snaps vol to the seed skew at the current strike/tenor
 * (so the skew is something you can feel, not just read about).
 */

import type { BsmInputs, OptionType } from '../engine'
import { fmtPct } from './format'

interface Bounds {
  min: number
  max: number
  step: number
}

interface FieldProps {
  label: string
  sub?: string
  value: number
  bounds: Bounds
  display: string
  onChange: (v: number) => void
}

function Field({ label, sub, value, bounds, display, onChange }: FieldProps) {
  const handle = (raw: string) => {
    const v = Number(raw)
    if (Number.isFinite(v)) onChange(v)
  }
  return (
    <div className="field">
      <div className="field-head">
        <span className="field-label">
          {label}
          {sub && <span className="field-sub">{sub}</span>}
        </span>
        <span className="field-display mono">{display}</span>
      </div>
      <div className="field-controls">
        <input
          type="range"
          min={bounds.min}
          max={bounds.max}
          step={bounds.step}
          value={value}
          onChange={(e) => handle(e.target.value)}
          aria-label={`${label} slider`}
        />
        <input
          type="number"
          className="mono num"
          min={bounds.min}
          max={bounds.max}
          step={bounds.step}
          value={value}
          onChange={(e) => handle(e.target.value)}
          aria-label={`${label} value`}
        />
      </div>
    </div>
  )
}

interface InputPanelProps {
  inputs: BsmInputs
  type: OptionType
  spot: number
  currency: string
  onChange: (patch: Partial<BsmInputs>) => void
  onTypeChange: (t: OptionType) => void
  onReset: () => void
  surfaceVol: (K: number, T: number) => number
}

export function InputPanel({
  inputs,
  type,
  spot,
  currency,
  onChange,
  onTypeChange,
  onReset,
  surfaceVol,
}: InputPanelProps) {
  const px = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return (
    <div className="input-panel">
      <div className="panel-title-row">
        <h2 className="panel-title">Inputs</h2>
        <div className="seg" role="group" aria-label="option type">
          <button
            className={`seg-btn ${type === 'call' ? 'active call' : ''}`}
            onClick={() => onTypeChange('call')}
          >
            CALL
          </button>
          <button
            className={`seg-btn ${type === 'put' ? 'active put' : ''}`}
            onClick={() => onTypeChange('put')}
          >
            PUT
          </button>
        </div>
      </div>

      <Field
        label="Spot"
        sub="S"
        value={inputs.S}
        bounds={{ min: round(spot * 0.6), max: round(spot * 1.4), step: stepFor(spot) }}
        display={`${px(inputs.S)} ${currency}`}
        onChange={(v) => onChange({ S: v })}
      />
      <Field
        label="Strike"
        sub="K"
        value={inputs.K}
        bounds={{ min: round(spot * 0.6), max: round(spot * 1.4), step: stepFor(spot) }}
        display={`${px(inputs.K)} ${currency}`}
        onChange={(v) => onChange({ K: v })}
      />
      <Field
        label="Time to expiry"
        sub="T"
        value={inputs.T}
        bounds={{ min: 0.003, max: 2, step: 0.003 }}
        display={`${inputs.T.toFixed(3)} y · ${Math.round(inputs.T * 365)} d`}
        onChange={(v) => onChange({ T: v })}
      />
      <Field
        label="Volatility"
        sub="σ"
        value={inputs.sigma}
        bounds={{ min: 0.02, max: 1, step: 0.0025 }}
        display={fmtPct(inputs.sigma)}
        onChange={(v) => onChange({ sigma: v })}
      />
      <Field
        label="Rate"
        sub="r"
        value={inputs.r}
        bounds={{ min: -0.02, max: 0.1, step: 0.0005 }}
        display={fmtPct(inputs.r)}
        onChange={(v) => onChange({ r: v })}
      />
      <Field
        label="Dividend yield"
        sub="q"
        value={inputs.q}
        bounds={{ min: 0, max: 0.06, step: 0.0005 }}
        display={fmtPct(inputs.q)}
        onChange={(v) => onChange({ q: v })}
      />

      <div className="input-actions">
        <button className="btn" onClick={onReset} title="Restore the seed snapshot inputs">
          ⟲ Reset to snapshot
        </button>
        <button
          className="btn"
          onClick={() => onChange({ sigma: surfaceVol(inputs.K, inputs.T) })}
          title="Set σ to the seed vol surface at this strike & tenor (shows the skew)"
        >
          σ ← surface
        </button>
      </div>
    </div>
  )
}

function round(x: number): number {
  return Math.round(x)
}

function stepFor(spot: number): number {
  if (spot >= 2000) return 1
  if (spot >= 200) return 0.5
  return 0.1
}
