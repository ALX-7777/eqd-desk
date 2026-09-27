/**
 * PositionReadout — net premium (debit/credit) hero plus the aggregate greeks of
 * the whole structure, grouped and clickable (selecting a greek drives the plot
 * and education panel). Mirrors the single-option readout but for a position.
 */

import type { PositionAnalysis } from '../engine'
import { GREEK_UNITS } from '../engine'
import { fmtNum, fmtMoney, signClass } from './format'
import { GREEK_DOCS, type GreekKey } from './education'

interface PositionReadoutProps {
  analysis: PositionAnalysis
  selectedGreek: GreekKey
  onSelectGreek: (k: GreekKey) => void
  currency: string
}

const GROUPS: { title: string; keys: GreekKey[] }[] = [
  { title: 'First order', keys: ['delta', 'vega', 'theta', 'rho'] },
  { title: 'Second order / cross', keys: ['gamma', 'vanna', 'volga', 'charm'] },
  { title: 'Third order', keys: ['speed', 'color'] },
]

export function PositionReadout({
  analysis,
  selectedGreek,
  onSelectGreek,
  currency,
}: PositionReadoutProps) {
  const { price, raw, reported } = analysis
  // price > 0 ⇒ you pay (debit); < 0 ⇒ you receive (credit).
  const isDebit = price >= 0
  const mag = Math.abs(price)

  return (
    <div className="readout">
      <div className="panel-title-row">
        <h2 className="panel-title">Net Position</h2>
        <span className={`tag ${isDebit ? '' : 'subtle'}`}>{isDebit ? 'DEBIT' : 'CREDIT'}</span>
      </div>

      <button
        className={`price-hero ${selectedGreek === 'price' ? 'sel' : ''}`}
        onClick={() => onSelectGreek('price')}
        title="Net premium of the structure (debit = you pay, credit = you receive)."
      >
        <div className={`price-hero-main mono ${isDebit ? '' : 'pos'}`}>
          {isDebit ? '−' : '+'}
          {fmtMoney(mag)}
        </div>
        <div className="price-hero-sub">
          <span>net premium ({currency})</span>
          <span className="dim">{isDebit ? 'you pay (debit)' : 'you receive (credit)'}</span>
        </div>
      </button>

      <table className="greeks-table">
        <tbody>
          {GROUPS.map((g) => (
            <GreekGroup
              key={g.title}
              title={g.title}
              keys={g.keys}
              reported={reported}
              raw={raw}
              selectedGreek={selectedGreek}
              onSelectGreek={onSelectGreek}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface GroupProps {
  title: string
  keys: GreekKey[]
  reported: PositionAnalysis['reported']
  raw: PositionAnalysis['raw']
  selectedGreek: GreekKey
  onSelectGreek: (k: GreekKey) => void
}

function GreekGroup({ title, keys, reported, raw, selectedGreek, onSelectGreek }: GroupProps) {
  return (
    <>
      <tr className="group-row">
        <td colSpan={3}>{title}</td>
      </tr>
      {keys.map((k) => {
        const value = reported[k]
        const unit = GREEK_UNITS[k]
        const sel = selectedGreek === k
        return (
          <tr
            key={k}
            className={`greek-row ${sel ? 'sel' : ''}`}
            onClick={() => onSelectGreek(k)}
            title={`raw ∂: ${raw[k].toPrecision(6)} — ${GREEK_DOCS[k].measures}`}
          >
            <td className="g-label">{unit.label}</td>
            <td className={`g-value mono ${signClass(value)}`}>{fmtNum(value)}</td>
            <td className="g-unit dim">{unit.unit}</td>
          </tr>
        )
      })}
    </>
  )
}
