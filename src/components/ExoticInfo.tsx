/**
 * ExoticInfo — the right-hand education panel for an exotic: the instrument's
 * desk doc (what / behaviour / risk) and, for the priced exotics, the selected
 * price/greek's explanation with a chip row that drives the plot metric.
 */

import { EXOTIC_DOCS, EXOTIC_METRICS, type ExoticKind, type ExoticMetric } from './exoticsDocs'
import { GREEK_DOCS } from './education'
import { GREEK_UNITS } from '../engine'

interface ExoticInfoProps {
  kind: ExoticKind
  /** Selected metric (drives both the plot and which greek doc is shown). */
  metric?: ExoticMetric
  onSelectMetric?: (m: ExoticMetric) => void
  /** Show the price/greek chips + doc (false for the variance swap). */
  showGreeks?: boolean
}

export function ExoticInfo({ kind, metric = 'price', onSelectMetric, showGreeks = true }: ExoticInfoProps) {
  const doc = EXOTIC_DOCS[kind]
  const greek = GREEK_DOCS[metric]

  return (
    <div className="education">
      <div className="panel-title-row">
        <h2 className="panel-title">Learn</h2>
        <span className="tag subtle">exotic</span>
      </div>

      <div className="edu-card">
        <h3 className="edu-title">{doc.title}</h3>
        <dl className="edu-dl">
          <dt>What it is</dt>
          <dd>{doc.what}</dd>
          <dt>Behaviour</dt>
          <dd>{doc.behaviour}</dd>
          <dt>Principal risk</dt>
          <dd>{doc.risk}</dd>
        </dl>
      </div>

      {showGreeks && (
        <>
          <h3 className="sub-head">Price &amp; greeks</h3>
          <div className="edu-chips">
            {EXOTIC_METRICS.map((m) => (
              <button
                key={m}
                className={`chip ${metric === m ? 'active' : ''}`}
                onClick={() => onSelectMetric?.(m)}
              >
                {GREEK_UNITS[m].label}
              </button>
            ))}
          </div>
          <div className="edu-card">
            <h3 className="edu-title">{greek.title}</h3>
            <dl className="edu-dl">
              <dt>Measures</dt>
              <dd>{greek.measures}</dd>
              <dt>Intuition</dt>
              <dd>{greek.intuition}</dd>
            </dl>
          </div>
        </>
      )}
    </div>
  )
}
