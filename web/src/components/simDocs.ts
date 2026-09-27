/**
 * Education content for the Phase 4 trading simulator: the market-making loop,
 * the spread/fill tradeoff, gamma scalping (realised vs implied), and how to read
 * a P&L explain. Plus per-term notes for the attribution panel.
 */

export interface SimConcept {
  title: string
  body: string
}

export const SIM_CONCEPTS: SimConcept[] = [
  {
    title: 'The market-making loop',
    body: 'A client asks for a price; you quote a two-way (bid/ask around fair); you win or lose the trade; you are left with risk; you hedge it; and at end-of-day you attribute your P&L. Every tick of this simulator is one turn of that loop — your job is to be paid for the risk you warehouse.',
  },
  {
    title: 'Spread vs fill — the edge tradeoff',
    body: 'A wider spread earns more edge per trade but wins less flow; a tighter spread wins more trades but is paid less for the risk. The skill is pricing tight enough to capture flow yet wide enough to be compensated — and skewing your quote when you already have a position you want to reduce.',
  },
  {
    title: 'Gamma scalping — realised vs implied',
    body: 'Once you hold an option and delta-hedge, your P&L per unit time is ≈ ½·Γ·S²·(σ_realised² − σ_implied²). Long gamma makes money when the market moves MORE than the vol you paid (realised > implied) and bleeds theta when it is calmer; short gamma is the reverse. The vol index (VIX/VSTOXX) is the implied gauge you are betting against.',
  },
  {
    title: 'The leverage effect bites twice',
    body: 'Spot down → vol up. So a sell-off hits a short-gamma / short-vega book twice: a gamma loss on the move AND a vega loss as implied vol spikes. The vanna term in your P&L explain is exactly this spot-vol interaction — it is why equity skew is not cosmetic.',
  },
  {
    title: 'Reading a P&L explain',
    body: 'Decompose each step into delta (spot × your net delta), gamma (convexity, ½Γ·ΔS²), theta (decay), vega (implied-vol move), vanna (spot-vol cross), volga (vol convexity) and a residual. A small residual means the second-order Taylor explains your day — you understand your risk. A large residual flags a gap, a big move, or risk you are not measuring.',
  },
]

export interface AttributionTerm {
  key: 'delta' | 'gamma' | 'theta' | 'vega' | 'vanna' | 'volga' | 'residual'
  label: string
  note: string
}

export const ATTRIBUTION_TERMS: AttributionTerm[] = [
  { key: 'delta', label: 'Delta', note: 'Spot moved × your net delta (options + hedge). Hedge it to isolate vol/gamma.' },
  { key: 'gamma', label: 'Gamma', note: 'Convexity: ½·Γ·ΔS². Long gamma loves big moves; short gamma fears them.' },
  { key: 'theta', label: 'Theta', note: 'Time decay — the rent you pay (long) or collect (short) for gamma.' },
  { key: 'vega', label: 'Vega', note: 'Implied vol moved × your vega — the level of the surface.' },
  { key: 'vanna', label: 'Vanna', note: 'Spot–vol cross (ΔS×Δσ). Bites with skew / the leverage effect.' },
  { key: 'volga', label: 'Volga', note: 'Vol convexity (½·volga·Δσ²) — the value of the wings.' },
  { key: 'residual', label: 'Residual', note: 'What 2nd-order Taylor missed: 3rd-order, big gaps, vol-path. Large ⇒ look closer.' },
]
