"""The two charts of the strategy builder (``StrategyPlots.tsx``), built on the shared
:mod:`eqd_desk.app.ui.charts` look. Pure: frames in, Altair charts out.

1. :func:`pnl_chart` — P&L vs terminal spot: at the front expiry (the classic payoff
   diagram) and now (mark-to-market), with the spot slider (dashed), the strikes (dotted)
   and the zero line, where the break-evens are.
2. :func:`greek_profile_chart` — one aggregate greek swept across spot, a parallel vol
   shift or elapsed time, with today's position marked (dashed).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import altair as alt
import pandas as pd

from eqd_desk.app.ui import charts, theme
from eqd_desk.app.ui.charts import Series, VRule
from eqd_desk.app.ui.format import to_fixed
from eqd_desk.app.ui.strategy_curves import AxisMeta
from eqd_desk.content import GreekKey
from eqd_desk.engine import GREEK_UNITS

X_TICK_COUNT: Final = 8
"""Tick-count hint of the x axes. Without it Vega picks a 200-point step on the spot axis
(70 %–130 % of spot) and the grouped mono labels collide in a centre-column-wide chart."""

NOW_LABEL: Final = "Now"
"""Legend / tooltip name of the mark-to-market P&L (React tooltip ``'Now'``)."""
EXPIRY_LABEL: Final = "At expiry"
"""Legend / tooltip name of the front-expiry P&L (React tooltip ``'At expiry'``)."""


def _spot_tick(x: float) -> str:
    """Tooltip text of a spot (React ``Number(v).toFixed(0)``)."""
    return to_fixed(x, 0)


def _tidy_x(chart: alt.LayerChart) -> alt.LayerChart:
    """Fewer, non-overlapping x tick labels (see :data:`X_TICK_COUNT`)."""
    tidy: alt.LayerChart = chart.configure_axisX(tickCount=X_TICK_COUNT, labelOverlap=True)
    return tidy


def pnl_chart(
    payoff: pd.DataFrame,
    *,
    spot: float,
    strikes: Sequence[float],
    currency: str,
    height: int = charts.DEFAULT_HEIGHT,
) -> alt.LayerChart:
    """P&L vs terminal spot from a :func:`~eqd_desk.app.ui.strategy_curves.payoff_frame`
    (columns ``S``, ``expiry``, ``now``).

    The expiry curve is the main line (2 px), the mark-to-market the thin accent one; the
    dashed rule is the spot slider (``spot``), the dotted ones the distinct ``strikes``.
    """
    return _tidy_x(
        charts.line_chart(
            payoff,
            x="S",
            series=[
                Series("now", NOW_LABEL, color=theme.ACCENT, width=1.5),
                Series("expiry", EXPIRY_LABEL, color=theme.LINE, width=2.0),
            ],
            x_title="Spot",
            y_title=f"P&L ({currency})",
            x_tooltip=_spot_tick,
            vrules=[VRule(spot, "current"), *(VRule(k, "strike") for k in dict.fromkeys(strikes))],
            height=height,
        )
    )


def greek_profile_title(greek: GreekKey) -> str:
    """Name of the plotted aggregate: ``"Net Delta"`` (React ``Net ${unit.label}``)."""
    return f"Net {GREEK_UNITS[greek].label}"


def greek_profile_chart(
    sweep: pd.DataFrame,
    meta: AxisMeta,
    greek: GreekKey,
    *,
    height: int = charts.SHORT_HEIGHT,
) -> alt.LayerChart:
    """One aggregate greek from a :func:`~eqd_desk.app.ui.strategy_curves.greek_sweep`
    frame, plotted in trader units (spot, vol points, days) with ``meta``'s ticks and the
    "now" marker; the y axis carries the greek's desk unit."""
    title = greek_profile_title(greek)
    return _tidy_x(
        charts.line_chart(
            pd.DataFrame({"x": sweep["x_plot"], "y": sweep[greek]}),
            x="x",
            series=Series("y", title),
            x_title=meta.axis_title,
            y_title=f"{title} ({GREEK_UNITS[greek].unit})",
            x_format=meta.axis_format,
            x_tooltip=meta.tick,
            vrules=[VRule(meta.current * meta.plot_scale, "current")],
            height=height,
        )
    )


__all__ = [
    "EXPIRY_LABEL",
    "NOW_LABEL",
    "X_TICK_COUNT",
    "greek_profile_chart",
    "greek_profile_title",
    "pnl_chart",
]
