# WORKLOG — EQD Greeks Lab

A living record of decisions, build steps, and verification status. Newest entries at the
bottom of each section. The approved plan lives at
`C:\Users\berna\.claude\plans\keen-wandering-pike.md`.

---

## Status board

| Phase | Item | State |
|-------|------|-------|
| 1 | Scaffold (Vite + React + TS strict, Vitest, Recharts) | ✅ done |
| 1 | Engine: types, mathUtils, bsm | ✅ done |
| 1 | Engine: greeks, reporting, index | ✅ done |
| 1 | Engine tests (FD harness + references + parity + edges) | ✅ 121/121 green |
| 1 | Adversarial math verification | ✅ all-correct (3 agents, 0 discrepancies) |
| 1 | Data layer (snapshot.json, snapshot.ts, volSurface.ts, config.ts) | ✅ done |
| 1 | UI (terminal shell, InputPanel, GreeksReadout, PlotsPanel, EducationPanel) | ✅ done |
| 1 | Finalize (acceptance, CLAUDE.md commands, full test/build) | ✅ done |
| 2 | Engine: strategy.ts (aggregate) + presets.ts | ✅ done |
| 2 | Engine tests + adversarial review (presets/payoff) | ✅ done · 0 issues |
| 2 | UI: Lab/Builder tabs, legs editor, position readout, payoff + greek plots, education | ✅ done |
| 2 | Finalize Phase 2 (full test/build, visual verify) | ✅ done |

**Phase 1 complete.** 133 tests green · `tsc -b` clean · production build OK · UI verified by
Playwright screenshot (acceptance behaviour confirmed). Reviewed and approved.

**Phase 2 (Strategy Builder) complete.** 148 tests green · build OK · all 8 presets + custom legs
verified by screenshot (butterfly debit / iron-condor credit / calendar tent payoffs render
correctly). Reviewed and approved.

| 3 | Engine exotics: digital, barrier, MC+autocall, varswap (+ numericGreeks) | ✅ done |
| 3 | Exotics tests (parity, MC cross-checks, deterministic cross-check, σ² recovery) | ✅ done |
| 3 | Adversarial review of exotic math (Haug barrier table, etc.) | ✅ done · 0 issues |
| 3 | UI: Exotics tab + 4 views (barrier/digital/autocall/varswap) | ✅ done |
| 3 | Finalize Phase 3 (full test/build, visual verify) | ✅ done |

**Phase 3 (Exotics) complete.** 182 tests green · build OK · all 4 exotic views verified by
screenshot (barrier gamma explosion, digital vs call-spread, autocall sample paths, varswap
replication strip + skew premium). Reviewed and approved.

| 4 | Engine sim: market/rfq/quote/book/pnl | ✅ done |
| 4 | Sim tests (attribution reconciles, leverage, fill, accounting) | ✅ done |
| 4 | Adversarial review of sim accounting + P&L explain | ✅ done · 0 issues |
| 4 | UI: Simulator tab (market/clock, RFQ+quote, book, hedge, P&L explain) | ✅ done |
| 4 | Finalize Phase 4 (full test/build, visual verify) | ✅ done |

**Phase 4 (Trading Simulator) complete — ALL FOUR PHASES DONE.** 197 tests green · build OK · the
full market-making loop verified by screenshot (RFQ → quote → fill → book/greeks → hedge → tick →
P&L explain). The P&L attribution bar chart decomposes P&L into delta/gamma/theta/vega/vanna/volga
+ residual; spot/vol path shows the leverage effect.

---

## Key decisions

- **Toolchain installed:** Node.js 24.18.0 LTS + npm 11.16.0 via winget (machine had no Node).
  Node lives at `C:\Program Files\nodejs`; shells must prepend it to PATH until a full re-login.
- **Versions (resolved by npm against Vite 8):** vite ^8.1.0, react ^19.2.7, typescript ~6.0.2,
  vitest ^4.1.9, recharts ^3.9.0, jsdom ^29, @testing-library/react ^16.3. Linter is **oxlint**
  (shipped by the new Vite template) rather than eslint.
