# EQD Greeks Lab

A browser-based training app that replicates the daily activity of an **equity-derivatives
(EQD) index market-maker**, built for interview prep. It optimises for *realistic activity +
educational depth* over live-data accuracy. Default underlying: **S&P 500 (SPX)**.

> **All four phases are implemented:** Phase 1 — Greeks Lab, Phase 2 — Strategy Builder, Phase 3 —
> Exotics (barriers, digitals, an autocallable, a variance swap), and Phase 4 — Trading Simulator.
> See [`CLAUDE.md`](CLAUDE.md) for the full spec and [`docs/WORKLOG.md`](docs/WORKLOG.md) for the
> build log.
>
> 📘 **New to options market-making?** Read **[`docs/TRADING_GUIDE.md`](docs/TRADING_GUIDE.md)** — a
> full "how to trade well" tutorial (foundations, the greeks, volatility, structures, market-making,
> hedging, P&L attribution, discipline) tied feature-by-feature to this app.

## What it does

Drag the inputs and watch the price and **every greek** update instantly:

- **Pricing & greeks from scratch.** Black–Scholes–Merton with continuous dividend yield `q`,
  plus delta, gamma, vega, theta, rho, vanna, volga, charm, speed and color — each an analytic
  pure function, **validated against finite differences** (this is the educational core; no
  black-box options library is used).
- **Live plots.** The selected greek vs spot / vol / time, and the payoff diagram.
- **Education panel.** Plain-language, desk-flavoured notes on each greek plus the key
  relationships (gamma↔theta via the BSM PDE, gamma vs vega across maturities, pin risk, and why
  the surface must move with spot).

The acceptance behaviour to look for: shrink **T** and the ATM **gamma** spikes into a tall,
narrow peak; lengthen **T** and gamma trades down while **vega** rises.

**Strategy Builder** (second tab) composes vanilla legs into a position — verticals, straddle/
strangle, risk reversal, butterfly, iron condor and calendar presets, or hand-edited legs. It shows
the net premium (debit/credit), aggregate greeks, the **P&L payoff diagram** (at the front expiry,
so calendars render their tent) and net greek profiles, plus the desk *view* each structure
expresses (risk reversal = skew bet, butterfly = vol-of-vol, calendar = term structure). Each leg's
vol is seeded skew-aware from the surface.

**Exotics** (third tab) covers four instruments, each with its characteristic plot: **barriers**
(Reiner–Rubinstein closed forms — watch gamma explode at the barrier), **digitals** (cash-or-nothing
vs its replicating call spread — the pin-risk step), an **autocallable** (Phoenix, Monte-Carlo, with
sample paths + early-redemption diagnostics) and a **variance swap** (fair variance via the 1/K²
option strip — the VIX-style convexity premium over ATM). Every closed form is cross-validated
against Monte Carlo / parity / analytic limits.

**Trading Simulator** (fourth tab) is the capstone market-making loop on a **skewed surface that
moves with spot**. Two market modes: a **simulated** GBM path (with the leverage effect) or
**historical replay** of a random *undisclosed* slice of real ^GSPC/^VIX history. A **queue** of
client **RFQs** — singles *and* structures (straddle / strangle / risk reversal / verticals) — that
**arrive automatically on Auto**; you quote a two-way (spread + a *lean* to skew your price), win or
lose, and are left with risk. Then you **hedge actively**: flatten delta in the future, or vega /
gamma / any option via the market (a **trade ticket**, crossing a real cost). A **desk scorecard**
(P&L, edge, costs, fill rate, risk flags) and a live **P&L explain** — the second-order Taylor
decomposition into delta / gamma / theta / vega / vanna / volga + residual — tie it to realised-vs-
implied vol (gamma scalping). Refresh the replay data with `python scripts/fetch_history.py`.

## Architecture

```
src/engine      pure TS: mathUtils (West-2009 normal CDF), bsm pricing, all greeks,
                reporting (unit conventions), index. Zero UI deps, fully unit-tested.
src/data        committed seed snapshot (JSON) + typed loader, vol surface, underlying config.
src/components   React UI: InputPanel, GreeksReadout, PlotsPanel, EducationPanel + content.
scripts         fetch_snapshot.py (yfinance) — refreshes the seed, OUT of the reactive loop.
docs            WORKLOG.md
```

Design rule: **data → engine inputs, never engine → data.** The engine returns *raw*
mathematical partials; a single `reporting.ts` layer applies desk units (vega/rho per 1 pt,
theta/charm/color per day).

## Quick start

```
npm install
npm run dev        # http://localhost:5173
npm test           # unit tests (engine FD checks, parity, edge cases, UI smoke)
npm run build      # type-check + production build
```

The app loads a committed static SPX snapshot (mid-2026 placeholder values). To refresh from
Yahoo Finance: `python scripts/fetch_snapshot.py --underlying spx --out src/data/snapshot.json`
(needs `pip install yfinance pandas numpy`).
