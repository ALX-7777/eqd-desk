// @vitest-environment jsdom
/**
 * Golden values for the Streamlit simulator's SESSION layer
 * (src/eqd_desk/app/ui/sim_session.py + simulator_display.py).
 *
 * Unlike the engine goldens, this one drives the REAL React spec: it renders
 * <SimulatorView/> in jsdom, runs a scripted desk session through the component's own
 * buttons, sliders and inputs (Tick, Auto on fake timers, Request a quote, spread/lean,
 * Quote/Pass, the three flatten buttons, every trade-ticket kind, the advisor's "Load into
 * ticket" and combined hedge, Reset, Simulated/Replay, replay length), and after EVERY action
 * records:
 *
 * - `dom`: what the screen shows (market stats, scorecard, the RFQ queue and quote box, the
 *   fill message, the P&L hero, book greeks, the positions blotter, the ticket preview, the
 *   advisor) as the rendered text + the tone class of each value;
 * - `state`: the component's internal SimState read from its React fiber, at full float
 *   precision (market, day, queue, fills, cumulative P&L explain, book, trades, history).
 *
 * The Python parity test (tests/ui/test_sim_session_parity.py) replays the SAME actions on
 * the Python session (same seeds, same draw order) and must reproduce both.
 *
 * Run: cd web && npx vitest run --config vitest.golden.config.ts scripts/golden/simsession.golden.ts
 *
 * Note: rendered WITHOUT <StrictMode> (like the production build). In a dev build React
 * double-invokes state updaters, and SimulatorView draws random numbers inside its updaters,
 * so the dev server's seeded stream differs from production's; the Python port follows the
 * production (single-invocation) semantics.
 */
import { createElement } from 'react'
import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { vi } from 'vitest'
import { SimulatorView } from '../../src/components/SimulatorView'
import { writeGolden } from './writeGolden'

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverStub as unknown as typeof ResizeObserver)
if (typeof HTMLElement !== 'undefined') {
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, value: 800 })
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 400 })
}

// ---------------------------------------------------------------------------- the script

type TicketKind = 'option' | 'structure' | 'future'
interface TicketSpec {
  kind?: TicketKind
  side?: 'long' | 'short'
  type?: 'call' | 'put'
  K?: number
  days?: number
  size?: number
  /** preset button label (structure only) */
  preset?: string
  /** wing % (structure only) */
  wing?: number
}

type Action =
  | { kind: 'tick' }
  | { kind: 'auto'; ticks: number }
  | { kind: 'request' }
  | { kind: 'select'; index: number }
  | { kind: 'spread'; value: number }
  | { kind: 'lean'; value: number }
  | { kind: 'quote' }
  | { kind: 'pass' }
  | { kind: 'flattenDelta' }
  | { kind: 'flattenVega' }
  | { kind: 'flattenGamma' }
  | { kind: 'ticket'; tk: TicketSpec }
  | { kind: 'execute' }
  | { kind: 'advisor' }
  | { kind: 'loadPlan'; index: number }
  | { kind: 'executeJoint' }
  | { kind: 'closeAdvisor' }
  | { kind: 'reset' }
  | { kind: 'mode'; value: 'simulated' | 'historical' }
  | { kind: 'replayLen'; value: number }
  | { kind: 'speed'; value: number }

const T = (n: number): Action[] => Array.from({ length: n }, () => ({ kind: 'tick' }) as Action)