- **TS strict** enabled in `tsconfig.app.json` (the Vite 8 template omitted it).
- **Vitest** configured in `vite.config.ts`: globals on, `jsdom` environment (so one runner covers
  both pure-engine and React tests), setup file adds jest-dom matchers.
- **Engine architecture:** unit-pure raw-greek core + a thin `reporting.ts` layer that owns all
  display-unit scaling. Dependency rule: data → engine inputs, never engine → data.
- **Normal CDF:** West (2009) cumulative-normal (Hart coefficients) — machine precision in the
  wings. `normCdf(-d)` always called directly (never `1 - normCdf(d)`).
- **Reference-value policy:** trust textbook numbers (price, delta, gamma, vega, theta, rho) but
  treat higher-order greek reference numbers as *guilty until FD-validated* — the finite-difference
  cross-check is the source of truth; regression snapshots are taken from the FD-validated engine.

## Reporting-unit conventions (single source of truth = `reporting.ts`)

| Greek | Raw unit | Reported unit | Scale |
|-------|----------|---------------|-------|
| price | currency | currency | ×1 |
| delta | ∂V/∂S | per $1 spot | ×1 |
| gamma | ∂²V/∂S² | per $1 spot | ×1 |
| vega  | ∂V/∂σ (per 1.00 vol) | per 1 vol pt | ÷100 |
| theta | ∂V/∂t (per year) | per calendar day | ÷365 |
| rho   | ∂V/∂r (per 1.00 rate) | per 1 rate pt (1%) | ÷100 |
| vanna | ∂Δ/∂σ | Δdelta per 1 vol pt | ÷100 |
| volga | ∂vega/∂σ | Δ(vol-pt vega) per 1 vol pt | ÷10000 |
| charm | ∂Δ/∂t (per year) | delta decay per day | ÷365 |
| speed | ∂Γ/∂S | per $1 spot | ×1 |
| color | ∂Γ/∂t (per year) | gamma decay per day | ÷365 |

Sign convention for time greeks: `∂/∂t = −∂/∂T` (a long option bleeds **negative** theta).

---

## Build log

- **2026-06-24** — Installed Node LTS (winget). Scaffolded Vite React-TS into the existing repo
  (temp subdir → relocated). Enabled TS strict, wired Vitest, created folder structure
  (`src/engine`, `src/components`, `src/data`, `scripts`, `docs`), moved `fetch_snapshot.py` →
  `scripts/`. Toolchain smoke test passed (vitest 4.1.9). Starting the engine.
