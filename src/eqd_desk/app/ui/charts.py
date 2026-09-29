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

Axes read like the React ones by default: the y ticks print ``fmtNum(v, 3)``
(:data:`FMT_NUM_3`, the React ``tickFormatter`` of every greek / P&L chart; Vega's adaptive
format where three significant figures cannot tell the ticks apart), and the x axis
is tidied (:data:`X_TICK_COUNT` ticks, labels thinned so they never collide, an end label
that would be cut off hidden) so dense mono labels stay legible at any chart width.

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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal, cast

import altair as alt
import pandas as pd

from eqd_desk.app.ui import theme
from eqd_desk.app.ui.format import fmt_level, fmt_money, fmt_num

DEFAULT_HEIGHT: Final = 320
"""Main chart height in px (React ``.chart-wrap``)."""
SHORT_HEIGHT: Final = 210
"""Secondary chart height in px (React ``.chart-wrap.short``)."""
MEDIUM_HEIGHT: Final = 250
"""Between short and default, in px (React VarSwapView's strip, ``style={{ height: 250 }}``):
a companion chart that needs a little more room than a short one."""
TALL_HEIGHT: Final = 420
"""Hero chart height in px (the exotics' characteristic charts)."""

TickFormatter = Callable[[float], str]
"""Formats a number for a tooltip (a :mod:`~eqd_desk.app.ui.format` function)."""

# ------------------------------------------------------------------ axis formats

FMT_NUM_3: Final = "fmtNum3"
"""Axis-format name (not a d3 format): print the ticks like ``format.ts`` ``fmtNum(v, 3)``,
the React y-axis ``tickFormatter`` (a delta axis reads ``0.250``, ``0.500``; a gamma axis
``0.000700``; a speed axis ``1.20e-6``). The default y format of :func:`line_chart`."""

FMT_NUM_3_LABEL_EXPR: Final = (
    "datum.value == 0 ? '0' : "
    "(abs(datum.value) >= 1e7 || abs(datum.value) < 1e-4) ? format(datum.value, '.2e') : "
    "format(datum.value, "
    "'.' + clamp(3 - (floor(log(abs(datum.value)) / LN10) + 1), 0, 8) + 'f')"
)
"""Vega expression behind :data:`FMT_NUM_3`: ``0``; two-decimal exponent outside
1e-4 … 1e7; otherwise ``3 − integer digits`` decimals, clamped to 0 … 8."""

SPOT_AXIS_FORMAT: Final = ",.0f"
"""d3 format of an index-level axis (spot, strike): whole points with a thousands separator
(``6,300``)."""

X_TICK_COUNT: Final = 8
"""Tick-count hint of every x axis. Without it Vega aims at one tick per 40 px and picks,
e.g., a 200-point step on a 70 %–130 % spot axis, whose grouped mono labels then collide."""
X_LABEL_GAP_PX: Final = 6
"""Minimum gap between neighbouring x tick labels; closer ones are thinned out (every other
label is dropped until they fit)."""
X_LABEL_BOUND_PX: Final = 8
"""Pixels by which an x tick label may spill past either end of the axis before it is
hidden rather than cut in half (the chart's right padding is 10 px, so a kept label is never
clipped). A label exactly at an end (0 on a time axis) is aligned inside the plot instead."""


def fmt_num_3_step(value: float) -> float:
    """The smallest difference ``fmtNum(v, 3)`` shows at the magnitude of ``value``: three
    significant figures (``53.1`` → 0.1, ``0.0007`` → 1e-6), clamped to 8 decimals like
    ``fmtNum``; 0 for ``value == 0``."""
    a = abs(value)
    if a == 0 or not math.isfinite(a):
        return 0.0
    exponent = math.floor(math.log10(a))
    if a >= 1e7 or a < 1e-4:
        return float(10.0 ** (exponent - 2))  # two-decimal exponential: 1.23e-6
    return float(10.0 ** -min(8, max(0, 3 - (exponent + 1))))