const SCRIPT: Action[] = [
  // a few quiet days, then the first client flow
  ...T(3),
  { kind: 'request' },
  { kind: 'request' },
  { kind: 'spread', value: 0.03 },
  { kind: 'lean', value: 0.0075 },
  { kind: 'quote' },
  { kind: 'lean', value: -0.01 },
  { kind: 'quote' },
  { kind: 'request' },
  { kind: 'pass' },
  { kind: 'flattenDelta' },
  // the market runs on Auto: RFQs arrive (seeded) and expire after 4 days
  { kind: 'speed', value: 300 },
  { kind: 'auto', ticks: 12 },
  { kind: 'select', index: 1 },
  { kind: 'spread', value: 0.005 },
  { kind: 'lean', value: 0 },
  { kind: 'quote' },
  { kind: 'quote' },
  { kind: 'spread', value: 0.2 },
  { kind: 'quote' },
  { kind: 'flattenVega' },
  { kind: 'flattenGamma' },
  // every trade-ticket kind
  { kind: 'ticket', tk: { kind: 'option', side: 'short', type: 'put', K: 6200, days: 30, size: 20 } },
  { kind: 'execute' },
  { kind: 'ticket', tk: { kind: 'structure', preset: 'Risk reversal', side: 'long', wing: 4, days: 45, size: 3 } },
  { kind: 'execute' },
  { kind: 'ticket', tk: { kind: 'structure', preset: 'Butterfly', side: 'short', wing: 3, days: 20, size: 2 } },
  { kind: 'execute' },
  { kind: 'ticket', tk: { kind: 'structure', preset: 'Calendar', side: 'long', days: 25, size: 4 } },
  { kind: 'execute' },
  { kind: 'ticket', tk: { kind: 'future', side: 'short', size: 7 } },
  { kind: 'execute' },
  ...T(2),
  // the desk advisor: load its first plan into the ticket and execute it
  { kind: 'advisor' },
  { kind: 'loadPlan', index: 0 },
  { kind: 'execute' },
  { kind: 'advisor' },
  { kind: 'loadPlan', index: 1 },
  { kind: 'execute' },
  { kind: 'advisor' },
  { kind: 'executeJoint' },
  { kind: 'closeAdvisor' },
  // a long auto run: the queue fills up (max 4) and stale RFQs expire
  { kind: 'auto', ticks: 30 },
  { kind: 'spread', value: 0.01 },
  { kind: 'quote' },
  { kind: 'quote' },
  { kind: 'lean', value: 0.02 },
  { kind: 'quote' },
  { kind: 'lean', value: -0.02 },
  { kind: 'quote' },
  { kind: 'request' },
  { kind: 'request' },
  { kind: 'request' },
  { kind: 'request' },
  { kind: 'request' },
  { kind: 'select', index: 2 },
  { kind: 'pass' },
  { kind: 'flattenDelta' },
  ...T(3),
  { kind: 'advisor' },
  { kind: 'closeAdvisor' },
  // a fresh session (new seeds for the market, client noise and arrivals; RFQ stream goes on)
  { kind: 'reset' },
  ...T(2),
  { kind: 'request' },
  { kind: 'spread', value: 0.02 },
  { kind: 'lean', value: 0 },
  { kind: 'quote' },
  { kind: 'auto', ticks: 8 },
  { kind: 'quote' },
  { kind: 'ticket', tk: { kind: 'option', side: 'long', type: 'call', K: 6400, days: 90, size: 15 } },
  { kind: 'execute' },
  { kind: 'flattenDelta' },
  // historical replay: an undisclosed window of real ^GSPC / ^VIX
  { kind: 'mode', value: 'historical' },
  ...T(3),
  { kind: 'request' },
  { kind: 'spread', value: 0.015 },
  { kind: 'quote' },
  { kind: 'flattenDelta' },
  { kind: 'auto', ticks: 10 },
  { kind: 'advisor' },
  { kind: 'closeAdvisor' },
  // a short episode that runs to its end (auto pauses; Tick is disabled)
  { kind: 'replayLen', value: 30 },
  { kind: 'reset' },
  { kind: 'request' },
  { kind: 'quote' },
  { kind: 'auto', ticks: 40 },
  { kind: 'tick' },
  { kind: 'auto', ticks: 2 },
  { kind: 'quote' },
  { kind: 'flattenGamma' },
  // back to the simulated market
  { kind: 'mode', value: 'simulated' },
  ...T(2),
  { kind: 'request' },
  { kind: 'quote' },
]

// ---------------------------------------------------------------------------- DOM reading

const txt = (el: Element | null | undefined): string => (el?.textContent ?? '').trim()
const kids = (el: Element): string[] => Array.from(el.children).map((c) => txt(c))

const TONES = ['pos', 'neg', 'zero', 'accent', 'dim'] as const
/** The tone class of a value span ("" when uncoloured). */
const tone = (el: Element | null | undefined): string => (el ? TONES.find((t) => el.classList.contains(t)) ?? '' : '')

function panels(): Element[] {
  return Array.from(document.querySelectorAll('.panel'))
}

/** First button in `scope` whose trimmed text equals `name` (or matches the regex). */
function button(scope: Element, name: string | RegExp): HTMLButtonElement | null {
  const all = Array.from(scope.querySelectorAll('button')) as HTMLButtonElement[]
  return all.find((b) => (typeof name === 'string' ? txt(b) === name : name.test(txt(b)))) ?? null
}