- **2026-06-24** — Built the engine: `types.ts`, `mathUtils.ts` (West 2009 normCdf + normPdf),
  `bsm.ts` (d1/d2, call/put price, validation, T/σ floors), `greeks.ts` (delta, gamma, vega,
  theta, rho, vanna, volga, charm, speed, color), `reporting.ts`, `index.ts`. Wrote the FD
  harness + `mathUtils.test.ts`, `bsm.test.ts`, `greeks.test.ts`.
  - **Bug the FD harness caught:** `charm` had a flipped sign (the initial closed form computed
    +∂Δ/∂T instead of charm = −∂Δ/∂T). Corrected to `charm_call = q·dfQ·N(d1) − common`,
    `charm_put = −q·dfQ·N(−d1) − common`. Re-validated by FD.
  - Two test calibrations (not engine bugs): the q≠0 FD set was nudged off the exact `d2=0`
    point (where analytic vomma is exactly 0 but the 2nd-difference shows truncation noise) and
    an explicit "vomma vanishes at d2=0" test was added; the deep-tail normCdf test now checks
    relative error (West's CF tail is ~1e-8 relative at z=8, ~5e-11 at z=5 — ample for pricing).
  - **Result: 121/121 tests green; `tsc -b` clean under strict.** Running independent adversarial
    re-derivation of every greek as a second check.
- **2026-06-24** — Adversarial verification workflow (3 parallel agents, independent first-
  principles re-derivation + Python finite-difference cross-checks). **Verdict: all-correct, zero
  discrepancies.** Price/delta/vega/theta/rho confirmed; gamma/vanna/volga/charm/speed/color
  confirmed (incl. the charm sign fix); West/Hart normCdf coefficients matched exactly; T/σ floors
  confirmed non-distorting for realistic inputs; all reporting unit-scalings dimensionally
  confirmed. One non-bug note acted on: corrected the mathUtils normCdf doc comment, which had
  overstated far-tail accuracy (it's ~1e-14 central, ~1e-8 at |x|≈8 — still far beyond pricing
  needs). Engine considered DONE.
- **2026-06-24** — Built the data layer: `config.ts` (SPX/SX5E presets), committed static
  `snapshot.json` (mid-2026 SPX placeholders), `snapshot.ts` (typed loader + validation +
  `seedInputs`), `volSurface.ts` (flat-but-skewed `getVol(K,T)` interface for forward-compat),
  plus `data.test.ts`. All green.
- **2026-06-24** — Built the UI (terminal aesthetic, dark, monospace numerics): `format.ts`,
  `education.ts` (desk-grade per-greek content + key relationships), `InputPanel`,
  `GreeksReadout`, `PlotsPanel` (Recharts: greek-vs-spot/vol/time + payoff), `EducationPanel`,
  the `App` shell, and the `index.css`/`App.css` theme. Removed Vite template cruft; added a
  custom favicon. Added a React render smoke test (jsdom + ResizeObserver polyfill).
- **2026-06-24** — Verified end-to-end. **133/133 tests green**, `tsc -b` clean, production build
  OK (576 kB bundle, Recharts-dominated). Installed Playwright/Chromium and screenshotted the
  running app: the **acceptance check holds visually** — ATM gamma spikes into a tall narrow peak
  as T→7d (Γ 0.0015→0.0030) and the gamma-vs-time curve explodes as T→0; vega falls and theta
  steepens short-dated. Phase 1 done; awaiting review before Phase 2.

## Phase 2 — Strategy Builder

- **2026-06-24** — Engine: `strategy.ts` (Leg/MarketParams/PositionAnalysis; aggregate price+greeks
  = Σ signed-qty·leg; `payoffProfile` evaluated at the FRONT expiry so calendars render correctly;
  `nowPnl` mark-to-market) and `presets.ts` (8 desk structures built from spot via a `volFor(K,T)`
  callback, so the engine stays data-free and each leg is skew-seeded). 14 strategy tests:
  aggregate=Σ, FD-validated net greeks (delta/gamma/vega/theta/rho on butterfly/RR/calendar),
  payoff bounds (vertical max-loss=debit, straddle, butterfly peak, calendar finite), preset
  structure checks, and a **skew-bet test** (put-skew makes the long-call/short-put RR cheaper).
  All green first run.
- **2026-06-24** — Adversarial review (1 agent, independent of the FD tests) of aggregation,
  payoff/calendar convention, and all 8 preset definitions vs desk conventions: **all correct, no
  edits**. Confirmed front-expiry payoff is the right calendar convention and reduces to intrinsic
  for single-expiry structures.
- **2026-06-24** — UI: top-level **Lab / Builder tabs** (extracted Phase 1 into `GreeksLab.tsx`).
  New components: `StrategyControls` (preset grid + market + build params), `LegsEditor`
  (inline-editable legs in trader units), `PositionReadout` (net premium debit/credit + aggregate
  greeks), `StrategyPlots` (P&L payoff at expiry + now, and net greek vs spot / vol-shift / elapsed-
  time), `StrategyEducation` (per-structure desk rationale + reused greek docs), `strategyDocs.ts`.
  Made `EducationPanel` embeddable. Fixed a Windows case-collision (renamed `strategyEducation.ts`
  → `strategyDocs.ts`). Added a builder smoke test.
- **2026-06-24** — Verified: **148/148 tests green**, `tsc -b` clean, build OK (597 kB). Restarted
  the stale dev server (HMR cache held the pre-rename case-collision) and screenshotted: butterfly
  (−146 debit, tent), iron condor (+22 credit, trapezoid), calendar (−98 debit, tent at front
  expiry). Phase 2 done; awaiting review before Phase 3 (exotics).

## Phase 3 — Exotics

- **2026-06-24** — Engine (`src/engine/exotics/`): `numericGreeks.ts` (shared bump-greeks in desk
  units, with common-random-numbers support for MC), `digital.ts` (cash/asset-or-nothing +
  call-spread replication), `barrier.ts` (Reiner–Rubinstein A/B/C/D, all 8 KO/KI×C/P with K≷H
  branches, breach guards, greeks by bump), `mc.ts` (mulberry32 + Marsaglia-polar normals + GBM),
  `autocall.ts` (Phoenix autocallable MC: memory coupon, early redemption, downside barrier,
  diagnostics + CRN greeks), `varswap.ts` (fair variance via 1/K² OTM strip split at the forward).
- **Tests (51 across 4 files):** digital = call-spread limit + identities + FD delta; barrier
  **KI+KO=vanilla parity (all 8)** + **MC cross-check of all 4 knock-out types** (both K≷H branches,
  with BGK continuity correction) + vanilla limits; autocall reproducibility + diagnostics +
  monotonicity + **deterministic digital-replication cross-check**; varswap **flat-vol = σ²** +
  skew premium. One test-side fix: the BGK continuity correction was applied in the wrong direction
  (down-barrier must shift UP) — not an engine bug.
- **Adversarial review** (1 agent, independent of the tests): the full Haug barrier table (all 16
  branch arms), digital, varswap (`e^{rT}` factor with q only in the forward), autocall loop, and
  the RNG — **all correct, no edits**.
- **UI:** third **Exotics** tab with a sub-selector → 4 self-contained views: `BarrierView` (greek
  vs spot with H/K marked — gamma explosion), `DigitalView` (digital vs replicating call spread),
  `AutocallView` (sample GBM paths + barriers, MC diagnostics), `VarSwapView` (1/K² strip + smile +
  convexity premium). Shared `Controls`, `chartTheme`, `ExoticInfo`, `exoticsDocs`.
- **Verified: 182/182 tests green**, `tsc -b` clean, build OK (642 kB). Screenshots confirm all
  four views (barrier gamma spike at H; digital step vs call spread; autocall paths crossing the
  autocall/protection lines; varswap fair vol 17.2% vs ATM 14.6%, +2.6% convexity premium). Phase 3
  done; awaiting review before Phase 4 (trading simulator).

## Phase 4 — Trading Simulator

- **2026-06-24** — Engine (`src/engine/sim/`): `market.ts` (GBM spot with the ATM vol moving
  AGAINST spot — the leverage effect — plus mean-reversion + vol-of-vol; a pluggable
  `MarketProcess` so Heston can drop in; a seeded `MarketSimulator`), `rfq.ts` (randomised client
  requests), `quote.ts` (two-way fill logic vs fair + noise — wider spread = more edge, fewer
  fills), `book.ts` (cash + positions + underlying-hedge accounting; net greeks via the Phase-2
  aggregation; `hedgeToFlat`), `pnl.ts` (second-order Taylor P&L explain using RAW greeks).
- **Tests (14):** market reproducibility + leverage sign (FD) + vol floor/cap + realised vol;
  RFQ validity/reproducibility; fill direction/edge + spread↔fill-prob; book value=edge,
  hedge-to-flat value-neutral; **attribution reconciles exactly** + residual tiny for small moves +
  vega/theta isolation + long-gamma delta-hedged ≈ ½ΓΔS². Two test-side fixes (quote around real
  BSM fair; `−0` vs `+0`), no engine bugs.
- **Adversarial review** (1 agent): accounting, attribution units (RAW greeks, Δσ decimal, Δt
  years — the classic "reported-greeks-in-the-explain" bug avoided), fill logic, leverage — **all
  correct, no edits**. Added a one-line invariant comment to `addFill` per its suggestion.
- **UI:** fourth **Simulator** tab (`SimulatorView`): Market panel (spot/implied/realised vol,
  clock, Tick / Auto-play / Reset), Client-RFQ + spread → bid/ask + Quote/Pass + win/lose, P&L
  hero + P&L-over-time line, **P&L-explain bar chart** (cumulative delta/gamma/theta/vega/vanna/
  volga/residual), spot+vol path (leverage visible), Book greeks + positions blotter + Hedge→flat,
  and a market-making education panel (`simDocs`). RNG streams live in refs for reproducibility.
- **Verified: 197 tests green** (incl. simulator smoke test), `tsc -b` clean, build OK (679 kB).
  Screenshot of a 6-trade, 25-day session: +1,800 P&L (2,990 edge captured), attribution bars sum
  to P&L, vol spikes inversely to spot. **Project complete — all four phases done.**

## Phase 4+ — Active-hedging desk & realism layer (post-review enhancement)

- **2026-06-24** — Per the user's request to make the simulator more realistic & hands-on:
  - **Skew surface** (`market.ts` `volForStrike`): MarketState gains optional `skewSlope/skewCurv`;
    options price on a quadratic log-moneyness skew anchored to the (leverage-moving) ATM level, so
    the whole surface shifts with spot and vanna is real. Flat when absent (older tests untouched).
  - **Per-leg P&L attribution** (`pnl.ts`): each leg's Δσ comes from the surface, so skew/leverage
    P&L lands in vega/vanna/volga instead of the residual — the explain stays tight even with skew.
  - **Transaction costs + market trades** (`book.ts`): `CostModel`, `totalCosts`; `hedgeTrade`/
    `hedgeToFlat` now cross the underlying spread; `tradeOption` (you pay the option spread, no
    edge), `flattenVega`/`flattenGamma` (trade an ATM option to zero a greek). `quote.ts` gains a
    `lean` to skew your two-way.
  - **UI** (`SimulatorView`): skew-aware market + skew readout, a **desk scorecard** (P&L, edge,
    costs, fill rate, net-Δ/vega risk flags), a **lean** slider on quotes, **Flatten Δ/vega/Γ**
    buttons, and a **Trade Ticket** to buy/sell any option or the future at market (showing the
    cost). 6 new engine tests.
  - **Verified: 203 tests green**, `tsc -b` clean, build OK (682 kB). Screenshot: active session
    with skew (slope −0.48, non-zero vanna P&L, small residual), costs tracked, trade-ticket + a
    flatten-vega hedge in the blotter, 86% fill rate.

## Phase 4++ — Historical replay, structure/multi RFQs, auto-flow (post-review)

- **2026-06-25** — Per the user's request:
  - **Historical replay**: `scripts/fetch_history.py` pulls real daily ^GSPC + ^VIX (yfinance) →
    committed `src/data/history.json` (**2010 days, Jun-2018 … Jun-2026** — incl. the COVID crash &
    2022 bear). `sim/replay.ts` (pure) picks a random undisclosed window and maps each point to a
    MarketState (VIX/100 = ATM implied). A **Simulated / Replay** mode toggle drives the market off
    GBM or the real path.
  - **Structure & multiple RFQs**: RFQ generalised to `legs` (single + straddle/strangle/risk-
    reversal/verticals, reusing the Phase-2 preset builder). `rfqFair` returns net + gross;
    `quote.ts` quotes the NET fair with spread/lean sized off GROSS (so credit structures work);
    `addFill` books all legs. A **queue** (up to 4) of live RFQs; quote the selected one as a net
    two-way.
  - **Auto-flow**: Auto now advances the clock AND brings RFQs in randomly (with expiry), so the
    desk feels live. Reset reseeds (non-repeating sim paths; new replay window).
  - 9 new engine tests (structures, multi-leg fill, replay stepping) + a replay-mode UI smoke test.
  - **Verified: 207 tests green**, `tsc -b` clean, build OK (775 kB incl. bundled history).
    Screenshots: Auto-flow queue with a Straddle/Put/Strangle auto-arrived; Replay mode at day 9/60,
    real spot 6,796 / VIX 18%, a 25× Risk-reversal RFQ in the queue. No console errors.
- **2026-06-25** — Tweaks: replay window now defaults to **120 days** and is adjustable via a
  **Replay length** slider (30–504d, applies on reset); added an **Auto speed** slider (120–3000
  ms/day) so the day-to-day delay in Auto is configurable. Also fixed the Positions blotter to list
  the underlying **FUTURE** hedge (it was only shown as the net-delta row before). 207 tests green.
- **2026-06-25** — Trade ticket now trades **structures**, not just single options: an
  Option / Structure / Future selector; in Structure mode a preset grid (the 8 Phase-2 structures),
  Buy/Sell the package, wing %, tenor and size, with a live net/cost readout. `tradeStructure`
  (book.ts) books every leg at market crossing the cost. +1 engine test. **208 tests green**, build
  OK. Verified: sold a risk reversal + bought an iron condor → 6 legs booked, costs tracked.
- **2026-06-25** — Simulator **session now persists across tab navigation**: it stays mounted
  (hidden via `.sim-host`) when another view is active, so book / P&L / market / queue / ticket all
  survive a round-trip to e.g. the Strategy Builder; it auto-pauses (`active` prop) when you leave.
  getByRole excludes hidden elements so no test collisions. Verified by screenshot: P&L −2,106.69
  and the 2-leg straddle identical before/after navigating away and back (charts re-render cleanly).
- **2026-06-25** — **Desk Advisor** (`sim/advisor.ts`, pure + tested): a 💡 button opens a modal
  that reads the live book + market and returns **ranked, explained hedging advice** with one-click
  actions — directional Δ (flatten in the future), vol/vega (contextualised by the vol regime +
  leverage), gamma reconciled with realised-vs-implied (the ½ΓS²(σr²−σi²) scalping P&L), theta, and
  an over-hedging-cost check; severity-sorted (high→ok). Chose a deterministic rule engine over an
  LLM (offline, free, exact on the actual greeks, testable). +4 engine tests. **212 tests green**,
  build OK. Verified: short straddle + short future → high vega + Δ + short-gamma cards with Flatten
  buttons. (A real Claude-API chatbox remains a possible add-on — needs an API key / small backend.)
- **2026-06-25** — Advisor now gives a concrete **HedgePlan** per advice (`advisor.ts`): the exact
  instrument, side and **quantity** (e.g. "BUY 19 × Call 6250 · 60d"), with the rationale (future =
  pure delta; ATM = vega-dense; short-dated ATM = gamma-dense) and the side-effects it brings.
  Quantity = net greek ÷ the hedge option's per-lot greek (raw). Each card has **Load into ticket →**
  which prefills the trade ticket (type/strike/expiry/side/size) and closes the modal, so you review
  the size and execute the *real* hedge yourself rather than auto-flattening. +1 test. **213 green**,
  build OK. Verified by screenshot: plans rendered, and loading the vega plan prefilled the ticket
  to Buy 19 Call 6250 60d.
- **2026-06-25** — **Axe / hedge-via-flow** (the cheapest hedge is offsetting client flow):
  `rfqRiskImpact(rfq, book, market)` computes the greeks you'd pick up by winning an RFQ and judges
  whether it **cuts** or **adds** your dominant risk. UI tags each queued RFQ **↓ (helps) / ↑ (hurts)**
  and shows a lean-guidance banner on the selected one ("cuts your short vega — lean in to win it and
  get PAID to hedge" vs "adds … quote wide or pass"). The Desk Advisor gained an **"axe your quotes
  to the flow you want"** card explaining the negative-cost hedge and which flow to lean into. +1
  test. **214 tests green**, build OK. Verified: short-straddle book → a client-sold straddle tagged
  ↓ green, client-bought puts tagged ↑ red, plus the axe advice.
- **2026-06-25** — **Combined hedge** (greeks interact — don't hedge one at a time). User noticed
  that hedging one greek with options moves the others (normal: an option carries delta+gamma+vega,
  only the future is a clean single-greek tool). New engine fn `jointHedge(book, market, strikeStep)`
  solves the 2×2 system for the quantities of a **short-dated ATM** (gamma-rich) and a **long-dated
  ATM** (vega-rich) that zero gamma AND vega *simultaneously*, then sizes a **future** for the
  residual delta (goes last). The advisor modal gained a "⚖︎ Hedge the book together" block — three
  legs tagged gamma/vega/Δ-last, the rationale, and an **Execute combined hedge** button (books the
  options, then `hedgeToFlat` for exact delta). Shown when both vega & gamma are exposed. +1 test
  (`combined hedge flattens delta, gamma and vega together` — applies the legs, asserts all three
  net greeks ≈ 0). **215 tests green**, build OK. Verified by screenshot on a short-straddle book.
