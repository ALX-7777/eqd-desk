"""What the exotics page SHOWS besides its charts: each view's readout rows (the table under
the hero number) and the notes and captions around its charts.

Pure (no Streamlit): the views (:mod:`eqd_desk.app.ui.exotics_views`) render these with
:func:`~eqd_desk.app.ui.widgets.readout_table` and ``st.caption`` / ``st.info``. The numbers
come from :mod:`eqd_desk.app.ui.exotics_curves`, the teaching text from
:mod:`eqd_desk.content.exotics`; numbers are formatted by :mod:`eqd_desk.app.ui.format`, so
they print as in the React views.

Every decomposition here reads down its rows: each row is one term of the heading above it,
shown with its sign, so the rows add up to the ``Sum`` row (knock-out + knock-in = vanilla;
K × digital ± vanilla = asset-or-nothing).
"""

from __future__ import annotations

from typing import Final

from eqd_desk.app.ui.exotics_curves import (
    AUTOCALL_READOUT_KEYS,
    BARRIER_KIND_LABELS,
    PRICED_READOUT_KEYS,
    AssetDecomposition,
    AutocallData,
    BarrierData,
    DigitalPayout,
    VarSwapControls,
    VarSwapData,
    barrier_sides,
    barrier_status,
    replication_recipe,
)
from eqd_desk.app.ui.format import (
    MINUS,
    fmt_level,
    fmt_money,
    fmt_num,
    fmt_pct,
    fmt_signed,
    fmt_signed_pct,
)
from eqd_desk.app.ui.readout import NBSP, ReadoutRow, greek_rows, group_row
from eqd_desk.content import ExoticMetric
from eqd_desk.content.exotics import (
    AUTOCALL_DIAGNOSTICS,
    BARRIER_BREACHED_NOTES,
    BARRIER_STRIKE_BEYOND_NOTES,
    DIGITAL_ASSET_PRICE_CAPTIONS,
    DIGITAL_GREEK_CAPTION,
    DIGITAL_PRICE_CAPTION,
    VARSWAP_READOUT,
)
from eqd_desk.engine import OptionType
from eqd_desk.engine.exotics import BarrierInputs, DigitalInputs

PARITY_HEADING: Final = "Knock‑in + knock‑out = vanilla"
"""Readout heading of the barrier's in/out rows (non-breaking hyphens keep it on one line)."""
ASSET_CALL_HEADING: Final = "Asset = K × digital + vanilla"
"""Readout heading of an asset-or-nothing call's decomposition rows."""
ASSET_PUT_HEADING: Final = "Asset = K × digital − vanilla"
"""Readout heading of an asset-or-nothing put's decomposition rows."""
K_DIGITALS_LABEL: Final = f"K{NBSP}×{NBSP}cash digital"
"""Readout label of the K cash digitals in the asset-or-nothing decomposition (``K × cash
digital``; a narrow column may wrap it before "digital", never around the ×)."""

# ------------------------------------------------------------------ barrier


def barrier_readout_rows(
    data: BarrierData, metric: ExoticMetric, currency: str
) -> list[ReadoutRow]:
    """The greeks in ``currency`` desk units (selected metric highlighted), then the
    knock-in + knock-out = vanilla rows (premiums, uncoloured)."""
    p = data.parity
    return [
        *greek_rows(
            data.greeks,
            groups=None,
            keys=PRICED_READOUT_KEYS,
            selected=metric,
            currency=currency,
        ),
        group_row(PARITY_HEADING),
        ReadoutRow(
            BARRIER_KIND_LABELS[p.out_kind], p.knock_out, fmt_money(p.knock_out), tone="text"
        ),
        ReadoutRow(BARRIER_KIND_LABELS[p.in_kind], p.knock_in, fmt_money(p.knock_in), tone="text"),
        ReadoutRow(
            "Sum",
            p.total,
            fmt_money(p.total),
            unit=f"vanilla {fmt_money(p.vanilla)}",
            tone="text",
        ),
    ]


def barrier_note(i: BarrierInputs) -> str | None:
    """Why the barrier option reads as dead or as the vanilla, or ``None`` while the barrier
    still matters (:func:`~eqd_desk.app.ui.exotics_curves.barrier_status`): spot already
    through H, or the strike beyond H."""
    status = barrier_status(i)
    if status == "breached":
        return BARRIER_BREACHED_NOTES[i.kind]
    if status == "strike_beyond":
        return BARRIER_STRIKE_BEYOND_NOTES[barrier_sides(i.kind)[1]]
    return None


# ------------------------------------------------------------------ digital


def asset_rows(d: AssetDecomposition, price: float, option: OptionType) -> list[ReadoutRow]:
    """Asset-or-nothing = K cash digitals ± the vanilla, as readout rows (premiums,
    uncoloured): each row is a term of the heading with its sign (``+ vanilla call 312.24``,
    ``− vanilla put −19.82``), so the rows add up to the ``Sum`` row, the premium shown
    above them."""
    term = d.sign * d.vanilla
    call = option == "call"
    return [
        group_row(ASSET_CALL_HEADING if call else ASSET_PUT_HEADING),
        ReadoutRow(K_DIGITALS_LABEL, d.k_digitals, fmt_money(d.k_digitals), tone="text"),
        ReadoutRow(vanilla_term_label(option), term, fmt_money(term), tone="text"),
        ReadoutRow(
            "Sum", d.total, fmt_money(d.total), unit=f"premium {fmt_money(price)}", tone="text"
        ),
    ]


