"""What the exotics page shows besides its charts (the pure
:mod:`eqd_desk.app.ui.exotics_display`): each decomposition reads down its rows (every row a
signed term of its heading, the terms adding up to the ``Sum`` row), the barrier's "already
knocked" notes appear exactly when the engine prices a dead knock-out, and the captions and
notes follow the payout and the metric."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from eqd_desk.app.ui import exotics_curves as ec
from eqd_desk.app.ui import exotics_display as xd
from eqd_desk.app.ui.format import MINUS, fmt_money
from eqd_desk.app.ui.readout import NBSP, ReadoutRow
from eqd_desk.content.exotics import (
    AUTOCALL_DIAGNOSTICS,
    BARRIER_BREACHED_NOTES,
    BARRIER_STRIKE_BEYOND_NOTES,
    DIGITAL_ASSET_PRICE_CAPTIONS,
    DIGITAL_GREEK_CAPTION,
    DIGITAL_PRICE_CAPTION,
)
from eqd_desk.data import MarketSnapshot, load_snapshot
from eqd_desk.engine import OptionType
from eqd_desk.engine.exotics import BarrierInputs, BarrierKind, barrier_price

OPTIONS: tuple[OptionType, ...] = ("call", "put")
KINDS: tuple[BarrierKind, ...] = ("down-out", "down-in", "up-out", "up-in")


@pytest.fixture(scope="module")
def snap() -> MarketSnapshot:
    return load_snapshot()


def terms(rows: list[ReadoutRow]) -> tuple[str, list[ReadoutRow], ReadoutRow]:
    """(heading, term rows, Sum row) of a decomposition block."""
    heading, *body, total = rows
    assert heading.kind == "group"
    assert total.label == "Sum"
    return heading.label, body, total


# ------------------------------------------------------------------ asset-or-nothing


@pytest.mark.parametrize("option", OPTIONS)
@pytest.mark.parametrize("T", [0.005, 0.25, 1.0])
def test_asset_rows_read_down_to_the_premium(
    snap: MarketSnapshot, option: OptionType, T: float
) -> None:
    """Regression: the put's vanilla row read "Vanilla put −19.82" under "… − vanilla" (a
    double negative: the heading then gives K × digital + 19.82, not the Sum). Each row is
    now a term with its sign, so the rows add up to the Sum as printed."""
    i = replace(ec.digital_seed(snap), type=option, T=T)
    d = ec.asset_decomposition(i)
    price = ec.digital_price(i, "asset")
    heading, body, total = terms(xd.asset_rows(d, price, option))
    assert heading == (xd.ASSET_CALL_HEADING if option == "call" else xd.ASSET_PUT_HEADING)
    digitals, vanilla = body
    assert (digitals.label, digitals.value) == (xd.K_DIGITALS_LABEL, d.k_digitals)
    # the vanilla row carries the sign the heading gives it, on its label AND its value
    assert vanilla.label == xd.vanilla_term_label(option)
    assert d.vanilla > 0
    sign = "+" if option == "call" else MINUS
    assert vanilla.label.startswith(sign)
    assert f"{sign} vanilla" in heading
    assert vanilla.value == (d.vanilla if option == "call" else -d.vanilla)
    assert vanilla.text == fmt_money(vanilla.value)
    # reading down: the terms add up to the Sum row, which is the premium
    assert math.fsum(r.value for r in body) == pytest.approx(total.value, rel=1e-12)
    assert total.value == pytest.approx(price, rel=1e-12)
    assert total.unit == f"premium {fmt_money(price)}"


def test_decomposition_labels_never_strand_an_operator() -> None:
    """A narrow column may wrap a label, but never right after its sign or around ×."""
    assert xd.vanilla_term_label("call") == f"+{NBSP}vanilla call"
    assert xd.vanilla_term_label("put") == f"{MINUS}{NBSP}vanilla put"
    assert xd.K_DIGITALS_LABEL == f"K{NBSP}×{NBSP}cash digital"
    assert xd.K_DIGITALS_LABEL.replace(NBSP, " ") == "K × cash digital"


# ------------------------------------------------------------------ barrier


@pytest.mark.parametrize("kind", KINDS)
def test_barrier_parity_rows_read_down_to_the_vanilla(
    snap: MarketSnapshot, kind: BarrierKind
) -> None:
    H = 5675.0 if kind.startswith("down") else 7025.0
    i = replace(ec.barrier_seed(snap), kind=kind, H=H)
    data = ec.barrier_data(i, "gamma", snap.spot)
    rows = xd.barrier_readout_rows(data, "gamma", "USD")
    labels = [r.label for r in rows]
    assert labels[:5] == ["Delta", "Gamma", "Vega", "Theta", "Rho"]
    assert [r.selected for r in rows[:5]] == [False, True, False, False, False]
    heading, body, total = terms(rows[5:])
    assert heading == xd.PARITY_HEADING
    direction = kind.split("-")[0].capitalize()
    assert [r.label for r in body] == [f"{direction}-out", f"{direction}-in"]
    assert math.fsum(r.value for r in body) == pytest.approx(total.value, rel=1e-12)
    assert total.value == pytest.approx(data.parity.vanilla, rel=1e-9)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("option", OPTIONS)
def test_barrier_note_explains_every_dead_knock_out(
    snap: MarketSnapshot, kind: BarrierKind, option: OptionType
) -> None:
    """The note appears exactly when the knock-out is worth nothing (and the knock-in is
    the vanilla): breached, or struck beyond the barrier; it names the right case."""
    seed = replace(ec.barrier_seed(snap), type=option, kind=kind)
    down = kind.startswith("down")
    live_H = 5675.0 if down else 7025.0
    cases: list[tuple[BarrierInputs, str | None]] = [
        (replace(seed, H=live_H), None),
        (replace(seed, H=seed.S), BARRIER_BREACHED_NOTES[kind]),  # touching
        (replace(seed, H=7025.0 if down else 5675.0), BARRIER_BREACHED_NOTES[kind]),
    ]
    beyond_K = 5500.0 if down else 7200.0  # K beyond the live barrier
    struck_beyond = replace(seed, H=live_H, K=beyond_K)
    dead_by_strike = (down and option == "put") or (not down and option == "call")
    knock = ec.barrier_sides(kind)[1]
    cases.append((struck_beyond, BARRIER_STRIKE_BEYOND_NOTES[knock] if dead_by_strike else None))
    out_kind = kind if knock == "out" else ec.BARRIER_COMPLEMENT[kind]
    for i, note in cases:
        assert xd.barrier_note(i) == note, (i.S, i.K, i.H)
        knock_out = barrier_price(replace(i, kind=out_kind))
        assert (knock_out == 0.0) == (note is not None), (i.S, i.K, i.H, knock_out)


def test_barrier_notes_name_the_kind_and_the_fix() -> None:
    for kind, text in BARRIER_BREACHED_NOTES.items():
        direction, knock = kind.split("-")
        assert f"{direction}-and-{knock}" in text
        assert ("above spot" if direction == "up" else "below spot") in text
        assert ("worth nothing" if knock == "out" else "the vanilla") in text
    assert "worth nothing" in BARRIER_STRIKE_BEYOND_NOTES["out"]
    assert "vanilla" in BARRIER_STRIKE_BEYOND_NOTES["in"]


# ------------------------------------------------------------------ digital


def test_digital_chart_caption_follows_the_payout_and_the_metric() -> None:
    assert xd.digital_chart_caption(True, "cash", "put") == DIGITAL_PRICE_CAPTION
    assert xd.digital_chart_caption(False, "cash", "call") == DIGITAL_GREEK_CAPTION
    assert xd.digital_chart_caption(False, "asset", "call") == DIGITAL_GREEK_CAPTION
    for option in OPTIONS:
        caption = xd.digital_chart_caption(True, "asset", option)
        assert caption == DIGITAL_ASSET_PRICE_CAPTIONS[option]
    # a call's replication adds the vanilla, a put's subtracts it
    assert "vanilla call +" in xd.digital_chart_caption(True, "asset", "call")
    assert "− a vanilla put" in xd.digital_chart_caption(True, "asset", "put")


def test_convergence_note_names_the_replication(snap: MarketSnapshot) -> None:
    i = ec.digital_seed(snap)
    cash = xd.convergence_note(53.1, 53.14, i, 125.0, "cash")
    assert cash.startswith("At Δ = 125.00: spread 53.10 vs digital 53.14 (difference −0.0400)")
    assert cash.endswith(f"{ec.replication_recipe(i, 125.0, 'cash')}.")
    asset = xd.convergence_note(2730.66, 2730.5, replace(i, type="put"), 125.0, "asset")
    assert "replication 2,730.66" in asset
    assert asset.endswith("put spreads − 1 vanilla put.")


# ------------------------------------------------------------------ autocallable


def test_autocall_rows_show_the_diagnostics_then_the_reported_greeks(
    snap: MarketSnapshot,
) -> None:
    data = ec.autocall_data(ec.autocall_seed(snap))
    rows = xd.autocall_readout_rows(data, "vega", "USD")
    labels = [r.label for r in rows]
    assert labels == [
        "Diagnostics",
        *(n.label for n in AUTOCALL_DIAGNOSTICS),
        "Greeks (MC)",
        "Delta",
        "Vega",
        "Theta",
        "Rho",
    ]
    assert "Gamma" not in labels
    assert [r.label for r in rows if r.selected] == ["Vega"]
    assert rows[2].tone == "neg"  # P(capital loss)


# ------------------------------------------------------------------ variance swap


def test_varswap_rows_and_skew_note(snap: MarketSnapshot) -> None:
    c = ec.varswap_seed(snap)
    data = ec.varswap_data(c, S=snap.spot, r=snap.r, q=snap.q)
    rows = xd.varswap_readout_rows(data, "USD")
    assert [r.label for r in rows] == ["Fair variance", "ATM vol", "Convexity premium", "Forward"]
    assert rows[2].tone == "pos"  # equity skew: fair vol above ATM
    assert rows[3].unit == "USD"
    assert xd.skew_note(data, c).startswith("At slope -0.480: fair vol")  # fmtNum, as React
    flat = replace(c, skew=False)
    flat_data = ec.varswap_data(flat, S=snap.spot, r=snap.r, q=snap.q)
    assert xd.skew_note(flat_data, flat).startswith("Skew off (flat smile): fair vol")
    assert xd.skew_note(data, c).endswith("400 strikes.")
