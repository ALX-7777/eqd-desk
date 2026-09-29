"""The net-premium readout of the strategy builder: debit and credit as in the React app,
and two neutral states it lacks (no legs; premiums that cancel), which never print a signed
zero."""

from __future__ import annotations

import pytest

from eqd_desk.app.ui.format import MINUS
from eqd_desk.app.ui.strategy_builder_readout import (
    FLAT_BADGE,
    FLAT_NOTE,
    ZERO_COST_BADGE,
    ZERO_COST_NOTE,
    PremiumView,
    premium_view,
)
from eqd_desk.content.strategies import PREMIUM_SIDE_NOTES


def test_a_debit_reads_like_the_react_readout() -> None:
    assert premium_view(146.3921, n_legs=3) == PremiumView(
        value=f"{MINUS}146.39",
        badge="DEBIT",
        badge_color="primary",
        detail=PREMIUM_SIDE_NOTES["debit"],
        tone=None,
    )


def test_a_credit_reads_like_the_react_readout() -> None:
    assert premium_view(-221.974, n_legs=4) == PremiumView(
        value="+221.97",
        badge="CREDIT",
        badge_color="gray",
        detail=PREMIUM_SIDE_NOTES["credit"],
        tone="pos",
    )


def test_no_legs_is_flat_not_a_debit() -> None:
    view = premium_view(0.0, n_legs=0)
    assert view == PremiumView("0.00", FLAT_BADGE, "gray", FLAT_NOTE, None)
    assert MINUS not in view.value


@pytest.mark.parametrize("price", [0.0, -0.0, 0.004, -0.004])
def test_premiums_that_cancel_to_the_cent_are_zero_cost(price: float) -> None:
    view = premium_view(price, n_legs=2)
    assert view == PremiumView("0.00", ZERO_COST_BADGE, "gray", ZERO_COST_NOTE, None)


@pytest.mark.parametrize(("price", "value"), [(0.005, f"{MINUS}0.01"), (-0.006, "+0.01")])
def test_a_premium_of_a_cent_keeps_its_side(price: float, value: str) -> None:
    assert premium_view(price, n_legs=1).value == value
