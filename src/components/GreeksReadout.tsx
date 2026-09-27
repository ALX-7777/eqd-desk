/**
 * GreeksReadout — the live numeric readout. Price hero (with intrinsic / time-
 * value split) plus a grouped, right-aligned table of every greek in desk units.
 * Hovering a value shows the raw partial; clicking a row selects that greek for
 * the plot and education panel.
 */

import type { OptionAnalysis } from '../engine'
import { GREEK_UNITS } from '../engine'
import { fmtNum, fmtMoney, signClass } from './format'
import { GREEK_DOCS, type GreekKey } from './education'

interface GreeksReadoutProps {
  analysis: OptionAnalysis
  selectedGreek: GreekKey
  onSelectGreek: (k: GreekKey) => void
  currency: string
}

const GROUPS: { title: string; keys: GreekKey[] }[] = [
  { title: 'First order', keys: ['delta', 'vega', 'theta', 'rho'] },
  { title: 'Second order / cross', keys: ['gamma', 'vanna', 'volga', 'charm'] },
  { title: 'Third order', keys: ['speed', 'color'] },
]

export function GreeksReadout({
  analysis,
  selectedGreek,
  onSelectGreek,
  currency,
}: GreeksReadoutProps) {
  const { inputs, type, raw, reported } = analysis
  const intrinsic =
    type === 'call' ? Math.max(inputs.S - inputs.K, 0) : Math.max(inputs.K - inputs.S, 0)
  const timeValue = reported.price - intrinsic

  return (
    <div className="readout">
      <div className="panel-title-row">
        <h2 className="panel-title">Price &amp; Greeks</h2>
        <span className="tag">{type.toUpperCase()}</span>
      </div>

      <button
        className={`price-hero ${selectedGreek === 'price' ? 'sel' : ''}`}
        onClick={() => onSelectGreek('price')}
        title={GREEK_DOCS.price.measures}
      >
        <div className="price-hero-main mono">{fmtMoney(reported.price)}</div>
        <div className="price-hero-sub">
          <span>premium ({currency})</span>
          <span className="dim">
            intrinsic {fmtMoney(intrinsic)} · time value {fmtMoney(timeValue)}
          </span>
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
  reported: OptionAnalysis['reported']
  raw: OptionAnalysis['raw']
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
