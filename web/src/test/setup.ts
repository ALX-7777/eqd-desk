// Vitest global setup. Adds jest-dom matchers (toBeInTheDocument, etc.) for
// component tests, and polyfills browser APIs jsdom lacks but Recharts needs.
import '@testing-library/jest-dom'

// jsdom has no ResizeObserver; Recharts' ResponsiveContainer relies on it.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverStub as unknown as typeof ResizeObserver)

// Give ResponsiveContainer a non-zero box so charts render in tests.
if (typeof HTMLElement !== 'undefined') {
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, value: 800 })
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 400 })
}
