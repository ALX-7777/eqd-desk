/// <reference types="vitest/config" />
import { defineConfig } from 'vite'

// Golden-value exporters: each *.golden.ts runs the TS engine over a fixed grid of inputs
// and writes the results to ../tests/parity/golden/<name>.json. The Python engine's parity
// tests (tests/parity/) assert it reproduces these numbers. Run with `npm run golden`.
export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['scripts/golden/**/*.golden.ts'],
  },
})
