"""Two-way quoting and fill logic on a package (single or multi-leg).

You quote around the NET fair, with the spread and your lean sized off the GROSS premium
(Σ|leg premium|) so credit/zero-cost structures (e.g. risk reversals) still have a
well-defined width::

    client BUYS  ⇒ fills if your ask ≤ trueValue  (you go SHORT the package)
    client SELLS ⇒ fills if your bid ≥ trueValue  (you go LONG  the package)

``trueValue = netFair + noiseFrac·gross·Z``. Wider spread = more edge per fill, lower fill
probability. ``lean`` shifts your mid (as a fraction of gross) to skew your price toward
the flow you want; leaning past fair gives up edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from eqd_desk.engine.sim.rfq import RFQ

YourSide = Literal["buy", "sell"]
"""What YOU do on a fill (always the opposite of the client)."""


@dataclass(frozen=True, slots=True)
class FillResult:
    """Outcome of one quote."""

    filled: bool
    """Whether the client traded on your price."""
    you_side: YourSide | None
    """Your side if filled (``"sell"`` when the client buys), else ``None``."""
    price: float
    """Traded NET package price (your ask if the client buys, your bid if they sell)."""
    edge: float
    """Edge captured vs net fair (× size); 0 if not filled (can be < 0 if you lean past
    fair)."""
    bid: float
    """Your bid (net package price)."""
    ask: float
    """Your ask (net package price)."""
    fair_value: float
    """Net fair the quote was built around."""


def evaluate_quote(
    rfq: RFQ,
    net_fair: float,
    gross: float,
    spread_frac: float,
    noise_frac: float,
    z: float,
    lean: float = 0.0,
) -> FillResult:
    """Build your two-way around ``net_fair`` and decide whether the client trades.

    ::

        halfWidth = (spreadFrac / 2)·gross
        mid       = netFair + lean·gross
        ask, bid  = mid ± halfWidth
        trueValue = netFair + noiseFrac·gross·z       (the client's noisy valuation)

    Args:
        rfq: the request being quoted (its ``client_side`` and ``size`` matter).
        net_fair: signed fair value of ONE package (debit positive).
        gross: Σ|leg premium| of one package (≥ 0): the scale for width, lean and noise.
        spread_frac: full bid/ask width as a fraction of ``gross``.
        noise_frac: std-dev of the client's valuation noise, as a fraction of ``gross``.
        z: a standard-normal draw (the client's noise).
        lean: mid shift as a fraction of ``gross`` (+ ⇒ higher prices).
    """
    half_width = (spread_frac / 2) * gross
    mid = net_fair + lean * gross
    ask = mid + half_width
    bid = mid - half_width
    true_value = net_fair + noise_frac * gross * z

    if rfq.client_side == "buy":
        filled = ask <= true_value
        return FillResult(
            filled=filled,
            you_side="sell" if filled else None,
            price=ask,
            edge=(ask - net_fair) * rfq.size if filled else 0.0,
            bid=bid,
            ask=ask,
            fair_value=net_fair,
        )
    filled = bid >= true_value
    return FillResult(
        filled=filled,
        you_side="buy" if filled else None,
        price=bid,
        edge=(net_fair - bid) * rfq.size if filled else 0.0,
        bid=bid,
        ask=ask,
        fair_value=net_fair,
    )


__all__ = ["FillResult", "YourSide", "evaluate_quote"]
