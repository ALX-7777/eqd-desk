"""The simulator's three charts (pure builders over :mod:`eqd_desk.app.ui.charts`).

- :func:`pnl_chart`: the book's mark-to-market P&L day by day (React: the accent line under
  the P&L hero).
- :func:`explain_chart`: the cumulative P&L explain, one signed bar per Taylor term plus the
  residual.
- :func:`path_chart`: spot (left axis) and ATM implied vol (right axis) along the session, so
  the leverage effect (spot down, vol up) is visible.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, cast

import altair as alt

from eqd_desk.app.ui import theme
from eqd_desk.app.ui.charts import SHORT_HEIGHT, Series, bar_chart, dual_axis_chart, line_chart
from eqd_desk.app.ui.format import fmt_money, fmt_pct
from eqd_desk.app.ui.sim_session import CumAttribution, HistPoint, js_number
from eqd_desk.app.ui.simulator_display import attribution_bars, history_frame

MONEY_AXIS: Final = ",.2~f"
"""d3 format of a money axis: grouped, at most 2 decimals, trailing zeros dropped (also
keeps a flat, all-zero series from printing ``0.000000``)."""

DAY_FORMAT: Final = "d"
"""d3 format of the day axis (whole days; ticks are at least one day apart)."""


def _day_axis(chart: alt.LayerChart) -> alt.LayerChart:
    """Whole-day ticks on the x axis (no ``0.5`` days on a short session)."""
    return cast("alt.LayerChart", chart.configure_axisX(format=DAY_FORMAT, tickMinStep=1))


def day_text(day: float) -> str:
    """Tooltip x value: ``"Day 12"``."""
    return f"Day {js_number(day)}"


def pnl_chart(history: Sequence[HistPoint], currency: str) -> alt.LayerChart:
    """Mark-to-market P&L of the book against the session day (zero line included)."""
    chart = line_chart(
        history_frame(history),
        x="day",
        series=Series("pnl", "P&L", color=theme.ACCENT),
        x_title="Day",
        y_title=f"P&L ({currency})",
        y_format=MONEY_AXIS,
        x_tooltip=day_text,
        y_tooltip=fmt_money,
        height=SHORT_HEIGHT,
    )
    return _day_axis(chart)


def explain_chart(cum: CumAttribution, currency: str) -> alt.LayerChart:
    """The cumulative P&L explain: delta, gamma, theta, vega, vanna, volga, residual."""
    labels, values = attribution_bars(cum)
    chart = bar_chart(labels, values, y_title=f"P&L ({currency})", height=SHORT_HEIGHT)
    return cast("alt.LayerChart", chart.configure_axisY(format=MONEY_AXIS))


def path_chart(history: Sequence[HistPoint]) -> alt.LayerChart:
    """Spot (left axis, index points) and ATM implied vol (right axis) by day."""
    chart = dual_axis_chart(
        history_frame(history),
        x="day",
        left=Series("spot", "Spot", color=theme.LINE),
        right=Series("vol", "ATM vol", color=theme.PUT, width=1.5),
        x_title="Day",
        left_title="Spot",
        right_title="ATM implied vol",
        left_format=",.0f",
        right_format=".1%",
        x_tooltip=day_text,
        left_tooltip=fmt_money,
        right_tooltip=fmt_pct,
        height=SHORT_HEIGHT,
    )
    return _day_axis(chart)


__all__ = ["DAY_FORMAT", "MONEY_AXIS", "day_text", "explain_chart", "path_chart", "pnl_chart"]
