# EQD Desk — Index Trader Book Training Simulator

*(Project name is a placeholder — rename freely. Default underlying: S&P 500 / SPX.)*

A browser-based training app that replicates the daily activity of an **equity-derivatives (EQD) index market-maker** for interview prep. The goal is **realistic activity + educational depth**, NOT market-data accuracy or refresh speed. This is a tool to *learn from and train on*. Optimise every decision for clarity, correctness, and teaching value over realism of live data.

The intended user is a student preparing for EQD trading internships. They want to (1) build deep intuition for the greeks of vanillas, strategies, and a whole book, and (2) practise the market-making loop: a client asks, you quote a two-way price, you win/lose the trade, you're left with risk, you hedge, and at end-of-day you attribute your P&L.

---

## Underlying (configurable)

The underlying is a **config object**, not a hardcoded value, so it can be swapped with one flag. Two presets are provided; **S&P 500 is the default**.

**S&P 500 (SPX) — default.** USD-denominated, index ≈ 5,000–6,500 in recent history; options/futures on CBOE/CME. Dividend yield is modest (~1.3%, time-varying) but still a real input — keep `q` in the model and UI. Vol gauge: **VIX**. Richest free data (see Data seeding), which is why it's the default.

**Euro Stoxx 50 (SX5E) — alternate.** EUR-denominated; options/futures on Eurex. Dividend yield is larger (~3%) and SX5E dividend risk / dividend futures are notable desk topics. Vol gauge: **VSTOXX**. Kept available as a one-flag switch for European-desk relevance.

A config carries: `name, indexTicker, volIndexTicker, optionsProxy, currency, defaultDivYield`. Presets:
```
SPX:   { indexTicker: "^GSPC",      volIndexTicker: "^VIX",    optionsProxy: "SPY", currency: "USD", defaultDivYield: 0.013 }
SX5E:  { indexTicker: "^STOXX50E",  volIndexTicker: "V2TX.DE", optionsProxy: "FEZ", currency: "EUR", defaultDivYield: 0.03 }
```

---

## Core principles (these shape every decision)

- **Transparent pricing.** Implement Black–Scholes–Merton and all greeks **from scratch** in clear, documented pure functions. Do **not** use a black-box options library for the core vanilla math — the implementation *is* part of the educational value. Heavy libraries are acceptable only for exotics Monte Carlo if genuinely needed, and even then prefer readable code.
- **Compute our own greeks.** Always analytically from BSM (validated against finite differences — see Conventions). Never trust any third-party IV or greek values.
- **Simulated market, not live.** Drive the interactive "market moves and I react" loop with a **simulated price/vol path** (start with GBM; design the interface so a Heston-style spot+vol process can be dropped in later). Real data is used only to *seed a realistic starting snapshot* (see Data seeding) and optionally for historical replay. Controllable and repeatable beats real-time.
- **The vol surface must move with spot.** Model the leverage effect (spot down → vol up, whole surface shifts), so equity skew and the cross-greeks (vanna, volga) actually bite and hedging decisions become real instead of cosmetic. A static surface teaches the wrong lessons.
- **Education is a first-class feature.** Every instrument, greek, strategy, and the P&L decomposition ships with an in-app explanation panel: plain-language description of what it is, the sign/size intuition, and its risks. Not an afterthought, not a tooltip — a visible, well-written panel beside each tool.

---

## Data seeding

Index option chains (`^GSPC`, `^STOXX50E`) are **not** reliably available through yfinance. Do **not** build anything that depends on fetching them. Instead, a Python script in `/scripts` (`fetch_snapshot.py`, already provided, `--underlying spx|sx5e`) produces a JSON snapshot the app loads:

