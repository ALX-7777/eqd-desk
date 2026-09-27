/**
 * LegsEditor — the editable leg table for the Strategy Builder. Each leg shows
 * side (L/S), type (C/P), quantity, strike, expiry (days) and vol (points), all
 * inline-editable. Units are the trader-natural ones; conversions to the engine's
 * year-fraction T and decimal σ happen on change.
 */

import type { Leg, LegSide, OptionType } from '../engine'

interface LegsEditorProps {
  legs: Leg[]
  onUpdate: (id: string, patch: Partial<Leg>) => void
  onRemove: (id: string) => void
  onAdd: () => void
}

export function LegsEditor({ legs, onUpdate, onRemove, onAdd }: LegsEditorProps) {
  return (
    <div className="legs-editor">
      <div className="legs-head">
        <span>Side</span>
        <span>Type</span>
        <span className="ralign">Qty</span>
        <span className="ralign">Strike</span>
        <span className="ralign">Exp (d)</span>
        <span className="ralign">Vol %</span>
        <span />
      </div>

      {legs.length === 0 && <div className="legs-empty dim">No legs — pick a preset or add one.</div>}

      {legs.map((leg) => (
        <div className="leg-row" key={leg.id}>
          <button
            className={`mini-toggle ${leg.side === 'long' ? 'long' : 'short'}`}
            onClick={() => onUpdate(leg.id, { side: flipSide(leg.side) })}
            title="Toggle long / short"
          >
            {leg.side === 'long' ? 'L' : 'S'}
          </button>
          <button
            className={`mini-toggle ${leg.type === 'call' ? 'call' : 'put'}`}
            onClick={() => onUpdate(leg.id, { type: flipType(leg.type) })}
            title="Toggle call / put"
          >
            {leg.type === 'call' ? 'C' : 'P'}
          </button>
          <input
            className="mono leg-num"
            type="number"
            min={1}
            step={1}
            value={leg.quantity}
            onChange={(e) => onUpdate(leg.id, { quantity: Math.max(1, Math.round(num(e.target.value, leg.quantity))) })}
            aria-label="quantity"
          />
          <input
            className="mono leg-num"
            type="number"
            step={5}
            value={round2(leg.K)}
            onChange={(e) => onUpdate(leg.id, { K: num(e.target.value, leg.K) })}
            aria-label="strike"
          />
          <input
            className="mono leg-num"
            type="number"
            min={1}
            step={1}
            value={Math.round(leg.T * 365)}
            onChange={(e) => onUpdate(leg.id, { T: Math.max(1, num(e.target.value, leg.T * 365)) / 365 })}
            aria-label="expiry days"
          />
          <input
            className="mono leg-num"
            type="number"
            min={1}
            step={0.5}
            value={round2(leg.sigma * 100)}
            onChange={(e) => onUpdate(leg.id, { sigma: Math.max(0.01, num(e.target.value, leg.sigma * 100) / 100) })}
            aria-label="vol percent"
          />
          <button className="leg-remove" onClick={() => onRemove(leg.id)} title="Remove leg" aria-label="remove leg">
            ×
          </button>
        </div>
      ))}

      <button className="btn add-leg" onClick={onAdd}>
        + Add leg
      </button>
    </div>
  )
}

function flipSide(s: LegSide): LegSide {
  return s === 'long' ? 'short' : 'long'
}
function flipType(t: OptionType): OptionType {
  return t === 'call' ? 'put' : 'call'
}
function num(raw: string, fallback: number): number {
  const v = Number(raw)
  return Number.isFinite(v) ? v : fallback
}
function round2(x: number): number {
  return Math.round(x * 100) / 100
}
