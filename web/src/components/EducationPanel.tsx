/**
 * EducationPanel — the always-visible teaching surface. Shows the selected
 * greek's full explanation (what it measures, sign/size intuition, when it's
 * large, and how a desk uses it), a chip row to switch greek, and the standing
 * "key relationships" every trainee must internalise.
 */

import { GREEK_DOCS, GREEK_KEYS, KEY_RELATIONSHIPS, type GreekKey } from './education'
import { GREEK_UNITS } from '../engine'

interface EducationPanelProps {
  selectedGreek: GreekKey
  onSelectGreek: (k: GreekKey) => void
  /** When true, render without the "Learn" title row / outer wrapper (for embedding). */
  embedded?: boolean
}

export function EducationPanel({ selectedGreek, onSelectGreek, embedded = false }: EducationPanelProps) {
  const doc = GREEK_DOCS[selectedGreek]
  const unit = GREEK_UNITS[selectedGreek]

  const inner = (
    <>
      <div className="edu-chips">
        {GREEK_KEYS.map((k) => (
          <button
            key={k}
            className={`chip ${selectedGreek === k ? 'active' : ''}`}
            onClick={() => onSelectGreek(k)}
          >
            {GREEK_UNITS[k].label}
          </button>
        ))}
      </div>

      <div className="edu-card">
        <h3 className="edu-title">{doc.title}</h3>
        <dl className="edu-dl">
          <dt>Measures</dt>
          <dd>{doc.measures}</dd>
          <dt>Intuition</dt>
          <dd>{doc.intuition}</dd>
          <dt>When it's large</dt>
          <dd>{doc.whenLarge}</dd>
          <dt>On the desk</dt>
          <dd>{doc.desk}</dd>
        </dl>
      </div>

      <h3 className="sub-head">Key relationships</h3>
      <div className="edu-rels">
        {KEY_RELATIONSHIPS.map((r) => (
          <details key={r.title} className="rel">
            <summary>{r.title}</summary>
            <p>{r.body}</p>
          </details>
        ))}
      </div>
    </>
  )

  if (embedded) return inner

  return (
    <div className="education">
      <div className="panel-title-row">
        <h2 className="panel-title">Learn</h2>
        <span className="tag subtle">{unit.unit}</span>
      </div>
      {inner}
    </div>
  )
}