def fmt_num_3_fits(lo: float, hi: float, *, ticks: int = 10) -> bool:
    """Whether ``fmtNum(v, 3)`` tick labels stay distinct on an axis spanning ``[lo, hi]``
    with up to ``ticks`` ticks: False for a narrow range far from zero (53.13 … 53.14 would
    print "53.1" at every tick), where :func:`line_chart` falls back to Vega's adaptive
    format. A flat axis (``lo == hi``) has one tick and always fits."""
    span = hi - lo
    if span <= 0:
        return True
    return fmt_num_3_step(max(abs(lo), abs(hi))) <= span / ticks


def axis_format(fmt: str | None) -> dict[str, Any]:
    """``alt.Axis`` keyword arguments of a tick format: ``None`` = Vega's adaptive default,
    :data:`FMT_NUM_3` = React's ``fmtNum(v, 3)``, anything else a d3-format string
    (``".0%"``, ``",.0f"``)."""
    if fmt is None:
        return {}
    if fmt == FMT_NUM_3:
        return {"labelExpr": FMT_NUM_3_LABEL_EXPR}
    return {"format": fmt}


def tidy_x_axis(tick_count: int | None = X_TICK_COUNT) -> dict[str, Any]:
    """``alt.Axis`` keyword arguments that keep x tick labels whole and apart: about
    ``tick_count`` ticks (``None`` = Vega's default density), overlapping labels thinned
    (``labelOverlap`` with a :data:`X_LABEL_GAP_PX` separation), end labels flush with the
    plot and any that would still spill more than :data:`X_LABEL_BOUND_PX` hidden."""
    props: dict[str, Any] = {
        "labelOverlap": True,
        "labelSeparation": X_LABEL_GAP_PX,
        "labelFlush": True,
        "labelBound": X_LABEL_BOUND_PX,
    }
    if tick_count is not None:
        props["tickCount"] = tick_count
    return props