- **Spot + realized vol:** the `indexTicker` (e.g. `^GSPC`) — the real index level; daily history → realized vol.
- **ATM implied-vol anchor:** the `volIndexTicker` (e.g. `^VIX`, in vol points; 16 → 0.16). Sets the 30-day at-the-money level.
- **Skew + term structure:** the `optionsProxy` (e.g. **`SPY`**, the only *fetchable* real chain — and for SPX it is deep and high quality). Extract implied vol vs log-moneyness across a few expiries. The skew shape is fit in **log-moneyness** so it is scale-free and transfers from the proxy to the index directly (SPY ≈ SPX/10, but the fitted slope/curvature don't care). Use the proxy for the surface *shape* and the vol index for the ATM *level*. Defensive fallback: a parametric equity skew (downward-sloping in strike) anchored to the vol index if proxy data is sparse.
- **Dividend yield `q`:** estimated, or the config default, written into the snapshot.
- **Rate `r`:** a configurable short-rate placeholder in the snapshot — set it to the current level; don't hardcode silently.

Snapshot JSON shape: `{ asof, underlying, currency, spot, r, q, realized_vol, atm_vol_30d, skew: {atm, slope, curv}, term_structure: [{t, atm_iv}], source_notes }`. The app builds its initial vol surface from `atm_vol_30d` + `skew` (+ `term_structure` if present), then evolves it with the simulated path. Keep all data fetching **out** of the reactive loop.

---

## Tech stack

- **React + TypeScript**, scaffolded with **Vite**.
- **Charting:** pick one interactive library suited to financial plots (Recharts is fine to start; Plotly/visx are alternatives) and use it consistently.
- **State:** keep it simple — React state, lift to Zustand only if it gets unwieldy.
- **Engine is pure TypeScript** in `/src/engine`, with **zero UI dependencies** and full unit-test coverage.
- **Python** in `/scripts` for the yfinance snapshot generator, writing JSON into `/src/data`.
- **Aesthetic:** a clean, dense "trading terminal" feel — dark background, monospace for numerics, tight grids, fast-reading layout. Numbers are the product; make them legible and aligned.

---

## Folder structure

```
/src/engine      pure functions: bsm pricing, greeks (all orders), strategies,
                 exotics, market simulation (paths), pnl attribution. Fully tested.
/src/components   UI: greeks lab, strategy builder, exotics, simulator, education panels
/src/data         seed snapshot (JSON from the script) and vol-surface construction
/scripts          fetch_snapshot.py (yfinance, --underlying spx|sx5e)
/docs             design notes and the learning guide (for the human, not instructions)
```

Co-locate tests with the engine code they cover.

---

## Build order

Build **one phase at a time**: implement, write tests, get it working and reviewed, *then* move on. Do not scaffold all four phases at once. Phase 1 is specified in detail below; later phases are summarised and will be expanded when we reach them.

**Phase 1 — Greeks lab (vanillas).** The foundation. Everything else is this engine pointed at harder things.
**Phase 2 — Strategy builder.** Compose vanilla legs into standard structures; show aggregate greeks.
**Phase 3 — Exotics.** Barriers, digitals, autocallables, variance swaps.
**Phase 4 — Trading simulator.** Simulated market, client RFQs, two-way quoting, hedging, live P&L attribution.

---

## Phase 1 — Greeks lab (detailed spec)

**Engine — `bsm.ts`.** Black–Scholes–Merton with continuous dividend yield `q`. Inputs: spot `S`, strike `K`, time-to-expiry `T` (in years), rate `r`, dividend yield `q`, vol `σ`, call/put flag.

```
d1 = (ln(S/K) + (r − q + σ²/2)·T) / (σ·√T)
d2 = d1 − σ·√T
Call = S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2)
Put  = K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1)
```

**Engine — `greeks.ts`.** Implement **all** of the following analytically, each as a documented pure function stating the quantity it computes:
- First order: **delta, vega, theta, rho**.
- Second order / cross: **gamma, vanna** (∂Δ/∂σ = ∂vega/∂S), **volga/vomma** (∂vega/∂σ), **charm** (∂Δ/∂t).
- Third order (optional but include if cheap): **speed, color**.

Reference forms (with `q`; `φ` = standard normal pdf, `N` = cdf):
```
delta_call = e^(−qT)·N(d1)              delta_put = e^(−qT)·(N(d1) − 1)
gamma      = e^(−qT)·φ(d1) / (S·σ·√T)
vega       = S·e^(−qT)·φ(d1)·√T
vanna      = −e^(−qT)·φ(d1)·d2 / σ
volga      = vega · d1·d2 / σ
```
Implement theta, rho, charm, speed, and color from standard BSM as well.

**Unit conventions (state these in code comments and apply consistently):**
- `vega` and `rho` reported **per 1 percentage point** of vol/rate (i.e. divide the raw per-1.0 sensitivity by 100).
- `theta` reported **per calendar day** (divide the raw per-year sensitivity by 365).
- `T` is a year fraction; `r` and `q` are continuously compounded.

**Validation (required).** For every greek, write a unit test that checks the analytical value against a **central finite-difference bump** of the pricer (e.g. relative tolerance ~1e-4), plus a handful of hard-coded reference values for a known parameter set. This catches sign and convention errors and is non-negotiable.

**UI.** An input panel (paired sliders + numeric fields) for `S, K, T, r, q, σ` and a call/put toggle, seeded from the snapshot (spot ≈ index level, σ ≈ vol index / 100, q ≈ snapshot). A live readout of **price and every greek**, updating instantly as inputs change. Plots:
- Selectable **greek vs spot**, **greek vs vol**, and **greek vs time-to-expiry** (user picks which greek).
- **Payoff at expiry** for the option.

**Education panel.** For each greek: what it measures, the sign/size intuition, and when it's large. Plus the key relationships, written plainly: gamma↔theta (locked by the BSM PDE; delta-hedged P&L ≈ ½·Γ·S²·(realised vol² − implied vol²)), gamma↔vega across maturities (short-dated = gamma/realised play, long-dated = vega/implied play), and pin risk near expiry. *(The human has a fuller written guide in `/docs`; surface the intuition in-app in your own concise words.)*

**Acceptance check.** Dragging spot visibly spikes ATM gamma as `T` shrinks; increasing `T` visibly trades gamma down for vega up. If those two behaviours read clearly off the plots, Phase 1 is working.

---

## Phase 2 — Strategy builder (summary)

Compose N legs (side, call/put, strike, expiry, quantity) into a position. Show aggregate **price, payoff, and all greeks**, plus greek profiles vs spot/vol/time for the whole structure. Ship presets common on an index desk: vertical spreads, straddle/strangle, **risk reversal**, **butterfly**, condor, calendar. Education panel explains the *view* each expresses (risk reversal = skew bet; butterfly = vol-of-vol bet; calendar = term-structure bet).

## Phase 3 — Exotics (summary)

Barriers (down/up, in/out — closed-form where it exists, else Monte Carlo), cash-or-nothing **digitals**, an **autocallable** (Monte Carlo, path-dependent), and a **variance swap** (fair variance; ties naturally to the vol index). Greeks analytically or by bumping. Education covers the behaviours that matter: a barrier's gamma exploding near the barrier, a digital being an un-hedgeable tight call-spread at expiry (pin risk), and autocallable path-dependence.

## Phase 4 — Trading simulator (summary)

A simulated index path (GBM → Heston), a clock you tick forward, and randomised **client RFQs** (instrument, notional, side). You show a **two-way bid/ask** (mid ± a spread you choose); fill logic decides win/lose against a simulated fair value plus noise. A **book** aggregates positions and net greeks; you **hedge** by trading the underlying (index future proxy). Each step/EOD produces a **P&L attribution** decomposing the move into delta/gamma/theta/vega/vanna/volga **plus a residual**, via the second-order Taylor expansion. Education ties it to realised-vs-implied vol (gamma scalping, with the vol index as the implied gauge) and how to read a P&L explain.

---

## Conventions & quality bar

- TypeScript **strict** mode. Engine functions are **pure** and documented with the formula they implement.
- Every pricing/greek function has tests (finite-difference cross-check + reference values) before it's considered done.
- 2-space indentation. Prefer clarity over cleverness; this is a codebase meant to be *read and learned from*.
- Be explicit about units, currency, and day-count everywhere a number could be ambiguous.

## Commands

Requires Node.js (≥ 20; built on 24 LTS). On this machine Node lives at
`C:\Program Files\nodejs` — if a shell can't find `node`, prepend that to PATH.
```
npm install                                  install dependencies
npm run dev                                  start the dev server (http://localhost:5173)
npm run build                                type-check (tsc -b) + production build
npm run preview                              serve the production build
npm test                                     run the unit tests (vitest run)
npm run test:watch                           tests in watch mode
npm run typecheck                            type-check only (tsc -b --noEmit)
npm run lint                                 oxlint
python scripts/fetch_snapshot.py --underlying spx --out src/data/snapshot.json
                                             refresh the seed snapshot (needs:
                                             pip install yfinance pandas numpy)
python scripts/fetch_history.py --years 8 --out src/data/history.json
                                             refresh the simulator's historical-replay
                                             data (real ^GSPC + ^VIX daily)
```

Stack: Vite 8 + React 19 + TypeScript (strict), Vitest 4 + jsdom, Recharts 3, oxlint.
Playwright (chromium) is a dev dependency used for visual smoke screenshots
(`npx playwright install chromium` once).

## How to start

Begin in **plan mode**: propose how you'll scaffold the app and build Phase 1, and wait for my approval before large changes. Then scaffold Vite + React + TypeScript, build the `/src/engine` pricing and greeks with their tests, wire in the seed snapshot, and then the Phase 1 UI. We tackle Phases 2–4 only after Phase 1 works and I've reviewed it.
