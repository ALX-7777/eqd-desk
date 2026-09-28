"""Quote / fill logic. Port of the ``quote / fill logic`` block of
``web/src/engine/sim/__tests__/sim.test.ts``, plus the lean and client-sells branches."""

from __future__ import annotations

import pytest

from eqd_desk.engine.sim import evaluate_quote, single_option_rfq

RFQ_BUY = single_option_rfq("call", 100, 0.25, 10, "buy", 1)


def test_client_buys_only_if_ask_beats_their_noisy_value_edge_positive_on_fill() -> None:
    fair = 10  # net == gross for a single positive-priced option
    win = evaluate_quote(RFQ_BUY, fair, fair, 0.04, 0.1, 0.5)
    assert win.filled is True
    assert win.you_side == "sell"
    assert win.edge > 0
    lose = evaluate_quote(RFQ_BUY, fair, fair, 0.04, 0.1, 0.0)
    assert lose.filled is False
    assert lose.edge == 0


def test_wider_spread_needs_a_more_favourable_client_to_fill() -> None:
    z = 0.3
    tight = evaluate_quote(RFQ_BUY, 10, 10, 0.04, 0.1, z)  # threshold 0.2 < 0.3 → fills
    wide = evaluate_quote(RFQ_BUY, 10, 10, 0.08, 0.1, z)  # threshold 0.4 > 0.3 → misses
    assert tight.filled is True
    assert wide.filled is False


# --- beyond the TS tests -------------------------------------------------------------------


def test_quote_levels_and_client_sells_branch() -> None:
    rfq_sell = single_option_rfq("put", 100, 0.25, 20, "sell", 2)
    f = evaluate_quote(rfq_sell, 8, 8, 0.05, 0.1, -0.4)
    assert f.ask == pytest.approx(8 + 0.2, rel=1e-15)
    assert f.bid == pytest.approx(8 - 0.2, rel=1e-15)
    assert f.fair_value == 8
    # client values it at 8 − 0.32 = 7.68 ≤ your bid 7.8 ⇒ they sell to you, you buy
    assert f.filled is True
    assert f.you_side == "buy"
    assert f.price == f.bid
    assert f.edge == pytest.approx((8 - 7.8) * 20, rel=1e-12)
    miss = evaluate_quote(rfq_sell, 8, 8, 0.05, 0.1, 0.0)
    assert (miss.filled, miss.you_side, miss.edge) == (False, None, 0)


def test_leaning_past_fair_gives_up_edge() -> None:
    # lean −5% of gross with a 4% spread puts your ask BELOW fair: fills, negative edge
    f = evaluate_quote(RFQ_BUY, 10, 10, 0.04, 0.1, -0.1, lean=-0.05)
    assert f.filled is True
    assert f.ask == pytest.approx(9.7, rel=1e-14)
    assert f.edge == pytest.approx((9.7 - 10) * 10, rel=1e-12)
    assert f.edge < 0
