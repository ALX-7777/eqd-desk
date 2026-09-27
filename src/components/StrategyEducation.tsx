/**
 * StrategyEducation — the teaching panel for the Strategy Builder: the desk
 * rationale for the current structure (the view it expresses, its greek
 * signature and risk), then the per-greek education re-used from Phase 1.
 */

import { PRESETS, type PresetName } from '../engine'
import { STRATEGY_DOCS } from './strategyDocs'
import { EducationPanel } from './EducationPanel'
import type { GreekKey } from './education'

interface StrategyEducationProps {
  currentPreset: PresetName | 'custom'
  selectedGreek: GreekKey
  onSelectGreek: (k: GreekKey) => void
}

export function StrategyEducation({
  currentPreset,
  selectedGreek,
  onSelectGreek,
}: StrategyEducationProps) {
  const doc = currentPreset === 'custom' ? null : STRATEGY_DOCS[currentPreset]
  const label =
    currentPreset === 'custom'
      ? 'Custom structure'
      : (PRESETS.find((p) => p.name === currentPreset)?.label ?? currentPreset)

  return (
    <div className="education">
      <div className="panel-title-row">
        <h2 className="panel-title">Learn</h2>
        <span className="tag subtle">{label}</span>
      </div>

      {doc ? (
        <div className="edu-card">
          <h3 className="edu-title">{label}</h3>
          <dl className="edu-dl">
            <dt>The view</dt>
            <dd>{doc.view}</dd>
            <dt>Structure</dt>
            <dd>{doc.structure}</dd>
            <dt>Greek signature</dt>
            <dd>{doc.greeks}</dd>
            <dt>Principal risk</dt>
            <dd>{doc.risk}</dd>
          </dl>
        </div>
      ) : (
        <div className="edu-card">
          <p className="dim">
            Custom structure — edit the legs freely. Pick a preset to see its desk rationale.
          </p>
        </div>
      )}

      <h3 className="sub-head">Greek detail</h3>
      <EducationPanel selectedGreek={selectedGreek} onSelectGreek={onSelectGreek} embedded />
    </div>
  )
}
