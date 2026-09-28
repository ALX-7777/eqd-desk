/**
 * Golden values for the in-app teaching content: every doc object the React UI imports
 * from src/components/*.ts (greek docs + key relationships, strategy docs, exotic docs,
 * simulator concepts + P&L-explain terms), plus the key/ordering lists that drive the
 * panels and the strategy preset names. The Python port (src/eqd_desk/content) must
 * reproduce every string EXACTLY (tests/parity/test_content_parity.py).
 */
import { GREEK_DOCS, GREEK_KEYS, PLOTTABLE_KEYS, KEY_RELATIONSHIPS } from '../../src/components/education'
import { STRATEGY_DOCS } from '../../src/components/strategyDocs'
import { EXOTIC_DOCS, EXOTIC_METRICS } from '../../src/components/exoticsDocs'
import { SIM_CONCEPTS, ATTRIBUTION_TERMS } from '../../src/components/simDocs'
import { PRESETS } from '../../src/engine/presets'
import { writeGolden } from './writeGolden'

it('exports content goldens', () => {
  writeGolden('content', {
    greekKeys: GREEK_KEYS,
    plottableKeys: PLOTTABLE_KEYS,
    greekDocs: GREEK_DOCS,
    keyRelationships: KEY_RELATIONSHIPS,
    presets: PRESETS,
    strategyDocs: STRATEGY_DOCS,
    exoticMetrics: EXOTIC_METRICS,
    exoticDocs: EXOTIC_DOCS,
    simConcepts: SIM_CONCEPTS,
    attributionTerms: ATTRIBUTION_TERMS,
  })
})