def level_text(x: float) -> str:
    """An index level (spot, strike) in a tooltip: whole points, grouped like the axis ticks
    (:data:`SPOT_AXIS_FORMAT`) and the readouts (``Spot 6,312``). React's tooltips print
    ``Number(v).toFixed(0)`` (``6312``) under axes that it also leaves ungrouped; here the
    axes are grouped, so the hover matches them."""
    return fmt_level(x, 0)


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
    y_format: str | None = FMT_NUM_3,
    x_tooltip: TickFormatter = fmt_num,
    y_tooltip: TickFormatter = fmt_num,
    x_tick_count: int | None = X_TICK_COUNT,
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
        x_format, y_format: tick formats (see :func:`axis_format`): a d3-format string
            (``".0%"`` for a vol axis, :data:`SPOT_AXIS_FORMAT` for levels), :data:`FMT_NUM_3`
            (React's ``fmtNum(v, 3)``, the y default) or ``None`` (Vega's adaptive default,
            the x default). A :data:`FMT_NUM_3` y axis whose range is too narrow for three
            significant figures (:func:`fmt_num_3_fits`) uses Vega's default instead.
        x_tooltip, y_tooltip: formatters for the hover tooltip (default
            :func:`~eqd_desk.app.ui.format.fmt_num`, the React tooltip format; use
            :func:`level_text` for a spot / strike x (``Spot 6,312``) and
            :func:`~eqd_desk.app.ui.format.fmt_money` for a money series).
        x_tick_count: tick-count hint of the x axis (:func:`tidy_x_axis`; the labels are
            always thinned so they never collide); ``None`` = Vega's default density.
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
        axis=alt.Axis(**axis_format(x_format), **tidy_x_axis(x_tick_count)),
    )
    y_scale = (
        alt.Scale(domain=list(y_domain), nice=False, zero=False)
        if y_domain is not None
        else alt.Scale(zero=y_zero, nice=True)
    )
    if y_format == FMT_NUM_3 and y_range is not None:
        lo, hi = y_domain if y_domain is not None else y_range
        if y_domain is None and y_zero:
            lo, hi = min(lo, 0.0), max(hi, 0.0)
        if not fmt_num_3_fits(lo, hi):
            y_format = None  # 3 significant figures cannot tell these ticks apart
    y_enc = alt.Y(
        "y:Q",
        title=y_title,
        scale=y_scale,
        axis=alt.Axis(**axis_format(y_format)),
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
    spots: Iterable[float],
    expiry: Iterable[float],
    now: Iterable[float],
    *,
    spot: float,
    strikes: Iterable[float] = (),
    expiry_label: str = "At expiry",
    now_label: str = "Now",
    x_title: str = "Spot",
    y_title: str = "Value",
    x_format: str | None = SPOT_AXIS_FORMAT,
    y_format: str | None = FMT_NUM_3,
    x_tooltip: TickFormatter = level_text,
    y_tooltip: TickFormatter = fmt_money,
    height: int = SHORT_HEIGHT,
) -> alt.LayerChart:
    """Payoff at expiry (solid line colour, 2 px) against the value now (thin accent, 1.5 px),
    with the current spot (dashed accent), the strikes (dotted) and the zero line.

    The React convention: the gap between the two curves is time value (single option) or the
    mark-to-market vs expiry P&L (a structure). Pass P&L arrays and ``y_title="P&L (USD)"``
    for a strategy; values and ``y_title="Value (USD)"`` for a single option. The axes read
    as React's (``PlotsPanel.tsx`` / ``StrategyPlots.tsx``): spot ticks in whole points, y
    ticks ``fmtNum(v, 3)``; the hover reads like the axes and the readouts: ``Spot 6,312``
    and each curve in money (``119.61``, two decimals, as the premium hero prints it).
    ``x_format`` / ``y_format`` / ``x_tooltip`` / ``y_tooltip`` override
    them (same meaning as in :func:`line_chart`). Columns of a DataFrame work as the
    sequences: ``payoff_chart(df["S"], df["expiry"], df["now"], spot=…)``.
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
        x_format=x_format,
        y_format=y_format,
        x_tooltip=x_tooltip,
        y_tooltip=y_tooltip,
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
    x_tick_count: int | None = X_TICK_COUNT,
    height: int = SHORT_HEIGHT,
) -> alt.LayerChart:
    """Two series on independent y axes (left and right) against a shared x: the simulator's
    spot & implied-vol path. Hover shows both values. The x axis is tidied like
    :func:`line_chart`'s (``x_tick_count``); the y formats are d3 strings or
    :data:`FMT_NUM_3` (see :func:`axis_format`), Vega's default when ``None``."""
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
        "x:Q",
        title=x_title,
        scale=alt.Scale(domain=list(x_range), nice=False, zero=False),
        axis=alt.Axis(**tidy_x_axis(x_tick_count)),
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
        axis = alt.Axis(orient=orient, grid=orient == "left", **axis_format(fmt))
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


__all__ = [
    "DEFAULT_HEIGHT",
    "FMT_NUM_3",
    "FMT_NUM_3_LABEL_EXPR",
    "MEDIUM_HEIGHT",
    "RULE_STYLES",
    "SHORT_HEIGHT",
    "SPOT_AXIS_FORMAT",
    "TALL_HEIGHT",
    "X_LABEL_BOUND_PX",
    "X_LABEL_GAP_PX",
    "X_TICK_COUNT",
    "HRule",
    "RuleLook",
    "RuleStyle",
    "Series",
    "TickFormatter",
    "VRule",
    "axis_format",
    "bar_chart",
    "dual_axis_chart",
    "fmt_num_3_fits",
    "fmt_num_3_step",
    "level_text",
    "line_chart",
    "payoff_chart",
    "show_chart",
    "style_chart",
    "sweep_x",
    "tidy_x_axis",
]
