"""The greeks lab's two charts (port of ``web/src/components/PlotsPanel.tsx``), built on the
shared :mod:`eqd_desk.app.ui.charts` look.

1. :func:`greek_chart`: the selected greek (or the price) swept against spot, vol or time,
   with the current level (accent dashed) and, against spot, the strike (dotted).
2. :func:`payoff_chart`: the value at expiry (intrinsic, solid) against the value now
   (premium, thin accent); the gap is time value.

Pure builders (data in, Altair chart out). Axis ticks, hover labels and hover values read as
the React charts do: the y ticks use ``fmtNum(v, 3)`` (so a delta axis reads ``0.250``,
``0.500`` … and a speed axis ``1.20e-6``), the hover prints ``fmtNum(v)``.
"""

from __future__ import annotations

from functools import partial
from typing import Final

import altair as alt
import pandas as pd

from eqd_desk.app.ui import charts, theme
from eqd_desk.app.ui.charts import Series, VRule
from eqd_desk.app.ui.greeks_lab_curves import (
    X_AXIS_FORMATS,
    X_AXIS_LABELS,
    current_x,
    x_tick,
)
from eqd_desk.content import GreekKey
from eqd_desk.content.greeks import XAxisKey
from eqd_desk.engine import GREEK_UNITS, BsmInputs

FMT_NUM_3_LABEL_EXPR: Final = (
    "datum.value == 0 ? '0' : "
    "(abs(datum.value) >= 1e7 || abs(datum.value) < 1e-4) ? format(datum.value, '.2e') : "
    "format(datum.value, "
    "'.' + clamp(3 - (floor(log(abs(datum.value)) / LN10) + 1), 0, 8) + 'f')"
)
"""Vega expression printing an axis tick like ``format.ts`` ``fmtNum(v, 3)`` (the React
y-axis ``tickFormatter``): ``0``; two-decimal exponent outside 1e-4 … 1e7; otherwise
``3 − integer digits`` decimals, clamped to 0 … 8."""

GREEK_CHART_HEIGHT: Final = charts.TALL_HEIGHT
"""Height of the greek-sweep chart (px): the hero chart of the centre column, as in React."""
PAYOFF_CHART_HEIGHT: Final = 250
"""Height of the payoff chart (px)."""


def with_fmt_num_y_ticks(chart: alt.LayerChart) -> alt.LayerChart:
    """``chart`` with its y-axis ticks printed by :data:`FMT_NUM_3_LABEL_EXPR`."""
    styled: alt.LayerChart = chart.configure_axisY(labelExpr=FMT_NUM_3_LABEL_EXPR)
    return styled


def greek_axis_title(greek: GreekKey, currency: str) -> str:
    """The y-axis title: the greek with its desk unit (``"Vega (per 1 vol pt)"``); the price
    is in currency units (``"Price (USD)"``)."""
    unit = GREEK_UNITS[greek]
    return f"{unit.label} ({currency if greek == 'price' else unit.unit})"


def greek_chart_title(greek: GreekKey, x_axis: XAxisKey) -> tuple[str, str]:
    """The panel title as (greek label, lower-cased x label): ``("Delta", "spot")`` reads
    "Delta vs spot" (``PlotsPanel.tsx``)."""
    return GREEK_UNITS[greek].label, X_AXIS_LABELS[x_axis].lower()


def greek_rules(inputs: BsmInputs, x_axis: XAxisKey) -> list[VRule]:
    """Reference lines of the greek chart: the current level of the swept variable, plus the
    strike when sweeping spot."""
    rules = [VRule(current_x(inputs, x_axis), "current")]
    if x_axis == "S":
        rules.append(VRule(inputs.K, "strike"))
    return rules


def greek_chart(
    sweep: pd.DataFrame,
    greek: GreekKey,
    x_axis: XAxisKey,
    *,
    inputs: BsmInputs,
    currency: str,
    height: int = GREEK_CHART_HEIGHT,
) -> alt.LayerChart:
    """The selected greek against the swept variable.

    Args:
        sweep: :func:`~eqd_desk.app.ui.greeks_lab_curves.greek_sweep` output (column ``x``
            and one column per greek).
        greek: the column to plot.
        x_axis: what ``x`` is (spot, vol or time).
        inputs: the current option (for the reference lines).
        currency: premium currency (for the price's axis title).
        height: plot height in px.
    """
    chart = charts.line_chart(
        sweep,
        x="x",
        series=Series(greek, GREEK_UNITS[greek].label),
        x_title=X_AXIS_LABELS[x_axis],
        y_title=greek_axis_title(greek, currency),
        x_format=X_AXIS_FORMATS[x_axis],
        x_tooltip=partial(x_tick, x_axis),
        vrules=greek_rules(inputs, x_axis),
        height=height,
    )
    return with_fmt_num_y_ticks(chart)


def payoff_chart(
    curve: pd.DataFrame,
    *,
    inputs: BsmInputs,
    currency: str,
    height: int = PAYOFF_CHART_HEIGHT,
) -> alt.LayerChart:
    """Value at expiry (solid line colour, 2 px) against the value now (accent, 1.5 px), with
    the current spot (dashed), the strike (dotted) and the zero line.

    Args:
        curve: :func:`~eqd_desk.app.ui.greeks_lab_curves.payoff_curve` output.
        inputs: the current option (for the reference lines).
        currency: premium currency (y-axis title).
        height: plot height in px.
    """
    chart = charts.line_chart(
        curve,
        x="spot",
        series=[
            Series("now", "Now", color=theme.ACCENT, width=1.5),
            Series("expiry", "At expiry", color=theme.LINE, width=2.0),
        ],
        x_title="Spot",
        y_title=f"Value ({currency})",
        x_format=X_AXIS_FORMATS["S"],
        x_tooltip=partial(x_tick, "S"),
        vrules=[VRule(inputs.S, "current"), VRule(inputs.K, "strike")],
        zero_rule=True,
        height=height,
    )
    return with_fmt_num_y_ticks(chart)
