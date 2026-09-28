"""Altair chart builders with ONE dark-terminal look, shared by every page.

Every builder is pure (data in, ``alt.Chart`` out) so its spec is unit-testable; render with
:func:`show_chart`, the only function here that touches Streamlit. The look mirrors the React
charts (``web/src/components/chartTheme.ts`` + ``PlotsPanel.tsx``): transparent background,
dashed grid, mono axis labels, crisp 2 px curves, no animation, and the same reference-line
vocabulary:

========== ===================== ==========================================================
style      look                  used for
========== ===================== ==========================================================
current    accent, dashed 4-3    the current level (spot / vol / tenor / day)
strike     dim, dotted 1-4       strikes
barrier    red, dashed 5-3       a barrier ``H`` (labelled)
forward    accent, dashed 4-3    the forward ``F`` (labelled)
autocall   accent, dashed 5-3    autocall trigger level (labelled)
coupon     orange, dashed 4-4    coupon barrier (labelled)
protection red, dashed 5-3       capital-protection barrier (labelled)
marker     dim, dashed 2-4       anything else
========== ===================== ==========================================================

Hovering any line chart shows a crosshair and a tooltip with every series at that x, the
values formatted by :mod:`eqd_desk.app.ui.format` (so a tooltip prints exactly what the React
app prints).

Typical use::

    from eqd_desk.app.ui import charts
    from eqd_desk.app.ui.charts import Series, VRule

    xs = charts.sweep_x(0.6 * spot, 1.4 * spot, 100)
    df = pd.DataFrame({"S": xs, "delta": [...]})
    chart = charts.line_chart(
        df,
        x="S",
        series=Series("delta", "Delta"),
        x_title="Spot",
        y_title="Delta (per $1 spot)",
        vrules=[VRule(inputs.S, "current"), VRule(inputs.K, "strike")],
    )
    charts.show_chart(chart, key="lab.greek_chart")
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal, cast

import altair as alt
import pandas as pd

from eqd_desk.app.ui import theme
from eqd_desk.app.ui.format import fmt_money, fmt_num

DEFAULT_HEIGHT: Final = 320
"""Main chart height in px (React ``.chart-wrap``)."""
SHORT_HEIGHT: Final = 210
"""Secondary chart height in px (React ``.chart-wrap.short``)."""
TALL_HEIGHT: Final = 420
"""Hero chart height in px (the exotics' characteristic charts)."""

TickFormatter = Callable[[float], str]
"""Formats a number for a tooltip (a :mod:`~eqd_desk.app.ui.format` function)."""

RuleStyle = Literal[
    "current", "strike", "barrier", "forward", "autocall", "coupon", "protection", "marker"
]
"""Named reference-line look (see the module docstring)."""


@dataclass(frozen=True, slots=True)
class RuleLook:
    """Stroke of a reference line."""

    color: str
    dash: tuple[int, ...]
    """Vega ``strokeDash`` (dash, gap, …); empty = solid."""


RULE_STYLES: Final[Mapping[RuleStyle, RuleLook]] = MappingProxyType(
    {
        "current": RuleLook(theme.ACCENT, (4, 3)),
        "strike": RuleLook(theme.TEXT_DIM, (1, 4)),
        "barrier": RuleLook(theme.NEG, (5, 3)),
        "forward": RuleLook(theme.ACCENT, (4, 3)),
        "autocall": RuleLook(theme.ACCENT, (5, 3)),
        "coupon": RuleLook(theme.PUT, (4, 4)),
        "protection": RuleLook(theme.NEG, (5, 3)),
        "marker": RuleLook(theme.TEXT_DIM, (2, 4)),
    }
)
"""Stroke of each :data:`RuleStyle`, mirroring the React ``ReferenceLine`` props."""


@dataclass(frozen=True, slots=True)
class VRule:
    """A vertical reference line at ``x`` (optionally labelled at the top of the plot)."""

    x: float
    style: RuleStyle = "current"
    label: str | None = None


@dataclass(frozen=True, slots=True)
class HRule:
    """A horizontal reference line at ``y``, optionally labelled at the right edge, just
    above (``"above"``) or below (``"below"``) the line."""

    y: float
    style: RuleStyle = "current"
    label: str | None = None
    label_position: Literal["above", "below"] = "above"


@dataclass(frozen=True, slots=True)
class Series:
    """One curve of a line chart: which column of the (wide) DataFrame, and how to draw it."""

    column: str
    """Column holding the y values."""
    label: str
    """Legend and tooltip name (must be unique within a chart)."""
    color: str = theme.LINE
    width: float = 2.0
    """Stroke width in px (React: 2 for the main curve, 1.5 for a secondary one)."""
    dash: tuple[int, ...] = ()
    """``strokeDash``; empty = solid."""
    opacity: float = 1.0
    fill: str | None = None
    """If set, also fill the area between the curve and y = 0 with this colour (e.g.
    :data:`~eqd_desk.app.ui.theme.ACCENT_DIM`)."""


# ------------------------------------------------------------------ pure helpers


def sweep_x(lo: float, hi: float, n: int) -> list[float]:
    """``n + 1`` evenly spaced points from ``lo`` to ``hi`` inclusive, computed EXACTLY as the
    React sweeps do (``lo + ((hi - lo) * i) / N``), so each x, and every engine value
    evaluated at it, is bit-identical to the React app's.

    Raises:
        ValueError: if ``n < 1``.
    """
    if n < 1:
        raise ValueError(f"sweep_x: n must be >= 1 (got {n})")
    return [lo + ((hi - lo) * i) / n for i in range(n + 1)]


def _solid(dash: Sequence[int]) -> list[int]:
    """Vega needs a non-empty dash array in a scale range; ``[1, 0]`` draws a solid line."""
    return list(dash) if dash else [1, 0]


def _as_series(series: Series | Sequence[Series]) -> tuple[Series, ...]:
    out = (series,) if isinstance(series, Series) else tuple(series)
    if not out:
        raise ValueError("chart needs at least one series")
    labels = [s.label for s in out]
    if len(set(labels)) != len(labels):
        raise ValueError(f"series labels must be unique, got {labels}")
    return out


def _finite_range(values: pd.Series) -> tuple[float, float] | None:
    """(min, max) of the finite values, or None if there are none."""
    finite = values[pd.to_numeric(values, errors="coerce").map(math.isfinite)]
    if finite.empty:
        return None
    return float(finite.min()), float(finite.max())


def style_chart[C: alt.TopLevelMixin](chart: C) -> C:
    """Apply the terminal look (top-level ``config``) to any Altair chart.

    Builders call it last; use it for a hand-built chart so it matches the rest of the app.
    The result can no longer be layered (Vega-Lite only allows ``config`` at the top level).
    """
    styled = (
        chart.configure(
            background="transparent",
            font=theme.SANS_FONT,
            padding={"left": 2, "right": 10, "top": 6, "bottom": 2},
        )
        .configure_view(stroke=None)
        .configure_axis(
            domainColor=theme.AXIS,
            tickColor=theme.AXIS,
            gridColor=theme.GRID,
            gridDash=[2, 4],
            labelColor=theme.TEXT_DIM,
            labelFont=theme.MONO_FONT,
            labelFontSize=11,
            titleColor=theme.TEXT_DIM,
            titleFont=theme.SANS_FONT,
            titleFontSize=11,
            titleFontWeight="normal",
            titlePadding=8,
        )
        .configure_legend(
            labelColor=theme.TEXT,
            labelFont=theme.SANS_FONT,
            labelFontSize=11,
            symbolStrokeWidth=2,
            symbolSize=160,
            orient="top",
            direction="horizontal",
            title=None,
            padding=0,
            offset=6,
        )
        .configure_text(font=theme.MONO_FONT)
    )
    return cast("C", styled)


def _vrule_layers(rules: Sequence[VRule]) -> list[alt.Chart]:
    layers: list[alt.Chart] = []
    for r in rules:
        if not math.isfinite(r.x):
            continue
        look = RULE_STYLES[r.style]
        df = pd.DataFrame({"x": [r.x], "label": [r.label or ""]})
        layers.append(
            alt.Chart(df)
            .mark_rule(color=look.color, strokeDash=_solid(look.dash), strokeWidth=1, clip=True)
            .encode(x=alt.X("x:Q"))
        )
        if r.label:
            layers.append(
                alt.Chart(df)
                .mark_text(
                    color=look.color,
                    align="left",
                    baseline="top",
                    dx=4,
                    dy=2,
                    fontSize=10,
                    clip=True,
                )
                .encode(x=alt.X("x:Q"), y=alt.value(0), text=alt.Text("label:N"))
            )
    return layers


def _hrule_layers(rules: Sequence[HRule]) -> list[alt.Chart]:
    layers: list[alt.Chart] = []
    for r in rules:
        if not math.isfinite(r.y):
            continue
        look = RULE_STYLES[r.style]
        df = pd.DataFrame({"y": [r.y], "label": [r.label or ""]})
        layers.append(
            alt.Chart(df)
            .mark_rule(color=look.color, strokeDash=_solid(look.dash), strokeWidth=1, clip=True)
            .encode(y=alt.Y("y:Q"))
        )
        if r.label:
            above = r.label_position == "above"
            layers.append(
                alt.Chart(df)
                .mark_text(
                    color=look.color,
                    align="right",
                    baseline="bottom" if above else "top",
                    dx=-4,
                    dy=-3 if above else 3,
                    fontSize=10,
                    clip=True,
                )
                .encode(x=alt.value("width"), y=alt.Y("y:Q"), text=alt.Text("label:N"))
            )
    return layers


def _zero_layer() -> alt.Chart:
    rule: alt.Chart = (
        alt.Chart(pd.DataFrame({"y": [0.0]}))
        .mark_rule(color=theme.AXIS, strokeWidth=1, clip=True)
        .encode(y=alt.Y("y:Q"))
    )
    return rule


def _finish(
    layers: Sequence[alt.Chart], height: int, *, independent_y: bool = False
) -> alt.LayerChart:
    """Layer, size and style: the last step of every builder."""
    chart = alt.LayerChart(layer=list(layers))
    if independent_y:
        chart = chart.resolve_scale(y="independent")
    return style_chart(chart.properties(height=height, width="container"))


# ------------------------------------------------------------------ builders


def line_chart(
    data: pd.DataFrame,
    *,
    x: str,
    series: Series | Sequence[Series],
    x_title: str,
    y_title: str,
    x_format: str | None = None,
    y_format: str | None = None,
    x_tooltip: TickFormatter = fmt_num,
    y_tooltip: TickFormatter = fmt_num,
    vrules: Sequence[VRule] = (),
    hrules: Sequence[HRule] = (),
    zero_rule: bool = True,
    y_zero: bool = True,
    y_domain: tuple[float, float] | None = None,
    legend: bool | None = None,
    crosshair: bool = True,
    height: int = DEFAULT_HEIGHT,
) -> alt.LayerChart:
    """One or more curves against a shared x, with reference lines and a hover crosshair.

    Args:
        data: WIDE frame: column ``x`` plus one column per :class:`Series`.
        x: name of the x column (spot, vol, T, day …). The x axis spans exactly its min…max
            (no padding, no forced zero), like Recharts ``domain={['dataMin','dataMax']}``.
        series: the curves, drawn in order (the last one on top).
        x_title, y_title: axis titles; ``y_title`` should carry the unit
            (use :data:`eqd_desk.engine.GREEK_UNITS`).
        x_format, y_format: d3-format strings for the axis ticks (e.g. ``".0%"`` for a vol
            axis, ``",.0f"`` for levels); ``None`` = Vega's adaptive default.
        x_tooltip, y_tooltip: formatters for the hover tooltip (default
            :func:`~eqd_desk.app.ui.format.fmt_num`, the React tooltip format).
        vrules, hrules: reference lines (:class:`VRule` / :class:`HRule`).
        zero_rule: draw the y = 0 axis line (only when 0 is inside the y range, like a
            Recharts ``ReferenceLine y={0}``).
        y_zero: include 0 in the y domain (Recharts' default ``[0, 'auto']``); set False for
            level-type data (spot paths, a vol smile).
        y_domain: fix the y domain instead.
        legend: show a legend; default = only when there are several series.
        crosshair: hover rule + points + tooltip with every series at that x.
        height: plot height in px (width stretches to the container).
    """
    specs = _as_series(series)
    labels = [s.label for s in specs]
    cols = [s.column for s in specs]
    wide = pd.DataFrame({"x": pd.to_numeric(data[x], errors="coerce").astype(float)})
    for i, s in enumerate(specs):
        wide[f"s{i}"] = pd.to_numeric(data[s.column], errors="coerce").astype(float).to_numpy()
    x_range = _finite_range(wide["x"])
    if x_range is None:
        raise ValueError(f"line_chart: column {x!r} has no finite values")

    long = wide.melt(id_vars=["x"], value_vars=[f"s{i}" for i in range(len(cols))], var_name="k")
    long["series"] = long["k"].map({f"s{i}": lab for i, lab in enumerate(labels)})
    long = long.drop(columns="k").rename(columns={"value": "y"})
    y_range = _finite_range(long["y"])

    show_legend = len(specs) > 1 if legend is None else legend
    x_enc = alt.X(
        "x:Q",
        title=x_title,
        scale=alt.Scale(domain=list(x_range), nice=False, zero=False),
        axis=alt.Axis(format=x_format) if x_format else alt.Axis(),
    )
    y_scale = (
        alt.Scale(domain=list(y_domain), nice=False, zero=False)
        if y_domain is not None
        else alt.Scale(zero=y_zero, nice=True)
    )
    y_enc = alt.Y(
        "y:Q",
        title=y_title,
        scale=y_scale,
        axis=alt.Axis(format=y_format) if y_format else alt.Axis(),
    )
    color_scale = alt.Scale(domain=labels, range=[s.color for s in specs])
    color_enc = alt.Color(
        "series:N",
        scale=color_scale,
        legend=alt.Legend(symbolType="stroke") if show_legend else None,
        sort=labels,
    )
    # One layer per series with fixed stroke properties; the shared colour scale gives the
    # legend. (Encoding width/opacity from a nominal field makes Vega-Lite warn.)
    lines = [
        alt.Chart(long[long["series"] == s.label])
        .mark_line(
            interpolate="monotone",
            strokeWidth=s.width,
            strokeDash=_solid(s.dash),
            opacity=s.opacity,
            clip=True,
        )
        .encode(x=x_enc, y=y_enc, color=color_enc)
        for s in specs
    ]

    layers: list[alt.Chart] = []
    for i, s in enumerate(specs):
        if s.fill is not None:
            layers.append(
                alt.Chart(wide)
                .mark_area(color=s.fill, interpolate="monotone", clip=True)
                .encode(x=alt.X("x:Q"), y=alt.Y(f"s{i}:Q"))
            )
    if zero_rule and y_range is not None and (y_zero or y_range[0] <= 0 <= y_range[1]):
        layers.append(_zero_layer())
    layers.extend(_hrule_layers(hrules))
    layers.extend(_vrule_layers(vrules))
    layers.extend(lines)

    if crosshair:
        text = pd.DataFrame({"x": wide["x"], "x_text": wide["x"].map(x_tooltip)})
        for i in range(len(specs)):
            text[f"t{i}"] = wide[f"s{i}"].map(y_tooltip)
        hover = alt.selection_point(
            name="hover", fields=["x"], nearest=True, on="pointerover", empty=False
        )
        tooltip = [alt.Tooltip("x_text:N", title=x_title)] + [
            alt.Tooltip(f"t{i}:N", title=s.label) for i, s in enumerate(specs)
        ]
        layers.append(
            alt.Chart(text)
            .mark_rule(color=theme.TEXT_DIM, strokeWidth=1)
            .encode(
                x=alt.X("x:Q"),
                opacity=alt.when(hover).then(alt.value(0.5)).otherwise(alt.value(0.0)),
                tooltip=tooltip,
            )
            .add_params(hover)
        )
        layers.append(
            alt.Chart(long)
            .mark_point(filled=True, size=40, clip=True)
            .encode(
                x=alt.X("x:Q"),
                y=alt.Y("y:Q"),
                color=color_enc,
                opacity=alt.when(hover).then(alt.value(1.0)).otherwise(alt.value(0.0)),
            )
        )

    return _finish(layers, height)


def payoff_chart(
    spots: Sequence[float],
    expiry: Sequence[float],
    now: Sequence[float],
    *,
    spot: float,
    strikes: Sequence[float] = (),
    expiry_label: str = "At expiry",
    now_label: str = "Now",
    x_title: str = "Spot",
    y_title: str = "Value",
    height: int = SHORT_HEIGHT,
) -> alt.LayerChart:
    """Payoff at expiry (solid line colour, 2 px) against the value now (thin accent, 1.5 px),
    with the current spot (dashed accent), the strikes (dotted) and the zero line.

    The React convention: the gap between the two curves is time value (single option) or the
    mark-to-market vs expiry P&L (a structure). Pass P&L arrays and ``y_title="P&L"`` for a
    strategy; values and ``y_title="Value"`` for a single option.
    """
    df = pd.DataFrame({"spot": list(spots), "now": list(now), "expiry": list(expiry)})
    return line_chart(
        df,
        x="spot",
        series=[
            Series("now", now_label, color=theme.ACCENT, width=1.5),
            Series("expiry", expiry_label, color=theme.LINE, width=2.0),
        ],
        x_title=x_title,
        y_title=y_title,
        vrules=[VRule(spot, "current"), *(VRule(k, "strike") for k in dict.fromkeys(strikes))],
        zero_rule=True,
        height=height,
    )


def bar_chart(
    labels: Sequence[str],
    values: Sequence[float],
    *,
    y_title: str,
    x_title: str | None = None,
    value_tooltip: TickFormatter = fmt_money,
    height: int = SHORT_HEIGHT,
) -> alt.LayerChart:
    """Signed bars in the given order, green for ``>= 0`` and red below (the P&L explain),
    with the zero line. The tooltip prints :func:`~eqd_desk.app.ui.format.fmt_money`."""
    if len(labels) != len(values):
        raise ValueError("bar_chart: labels and values differ in length")
    order = list(labels)
    df = pd.DataFrame(
        {
            "label": order,
            "value": [float(v) for v in values],
            "text": [value_tooltip(float(v)) for v in values],
            "tone": ["pos" if float(v) >= 0 else "neg" for v in values],
        }
    )
    bars = (
        alt.Chart(df)
        # No clip=True here: Vega-Lite drops rounded (cornerRadiusEnd) bars that are clipped.
        .mark_bar(cornerRadiusEnd=2)
        .encode(
            x=alt.X(
                "label:N",
                sort=order,
                title=x_title,
                axis=alt.Axis(
                    labelAngle=0, labelFont=theme.SANS_FONT, labelFontSize=10, grid=False
                ),
            ),
            y=alt.Y("value:Q", title=y_title, scale=alt.Scale(zero=True, nice=True)),
            color=alt.Color(
                "tone:N",
                scale=alt.Scale(domain=["pos", "neg"], range=[theme.POS, theme.NEG]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("label:N", title="Term"),
                alt.Tooltip("text:N", title=y_title),
            ],
        )
    )
    return _finish([_zero_layer(), bars], height)


def dual_axis_chart(
    data: pd.DataFrame,
    *,
    x: str,
    left: Series,
    right: Series,
    x_title: str,
    left_title: str,
    right_title: str,
    left_format: str | None = None,
    right_format: str | None = None,
    x_tooltip: TickFormatter = fmt_num,
    left_tooltip: TickFormatter = fmt_num,
    right_tooltip: TickFormatter = fmt_num,
    left_zero: bool = False,
    right_zero: bool = False,
    height: int = SHORT_HEIGHT,
) -> alt.LayerChart:
    """Two series on independent y axes (left and right) against a shared x: the simulator's
    spot & implied-vol path. Hover shows both values."""
    wide = pd.DataFrame(
        {
            "x": pd.to_numeric(data[x], errors="coerce").astype(float),
            "l": pd.to_numeric(data[left.column], errors="coerce").astype(float).to_numpy(),
            "r": pd.to_numeric(data[right.column], errors="coerce").astype(float).to_numpy(),
        }
    )
    x_range = _finite_range(wide["x"])
    if x_range is None:
        raise ValueError(f"dual_axis_chart: column {x!r} has no finite values")
    wide["x_text"] = wide["x"].map(x_tooltip)
    wide["l_text"] = wide["l"].map(left_tooltip)
    wide["r_text"] = wide["r"].map(right_tooltip)
    x_enc = alt.X(
        "x:Q", title=x_title, scale=alt.Scale(domain=list(x_range), nice=False, zero=False)
    )
    color = alt.Color(
        "name:N",
        scale=alt.Scale(domain=[left.label, right.label], range=[left.color, right.color]),
        legend=alt.Legend(symbolType="stroke"),
        sort=[left.label, right.label],
    )

    def side(
        col: str,
        spec: Series,
        title: str,
        fmt: str | None,
        zero: bool,
        orient: Literal["left", "right"],
    ) -> alt.Chart:
        axis = alt.Axis(orient=orient, grid=orient == "left")
        if fmt:
            axis = alt.Axis(orient=orient, grid=orient == "left", format=fmt)
        line: alt.Chart = (
            alt.Chart(wide.assign(name=spec.label))
            .mark_line(
                interpolate="monotone",
                strokeWidth=spec.width,
                strokeDash=_solid(spec.dash),
                opacity=spec.opacity,
                clip=True,
            )
            .encode(
                x=x_enc,
                y=alt.Y(f"{col}:Q", title=title, scale=alt.Scale(zero=zero, nice=True), axis=axis),
                color=color,
            )
        )
        return line

    hover = alt.selection_point(
        name="hover", fields=["x"], nearest=True, on="pointerover", empty=False
    )
    crosshair = (
        alt.Chart(wide)
        .mark_rule(color=theme.TEXT_DIM, strokeWidth=1)
        .encode(
            x=alt.X("x:Q"),
            opacity=alt.when(hover).then(alt.value(0.5)).otherwise(alt.value(0.0)),
            tooltip=[
                alt.Tooltip("x_text:N", title=x_title),
                alt.Tooltip("l_text:N", title=left.label),
                alt.Tooltip("r_text:N", title=right.label),
            ],
        )
        .add_params(hover)
    )
    return _finish(
        [
            side("l", left, left_title, left_format, left_zero, "left"),
            side("r", right, right_title, right_format, right_zero, "right"),
            crosshair,
        ],
        height,
        independent_y=True,
    )


# ------------------------------------------------------------------ rendering


def show_chart(chart: Any, *, key: str | None = None) -> None:
    """Render a chart built here: full container width, and ``theme=None`` so our terminal
    config is used instead of Streamlit's chart theme."""
    import streamlit as st

    st.altair_chart(chart, theme=None, width="stretch", key=key)
