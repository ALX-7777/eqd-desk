"""The simulator's three charts (pure builders over :mod:`eqd_desk.app.ui.charts`).

- :func:`pnl_chart`: the book's mark-to-market P&L day by day (React: the accent line under
  the P&L hero).
- :func:`explain_chart`: the cumulative P&L explain, one signed bar per Taylor term plus the
  residual.
- :func:`path_chart`: spot (left axis) and ATM implied vol (right axis) along the session, so
  the leverage effect (spot down, vol up) is visible.

Every x axis is the session day in whole days (:data:`DAY_FORMAT`), on top of the shared
tidy x axis (about eight ticks, labels thinned so they never collide). The two money axes
share :data:`MONEY_AXIS`. At day 0 the path is a single point, which a line cannot draw, so
the two path charts mark it with a dot (:func:`with_points`), as the React charts do.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, cast

import altair as alt

from eqd_desk.app.ui import theme
from eqd_desk.app.ui.charts import (
    SHORT_HEIGHT,
    SPOT_AXIS_FORMAT,
    Series,
    bar_chart,
    dual_axis_chart,
    line_chart,
)
from eqd_desk.app.ui.format import fmt_money, fmt_pct, js_number
from eqd_desk.app.ui.sim_session import CumAttribution, HistPoint
from eqd_desk.app.ui.simulator_display import attribution_bars, history_frame

MONEY_AXIS: Final = ",.2~f"
"""d3 format of the two money axes (P&L over time, P&L explain): grouped, at most 2
decimals, trailing zeros dropped, so a flat, all-zero series at the seed reads ``0``, not
``0.000000``.

React prints them ``fmtNum(v, 3)`` and ``fmtNum(v, 2)`` (the same numbers, ungrouped). The
shared line chart's default y format is the first, but the shared bar chart has no tick
format and there is no ``fmtNum(v, 2)`` axis format, so both axes use this one: two stacked
P&L charts must not print ``20000`` above ``20,000``."""

DAY_FORMAT: Final = "d"
"""d3 format of the day axis (whole days; ticks are at least one day apart)."""

POINT_SIZES: Final = (90, 30)
"""Areas (px²) of the dots that mark a one-point path, line by line: the first line's dot is
larger, so where two lines' single points coincide (spot and vol at day 0 each sit in the
middle of their own axis) both colours stay visible, one ringing the other."""


def with_points(chart: alt.LayerChart) -> alt.LayerChart:
    """A copy of ``chart`` whose lines also draw a dot at every data point, in the line's
    colour (sizes :data:`POINT_SIZES`): a path of one point (day 0) is otherwise
    invisible."""
    out = chart.copy(deep=True)
    lines = 0
    for layer in out.layer:
        mark = getattr(layer, "mark", None)
        if isinstance(mark, alt.MarkDef) and mark.type == "line":
            size = POINT_SIZES[min(lines, len(POINT_SIZES) - 1)]
            mark.point = alt.OverlayMarkDef(filled=True, size=size)
            lines += 1
    return out


def _dotted_if_single(chart: alt.LayerChart, history: Sequence[HistPoint]) -> alt.LayerChart:
    return with_points(chart) if len(history) < 2 else chart


def _day_axis(chart: alt.LayerChart) -> alt.LayerChart:
    """Whole-day ticks on the x axis (no ``0.5`` days on a short session)."""
    return cast("alt.LayerChart", chart.configure_axisX(format=DAY_FORMAT, tickMinStep=1))


def day_text(day: float) -> str:
    """Tooltip x value: ``"Day 12"``."""
    return f"Day {js_number(day)}"


def pnl_chart(history: Sequence[HistPoint], currency: str) -> alt.LayerChart:
    """Mark-to-market P&L of the book against the session day (zero line included), in
    :data:`MONEY_AXIS` ticks; the tooltip reads ``Day n`` and money. A one-point history
    (day 0) is drawn as a dot."""
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
    return _day_axis(_dotted_if_single(chart, history))


def explain_chart(cum: CumAttribution, currency: str) -> alt.LayerChart:
    """The cumulative P&L explain: delta, gamma, theta, vega, vanna, volga, residual."""
    labels, values = attribution_bars(cum)
    chart = bar_chart(labels, values, y_title=f"P&L ({currency})", height=SHORT_HEIGHT)
    return cast("alt.LayerChart", chart.configure_axisY(format=MONEY_AXIS))


def path_chart(history: Sequence[HistPoint]) -> alt.LayerChart:
    """Spot (left axis, index points) and ATM implied vol (right axis) by day; at day 0, a
    dot for each."""
    chart = dual_axis_chart(
        history_frame(history),
        x="day",
        left=Series("spot", "Spot", color=theme.LINE),
        right=Series("vol", "ATM vol", color=theme.PUT, width=1.5),
        x_title="Day",
        left_title="Spot",
        right_title="ATM implied vol",
        left_format=SPOT_AXIS_FORMAT,
        right_format=".1%",
        x_tooltip=day_text,
        left_tooltip=fmt_money,
        right_tooltip=fmt_pct,
        height=SHORT_HEIGHT,
    )
    return _day_axis(_dotted_if_single(chart, history))


__all__ = [
    "DAY_FORMAT",
    "MONEY_AXIS",
    "POINT_SIZES",
    "day_text",
    "explain_chart",
    "path_chart",
    "pnl_chart",
    "with_points",
]
