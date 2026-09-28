"""Client RFQ generation. Port of the ``RFQ generation`` block of
``web/src/engine/sim/__tests__/sim.test.ts``, plus checks of the draw order and geometry."""

from __future__ import annotations

from eqd_desk.engine.presets import PresetParams, build_preset
from eqd_desk.engine.rng import Mulberry32
from eqd_desk.engine.sim import RFQ, RfqLeg, generate_rfq, single_option_rfq


def test_produces_valid_reproducible_single_and_structure_requests() -> None:
    rng = Mulberry32(99)
    multi_leg = 0
    for n in range(80):
        rfq = generate_rfq(100, 5, rng, n)
        assert rfq.client_side in ("buy", "sell")
        assert rfq.size > 0
        assert len(rfq.legs) >= 1
        if len(rfq.legs) > 1:
            multi_leg += 1
        for leg in rfq.legs:
            assert leg.type in ("call", "put")
            assert leg.K > 0
            assert leg.T > 0
            assert leg.ratio > 0
    assert multi_leg > 0  # some structures appear
    r1 = generate_rfq(100, 5, Mulberry32(1), 0)
    r2 = generate_rfq(100, 5, Mulberry32(1), 0)
    assert r1 == r2


# --- beyond the TS tests -------------------------------------------------------------------


class _Scripted:
    """A uniform "generator" replaying fixed draws (to pin down the draw order)."""

    def __init__(self, draws: list[float]) -> None:
        self.draws = draws
        self.used = 0

    def __call__(self) -> float:
        v = self.draws[self.used]
        self.used += 1
        return v


def test_single_rfq_draw_order_and_strike_rounding() -> None:
    # structure 0.1·13 = 1.3 < 4 ⇒ single call; tenor 0.3 ⇒ 3m; side 0.7 ⇒ sell;
    # size 0.8 ⇒ 100; offset (0.9 − 0.5)·0.2 = +8% ⇒ 108 → rounded to the 5-grid = 110
    rng = _Scripted([0.1, 0.3, 0.7, 0.8, 0.9])
    rfq = generate_rfq(100, 5, rng, id=7, day=3)
    assert rng.used == 5
    assert rfq == RFQ(
        id=7,
        label="Call",
        legs=(RfqLeg(type="call", side="long", ratio=1, K=110, T=0.25),),
        size=100,
        client_side="sell",
        born_day=3,
    )


def test_single_rfq_strike_never_below_one_step() -> None:
    # 0.4·13 = 5.2 ∈ [4, 8) ⇒ single put; offset −10% of a tiny spot rounds to 0 ⇒ one step
    rfq = generate_rfq(1, 5, _Scripted([0.4, 0.0, 0.2, 0.0, 0.0]), id=1)
    assert rfq.label == "Put"
    assert rfq.client_side == "buy"
    assert rfq.legs[0].K == 5
    assert rfq.legs[0].T == 1 / 12
    assert rfq.size == 10


def test_structure_rfq_uses_the_preset_geometry() -> None:
    # 0.7·13 = 9.1 ⇒ past singles (8) and straddle (9) ⇒ strangle; width 3% + 0.5·5% = 5.5%
    rng = _Scripted([0.7, 0.99, 0.2, 0.5, 0.5])
    rfq = generate_rfq(6312.45, 25, rng, id=2)
    assert rng.used == 5
    assert rfq.label == "Strangle"
    expected = build_preset(
        "strangle",
        PresetParams(
            S=6312.45, base_t=1, width_pct=0.03 + 0.5 * 0.05, strike_step=25, vol_for=lambda K, T: 0
        ),
    )
    assert rfq.legs == tuple(
        RfqLeg(type=leg.type, side=leg.side, ratio=leg.quantity, K=leg.K, T=leg.T)
        for leg in expected
    )
    assert rfq.size == 50


def test_single_option_rfq() -> None:
    rfq = single_option_rfq("put", 95, 0.5, 30, "sell", 4)
    assert rfq.label == "Put"
    assert rfq.legs == (RfqLeg(type="put", side="long", ratio=1, K=95, T=0.5),)
    assert (rfq.size, rfq.client_side, rfq.id, rfq.born_day) == (30, "sell", 4, 0)
