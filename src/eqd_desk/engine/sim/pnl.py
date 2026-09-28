"""P&L attribution ("explain") for the book over one market step.

Via the second-order Taylor expansion of the book value in (S, σ, t)::

    ΔV ≈ Δ·ΔS + ½·Γ·ΔS² + Θ·Δt + vega·Δσ + vanna·ΔS·Δσ + ½·volga·Δσ² + residual

Uses RAW greeks (exact partials) at the START of the step; the residual is the actual
repriced ΔV minus the explained terms, so the decomposition reconciles exactly. The
residual collects third-and-higher order and any vol-path effects: small for small steps,
larger across a gap. The underlying hedge sits in the delta term (it folds into the book's
net delta).

Units: every term is in premium currency (e.g. USD for SPX), for the whole book. Δt is in
YEARS (raw theta is per year), Δσ in decimal vol (raw vega is per 1.00 of vol).
"""

from __future__ import annotations

from dataclasses import dataclass

from eqd_desk.engine.greeks import raw_greeks
from eqd_desk.engine.sim.book import MIN_REMAINING_T, Book, book_value
from eqd_desk.engine.sim.market import MarketState, vol_for_strike
from eqd_desk.engine.types import BsmInputs


@dataclass(frozen=True, slots=True)
class PnlAttribution:
    """One step's P&L explain. ``delta + gamma + theta + vega + vanna + volga + residual``
    equals ``total`` (up to float rounding)."""

    total: float
    """Actual mark-to-market change of the (unchanged) book over the step."""
    delta: float
    """Δ·ΔS (options + the underlying hedge)."""
    gamma: float
    """½·Γ·ΔS²."""
    theta: float
    """Θ·Δt (time decay)."""
    vega: float
    """vega·Δσ, with each leg's Δσ read off the moving surface."""
    vanna: float
    """vanna·ΔS·Δσ (the spot-vol cross term)."""
    volga: float
    """½·volga·Δσ²."""
    residual: float
    """Actual − explained: third-order and beyond (incl. surface dynamics)."""


def attribute(book: Book, before: MarketState, after: MarketState) -> PnlAttribution:
    """Per-leg P&L attribution of an unchanged ``book`` from ``before`` to ``after``.

    Each leg's vol change Δσ comes from the surface (:func:`vol_for_strike`), so when spot
    moves both the ATM level AND the leg's moneyness shift: the skew/leverage P&L lands in
    vega/vanna/volga rather than the residual. Spot greeks (delta/gamma) and theta sum
    across legs; the underlying hedge contributes only to delta.

    For a trade with signed quantity k, remaining maturities T_b / T_a (floored at 1e-6
    years) and surface vols σ_b / σ_a, with greeks g taken at ``before``::

        delta += k·g.Δ·ΔS           gamma += ½·k·g.Γ·ΔS²       theta += k·g.Θ·Δt
        vega  += k·g.vega·Δσ        vanna += k·g.vanna·ΔS·Δσ   volga += ½·k·g.volga·Δσ²
    """
    dS = after.spot - before.spot
    dt = after.t - before.t

    delta = 0.0
    gamma = 0.0
    theta = 0.0
    vega = 0.0
    vanna = 0.0
    volga = 0.0

    for tr in book.trades:
        k = (1 if tr.side == "long" else -1) * tr.quantity
        T_b = max(tr.expiry_time - before.t, MIN_REMAINING_T)
        T_a = max(tr.expiry_time - after.t, MIN_REMAINING_T)
        sig_b = vol_for_strike(before, tr.K, T_b)
        sig_a = vol_for_strike(after, tr.K, T_a)
        d_sig = sig_a - sig_b
        g = raw_greeks(
            BsmInputs(S=before.spot, K=tr.K, T=T_b, r=before.r, q=before.q, sigma=sig_b),
            tr.type,
        )
        delta += k * g.delta * dS
        gamma += 0.5 * k * g.gamma * dS * dS
        theta += k * g.theta * dt
        vega += k * g.vega * d_sig
        vanna += k * g.vanna * dS * d_sig
        volga += 0.5 * k * g.volga * d_sig * d_sig
    # underlying hedge: pure delta.
    delta += book.underlying_qty * dS

    total = book_value(book, after) - book_value(book, before)
    explained = delta + gamma + theta + vega + vanna + volga
    return PnlAttribution(
        total=total,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        vanna=vanna,
        volga=volga,
        residual=total - explained,
    )


__all__ = ["PnlAttribution", "attribute"]
