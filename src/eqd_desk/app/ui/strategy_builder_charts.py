"""The two charts of the strategy builder (``StrategyPlots.tsx``), built on the shared
:mod:`eqd_desk.app.ui.charts` look. Pure: frames in, Altair charts out.

1. :func:`pnl_chart` — P&L vs terminal spot: at the front expiry (the classic payoff
   diagram) and now (mark-to-market), with the spot slider (dashed), the strikes (dotted)
   and the zero line, where the break-evens are.
2. :func:`greek_profile_chart` — one aggregate greek swept across spot, a parallel vol
   shift or elapsed time, with today's position marked (dashed).

Both read like React's: y ticks ``fmtNum(v, 3)`` and a tidy x axis (the shared defaults).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import altair as alt
import pandas as pd

from eqd_desk.app.ui import charts
from eqd_desk.app.ui.charts import Series, VRule
from eqd_desk.app.ui.strategy_curves import AxisMeta
from eqd_desk.app.ui.units import axis_title
from eqd_desk.content import GreekKey
from eqd_desk.engine import GREEK_UNITS

NET_PREFIX: Final = "Net "
"""Qualifies an aggregate of the whole structure ("Net Delta")."""

EMPTY_CHARTS_NOTE: Final = (
    "Nothing to plot yet: the P&L and greek profiles appear once the structure has a leg. "
    "Pick a preset or add a leg."
)
"""Shown in place of both charts while the position has no legs (a flat zero line with a
break-even caption would read as a broken chart)."""


def pnl_chart(
    payoff: pd.DataFrame,
    *,
    spot: float,
    strikes: Sequence[float],
    currency: str,
    height: int = charts.DEFAULT_HEIGHT,
) -> alt.LayerChart:
    """P&L vs terminal spot from a :func:`~eqd_desk.app.ui.strategy_curves.payoff_frame`
    (columns ``S``, ``expiry``, ``now``): :func:`~eqd_desk.app.ui.charts.payoff_chart`
    with a ``P&L (<currency>)`` axis (the hover prints money: ``-62.25``).

    The expiry curve is the main line (2 px), the mark-to-market the thin accent one; the
    dashed rule is the spot slider (``spot``), the dotted ones the distinct ``strikes``.
    """
    return charts.payoff_chart(
        payoff["S"],
        payoff["expiry"],
        payoff["now"],
        spot=spot,
        strikes=strikes,
        y_title=f"P&L ({currency})",
        height=height,
    )


def greek_profile_title(greek: GreekKey) -> str:
    """Name of the plotted aggregate: ``"Net Delta"`` (React ``Net ${unit.label}``)."""
    return f"{NET_PREFIX}{GREEK_UNITS[greek].label}"


def greek_profile_chart(
    sweep: pd.DataFrame,
    meta: AxisMeta,
    greek: GreekKey,
    *,
    currency: str,
    height: int = charts.SHORT_HEIGHT,
) -> alt.LayerChart:
    """One aggregate greek from a :func:`~eqd_desk.app.ui.strategy_curves.greek_sweep`
    frame, plotted in trader units (spot, vol points, days) with ``meta``'s ticks and the
    "now" marker; the y axis carries the greek's desk unit in ``currency`` (the price, its
    currency: ``"Net Price (USD)"``)."""
    return charts.line_chart(
        pd.DataFrame({"x": sweep["x_plot"], "y": sweep[greek]}),
        x="x",
        series=Series("y", greek_profile_title(greek)),
        x_title=meta.axis_title,
        y_title=axis_title(greek, currency, prefix=NET_PREFIX),
        x_format=meta.axis_format,
        x_tooltip=meta.tick,
        vrules=[VRule(meta.current * meta.plot_scale, "current")],
        height=height,
    )


__all__ = [
    "EMPTY_CHARTS_NOTE",
    "NET_PREFIX",
    "greek_profile_chart",
    "greek_profile_title",
    "pnl_chart",
]
