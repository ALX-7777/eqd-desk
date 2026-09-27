import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** Directory the Python parity tests read from (repo-root tests/parity/golden). */
export const GOLDEN_DIR = resolve(process.cwd(), '..', 'tests', 'parity', 'golden')

/**
 * Write one golden file. JSON.stringify emits the shortest round-trip representation of
 * every double, so Python's json.load recovers the exact same float64 values.
 */
export function writeGolden(name: string, data: unknown): void {
  mkdirSync(GOLDEN_DIR, { recursive: true })
  const payload = { generator: `web/scripts/golden/${name}.golden.ts`, data }
  writeFileSync(resolve(GOLDEN_DIR, `${name}.json`), JSON.stringify(payload) + '\n')
}