def vanilla_term_label(option: OptionType) -> str:
    """Readout label of the vanilla's term in the asset-or-nothing decomposition, with the
    sign it enters with: ``+ vanilla call``, ``− vanilla put`` (the sign glued to
    "vanilla", so a wrap never leaves it alone on a line)."""
    sign = "+" if option == "call" else MINUS
    return f"{sign}{NBSP}vanilla {option}"


def digital_chart_caption(is_price: bool, payout: DigitalPayout, option: OptionType) -> str:
    """The caption under the digital's value-vs-spot chart: how to read the digital against
    its replication (the cash digital's call spread, or the asset-or-nothing's vanilla ±
    K/Δ spreads, which differ between a call and a put), or the greek caption."""
    if not is_price:
        return DIGITAL_GREEK_CAPTION
    return DIGITAL_PRICE_CAPTION if payout == "cash" else DIGITAL_ASSET_PRICE_CAPTIONS[option]


def convergence_note(
    spread: float, digital: float, i: DigitalInputs, width: float, payout: DigitalPayout
) -> str:
    """The numbers under the convergence chart: the replication vs the digital at the
    chosen width, and what the replication holds."""
    name = "spread" if payout == "cash" else "replication"
    return (
        f"At Δ = {fmt_money(width)}: {name} {fmt_money(spread)} vs digital "
        f"{fmt_money(digital)} (difference {fmt_signed(spread - digital, 3)}), "
        f"{replication_recipe(i, width, payout)}."
    )


# ------------------------------------------------------------------ autocallable


def autocall_readout_rows(
    data: AutocallData, metric: ExoticMetric, currency: str
) -> list[ReadoutRow]:
    """Diagnostics (P(autocall) and the expected life uncoloured, P(capital loss) in red),
    then the MC greeks in ``currency`` desk units."""
    res = data.result
    p_call, p_loss, life = AUTOCALL_DIAGNOSTICS
    return [
        group_row("Diagnostics"),
        ReadoutRow(
            p_call.label,
            res.prob_autocall,
            fmt_pct(res.prob_autocall, 1),
            p_call.note,
            tone="text",
        ),
        ReadoutRow(
            p_loss.label,
            res.prob_capital_loss,
            fmt_pct(res.prob_capital_loss, 1),
            p_loss.note,
            tone="neg",
        ),
        ReadoutRow(
            life.label, res.expected_life, fmt_num(res.expected_life, 3), life.note, tone="text"
        ),
        group_row("Greeks (MC)"),
        *greek_rows(
            data.greeks,
            groups=None,
            keys=AUTOCALL_READOUT_KEYS,
            selected=metric,
            currency=currency,
        ),
    ]


# ------------------------------------------------------------------ variance swap


def varswap_readout_rows(data: VarSwapData, currency: str) -> list[ReadoutRow]:
    """Fair variance, ATM vol and the forward (uncoloured), and the convexity premium
    (fair − ATM, green / red)."""
    fair_var, atm, premium = VARSWAP_READOUT
    cp = data.convexity_premium
    return [
        ReadoutRow(
            fair_var.label,
            data.fair_variance,
            fmt_num(data.fair_variance, 5),
            fair_var.note,
            tone="text",
        ),
        ReadoutRow(atm.label, data.atm_vol, fmt_pct(data.atm_vol), atm.note, tone="text"),
        ReadoutRow(
            premium.label, cp, fmt_signed_pct(cp), premium.note, "pos" if cp >= 0 else "neg"
        ),
        ReadoutRow("Forward", data.forward, fmt_money(data.forward), currency, tone="text"),
    ]


def skew_note(data: VarSwapData, c: VarSwapControls) -> str:
    """The numbers under the skew-effect chart: fair vs ATM at the current slope (or with
    the skew off), and the strip the fair variance was replicated with."""
    where = f"At slope {fmt_num(c.slope, 3)}" if c.skew else "Skew off (flat smile)"
    return (
        f"{where}: fair vol {fmt_pct(data.fair_vol)} vs ATM "
        f"{fmt_pct(data.atm_vol)} ({fmt_signed_pct(data.convexity_premium)}); strip "
        f"{fmt_level(c.lo_mult * data.forward, 0)} to {fmt_level(c.hi_mult * data.forward, 0)}, "
        f"{c.n_strikes} strikes."
    )


__all__ = [
    "ASSET_CALL_HEADING",
    "ASSET_PUT_HEADING",
    "K_DIGITALS_LABEL",
    "PARITY_HEADING",
    "asset_rows",
    "autocall_readout_rows",
    "barrier_note",
    "barrier_readout_rows",
    "convergence_note",
    "digital_chart_caption",
    "skew_note",
    "vanilla_term_label",
    "varswap_readout_rows",
]