function buttons(scope: Element, name: RegExp): HTMLButtonElement[] {
  return (Array.from(scope.querySelectorAll('button')) as HTMLButtonElement[]).filter((b) => name.test(txt(b)))
}

function statRows(p: Element): [string, string, string][] {
  return Array.from(p.querySelectorAll('.sim-stats > div')).map((d) => {
    const [label, value] = Array.from(d.children)
    return [txt(label), txt(value), tone(value)]
  })
}

function fieldDisplays(p: Element): [string, string][] {
  return Array.from(p.querySelectorAll('.field')).map((f) => [txt(f.querySelector('.field-label')), txt(f.querySelector('.field-display'))])
}

function observeDom() {
  const [mk, sc, rq, pl, bk, tk] = panels()
  const box = rq.querySelector('.quote-box')
  const impact = box?.querySelector('.rfq-impact')
  const fill = rq.querySelector('.fill-msg')
  const overlay = document.querySelector('.advisor-card')
  return {
    market: statRows(mk),
    marketFields: fieldDisplays(mk),
    marketCaptions: Array.from(mk.querySelectorAll('.chart-caption')).map((c) => txt(c)),
    episodeEnded: mk.querySelector('.fill-msg') ? txt(mk.querySelector('.fill-msg')) : null,
    tickDisabled: button(mk, /Tick/)!.disabled,
    autoButton: txt(button(mk, /Auto|Pause/)),
    autoDisabled: button(mk, /Auto|Pause/)!.disabled,
    scorecard: statRows(sc),
    rfqTag: txt(rq.querySelector('.tag')),
    emptyQueue: rq.querySelector('.rfq-queue > .dim') ? txt(rq.querySelector('.rfq-queue > .dim')) : null,
    chips: Array.from(rq.querySelectorAll('.rfq-chip')).map((c) => ({
      active: c.classList.contains('active'),
      text: kids(c),
      flagTitle: c.querySelector('.rfq-flag')?.getAttribute('title') ?? '',
    })),
    quoteBox: box
      ? {
          detail: txt(box.querySelector('.rfq-detail')),
          impact: impact ? { verdict: impact.className.replace('rfq-impact', '').trim(), text: txt(impact) } : null,
          fields: fieldDisplays(box),
          bid: txt(box.querySelector('.quote-bid')),
          ask: txt(box.querySelector('.quote-ask')),
        }
      : null,
    requestDisabled: button(rq, /Request a quote/)!.disabled,
    fill: fill ? { won: fill.classList.contains('won'), text: txt(fill) } : null,
    pnl: {
      tag: txt(pl.querySelector('.tag')),
      main: txt(pl.querySelector('.price-hero-main')),
      mainTone: tone(pl.querySelector('.price-hero-main')),
      sub: kids(pl.querySelector('.price-hero-sub')!),
    },
    book: Array.from(bk.querySelectorAll('.greeks-table tr')).map((r) => {
      const [label, value] = Array.from(r.children)
      return [txt(label), txt(value), tone(value)]
    }),
    positionsHead: txt(bk.querySelector('.sub-head')),
    blotter: Array.from(bk.querySelectorAll('.blotter-row')).map((r) => kids(r)),
    blotterTones: Array.from(bk.querySelectorAll('.blotter-row')).map((r) => tone(r.children[0])),
    emptyBook: bk.querySelector('.blotter > .dim') ? txt(bk.querySelector('.blotter > .dim')) : null,
    ticket: {
      active: Array.from(tk.querySelectorAll('.seg-btn.active, .preset-btn.active')).map((b) => txt(b)),
      inputs: Array.from(tk.querySelectorAll('.tk-field')).map((f) => [txt(f.querySelector('span')), (f.querySelector('input') as HTMLInputElement).value]),
      preview: kids(tk.querySelector('.quote-row')!),
    },
    advisor: overlay
      ? {
          subtitle: txt(overlay.querySelector('.advisor-head .dim')),
          items: Array.from(overlay.querySelectorAll('.advice')).map((a) => ({
            severity: (a.className.match(/sev-(\w+)/) ?? ['', ''])[1],
            title: txt(a.querySelector('.advice-title')),
            detail: txt(a.querySelector('.advice-detail')),
            plan: a.querySelector('.advice-plan')
              ? { line: kids(a.querySelector('.plan-line')!), why: txt(a.querySelector('.plan-why')) }
              : null,
          })),
          joint: overlay.querySelector('.joint-hedge')
            ? {
                head: kids(overlay.querySelector('.joint-head')!),
                legs: Array.from(overlay.querySelectorAll('.joint-legs .plan-line')).map((l) => kids(l)),
                why: txt(overlay.querySelector('.joint-hedge .plan-why')),
              }
            : null,
        }
      : null,
  }
}

