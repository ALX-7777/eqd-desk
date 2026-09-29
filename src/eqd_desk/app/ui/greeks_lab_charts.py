"""The greeks lab's charts (port of ``web/src/components/PlotsPanel.tsx``), built on the
shared :mod:`eqd_desk.app.ui.charts` look.

1. :func:`greek_chart`: the selected greek (or the price) swept against spot, vol or time,
   with the current level (accent dashed) and, against spot, the strike (dotted).
2. The payoff at expiry is the shared :func:`eqd_desk.app.ui.charts.payoff_chart` (value at
   expiry, solid, against the premium now, thin accent; the gap is time value), drawn
   :data:`PAYOFF_CHART_HEIGHT` tall.

Pure builders (data in, Altair chart out). Axis ticks, hover labels and hover values read as
the React charts do (the shared :func:`~eqd_desk.app.ui.charts.line_chart` defaults): the y
ticks use ``fmtNum(v, 3)`` (so a delta axis reads ``0.250``, ``0.500`` … and a speed axis
``1.20e-6``), the hover prints ``fmtNum(v)``.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from types import MappingProxyType
from typing import Final

import altair as alt
import pandas as pd

from eqd_desk.app.ui import charts
from eqd_desk.app.ui.charts import Series, VRule
from eqd_desk.app.ui.greeks_lab_curves import (
    X_AXIS_FORMATS,
    X_AXIS_LABELS,
    current_x,
    x_tick,
)
from eqd_desk.app.ui.units import axis_title
from eqd_desk.content import GreekKey
from eqd_desk.content.greeks import XAxisKey
from eqd_desk.engine import GREEK_UNITS, BsmInputs

GREEK_CHART_HEIGHT: Final = charts.TALL_HEIGHT
"""Height of the greek-sweep chart (px): the hero chart of the centre column, as in React."""
PAYOFF_CHART_HEIGHT: Final = 250
"""Height of the payoff chart (px)."""

GREEK_CHART_PADDING: Final[Mapping[str, int]] = MappingProxyType({"top": 10, "bottom": 20})
"""Top-level Vega padding of the greek chart (px; a missing side is 0).

``st.altair_chart`` gives every spec without a top-level ``padding`` the padding
``{"bottom": 20}``, which overrides the shared ``config.padding``: the plot then starts at
the very top of the canvas, and the top y tick label, centred on that edge, relies on
Vega's autosize to make room for it. After some changes of greek or x axis (vanna or volga
against vol) Vega sizes the plot from stale label bounds and the label ends up half above
the canvas, clipped. Ten pixels on top keep it whole in that worst case (a label centred on
the canvas edge overhangs it by about 6.5 px); the bottom keeps Streamlit's 20."""


def greek_axis_title(greek: GreekKey, currency: str) -> str:
    """The y-axis title: the greek with its desk unit (``"Vega (per 1 vol pt)"``); the price
    is in currency units (``"Price (USD)"``). The shared
    :func:`~eqd_desk.app.ui.units.axis_title`."""
    return axis_title(greek, currency)


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

    The chart carries :data:`GREEK_CHART_PADDING`, so its top tick label is never clipped.
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
    return chart.properties(padding=dict(GREEK_CHART_PADDING))


__all__ = [
    "GREEK_CHART_HEIGHT",
    "GREEK_CHART_PADDING",
    "PAYOFF_CHART_HEIGHT",
    "greek_axis_title",
    "greek_chart",
    "greek_chart_title",
    "greek_rules",
]