// ---------------------------------------------------------------------------- internal state

/* eslint-disable @typescript-eslint/no-explicit-any */
let container: HTMLElement

/** The SimulatorView fiber's hooks (current tree). */
function hooks(): any[] {
  const key = Object.keys(container).find((k) => k.startsWith('__reactContainer$'))!
  const root = (container as any)[key].stateNode
  let f = root.current.child
  while (f && f.type !== SimulatorView) f = f.child
  const out: any[] = []
  let h = f.memoizedState
  while (h) {
    out.push(h.memoizedState)
    h = h.next
  }
  return out
}

function simState(): any {
  return hooks().find((s) => s && typeof s === 'object' && 'cumAttr' in s && 'book' in s)
}

function replayWindow(): any {
  const ref = hooks().find((s) => s && typeof s === 'object' && 'current' in s && s.current && typeof s.current === 'object' && 'startIndex' in s.current)
  return ref ? ref.current : null
}

const rfqOut = (r: any) => [r.id, r.label, r.clientSide, r.size, r.bornDay, r.legs.map((l: any) => [l.type, l.side, l.ratio, l.K, l.T])]
const tradeOut = (t: any) => [t.id, t.type, t.side, t.quantity, t.K, t.expiryTime, t.tradedPrice]
const marketOut = (m: any) => [m.t, m.spot, m.atmVol, m.r, m.q, m.skewSlope, m.skewCurv]

let lastTradeCount = -1
let lastHistLen = -1
function observeState() {
  const s = simState()
  const b = s.book
  const trades = b.trades.length !== lastTradeCount ? b.trades.map(tradeOut) : null
  lastTradeCount = b.trades.length
  const win = replayWindow()
  const hist = s.history.length !== lastHistLen ? s.history.map((h: any) => [h.day, h.spot, h.vol, h.pnl]) : null
  lastHistLen = s.history.length
  return {
    day: s.day,
    quotes: s.quotes,
    fills: s.fills,
    selectedId: s.selectedId,
    market: marketOut(s.market),
    queue: s.queue.map(rfqOut),
    fill: s.fill,
    cumAttr: [s.cumAttr.delta, s.cumAttr.gamma, s.cumAttr.theta, s.cumAttr.vega, s.cumAttr.vanna, s.cumAttr.volga, s.cumAttr.residual],
    book: [b.cash, b.underlyingQty, b.realizedEdge, b.totalCosts, b.nextId, b.trades.length],
    trades,
    history: hist,
    replayStart: win ? win.startIndex : null,
  }
}

// ---------------------------------------------------------------------------- actions

let autoDelay = 650

function setRange(scope: Element, label: string, value: number): number {
  const input = scope.querySelector(`input[aria-label="${label}"]`) as HTMLInputElement
  fireEvent.change(input, { target: { value: String(value) } })
  return Number(input.value)
}

function setField(scope: Element, label: string, value: number): number {
  const field = Array.from(scope.querySelectorAll('.tk-field')).find((f) => txt(f.querySelector('span')) === label)!
  const input = field.querySelector('input') as HTMLInputElement
  fireEvent.change(input, { target: { value: String(value) } })
  return Number(input.value)
}

function click(b: HTMLButtonElement | null): boolean {
  if (!b || b.disabled) return false
  fireEvent.click(b)
  return true
}

/** Apply one action; returns whether it did anything and the values the component took. */
function apply(a: Action): { applied: boolean; resolved?: Record<string, unknown> } {
  const [mk, , rq, , bk, tk] = panels()
  const overlay = () => document.querySelector('.advisor-card')
  switch (a.kind) {
    case 'tick':
      return { applied: click(button(mk, /Tick/)) }
    case 'auto': {
      if (!click(button(mk, /Auto/))) return { applied: false }
      let ran = 0
      for (let i = 0; i < a.ticks; i++) {
        if (!button(panels()[0], /Pause/)) break
        act(() => {
          vi.advanceTimersByTime(autoDelay)
        })
        ran++
      }
      const pause = button(panels()[0], /Pause/)
      if (pause) click(pause)
      return { applied: true, resolved: { ran } }
    }
    case 'request':
      return { applied: click(button(rq, /Request a quote/)) }
    case 'select': {
      const chips = rq.querySelectorAll('.rfq-chip')
      if (a.index >= chips.length) return { applied: false }
      fireEvent.click(chips[a.index])
      return { applied: true }
    }
    case 'spread':
    case 'lean': {
      const box = rq.querySelector('.quote-box')
      if (!box) return { applied: false }
      const v = setRange(box, a.kind === 'spread' ? 'Your spread' : 'Lean (skew your price)', a.value)
      return { applied: true, resolved: { value: v } }
    }
    case 'quote':
      return { applied: click(button(rq, /^Quote$/)) }
    case 'pass':
      return { applied: click(button(rq, /^Pass$/)) }
    case 'flattenDelta':
      return { applied: click(button(bk, 'Flatten Δ (future)')) }
    case 'flattenVega':
      return { applied: click(button(bk, 'Flatten vega (opt)')) }
    case 'flattenGamma':
      return { applied: click(button(bk, 'Flatten Γ (opt)')) }
    case 'ticket': {
      const s = a.tk
      const resolved: Record<string, unknown> = {}
      if (s.kind) click(button(tk, s.kind === 'option' ? 'Option' : s.kind === 'structure' ? 'Structure' : 'Future'))
      const t2 = panels()[5]
      if (s.preset) click(button(t2, s.preset))
      if (s.side) click(button(t2, s.side === 'long' ? 'Buy' : 'Sell'))
      if (s.type) click(button(t2, s.type === 'call' ? 'Call' : 'Put'))
      if (s.K !== undefined) resolved.K = setField(t2, 'Strike', s.K)
      if (s.wing !== undefined) resolved.widthPct = setField(t2, 'Wing %', s.wing) / 100
      if (s.days !== undefined) resolved.days = setField(t2, 'Exp (d)', s.days)
      if (s.size !== undefined) resolved.size = setField(t2, 'Size', s.size)
      return { applied: true, resolved }
    }
    case 'execute':
      return { applied: click(button(tk, 'Execute @ market')) }
    case 'advisor':
      return { applied: click(button(bk, /Advisor/)) }
    case 'loadPlan': {
      const card = overlay()
      if (!card) return { applied: false }
      const loads = buttons(card, /Load into ticket/)
      if (a.index >= loads.length) {
        click(card.querySelector('button[aria-label="close advisor"]'))
        return { applied: false }
      }
      fireEvent.click(loads[a.index])
      return { applied: true }
    }
    case 'executeJoint': {
      const card = overlay()
      if (!card) return { applied: false }
      return { applied: click(button(card, /Execute combined hedge/)) }
    }
    case 'closeAdvisor': {
      const card = overlay()
      if (!card) return { applied: false }
      return { applied: click(card.querySelector('button[aria-label="close advisor"]')) }
    }
    case 'reset':
      return { applied: click(button(mk, /Reset session/)) }
    case 'mode':
      return { applied: click(button(mk, a.value === 'simulated' ? 'Simulated' : 'Replay')) }
    case 'replayLen': {
      if (!mk.querySelector('input[aria-label="Replay length"]')) return { applied: false }
      return { applied: true, resolved: { value: setRange(mk, 'Replay length', a.value) } }
    }
    case 'speed': {
      autoDelay = setRange(mk, 'Auto speed', a.value)
      return { applied: true, resolved: { value: autoDelay } }
    }
  }
}

// ---------------------------------------------------------------------------- export

it('exports the scripted SimulatorView session', () => {
  // Recharts warns that jsdom gives its containers no size; the charts are not read here.
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  try {
    container = render(createElement(SimulatorView)).container
    const steps: unknown[] = [{ action: { kind: 'init' }, applied: true, dom: observeDom(), state: observeState() }]
    for (const a of SCRIPT) {
      const r = apply(a)
      steps.push({ action: a, applied: r.applied, resolved: r.resolved ?? null, dom: observeDom(), state: observeState() })
    }
    writeGolden('simsession', { steps })
  } finally {
    cleanup()
    vi.useRealTimers()
    warn.mockRestore()
  }
}, 300_000)
