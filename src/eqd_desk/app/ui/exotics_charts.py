"""The exotics page's charts (ports of the Recharts plots in
``web/src/components/exotics/*View.tsx``), built on the shared :mod:`eqd_desk.app.ui.charts`
look.

- Barrier: :func:`barrier_chart`, the selected metric of the barrier option against spot
  (the vanilla's dashed beside it), barrier H red dashed, strike K dotted, spot accent: the
  gamma blow-up at a knock-out barrier is the picture.
- Digital: :func:`digital_chart`, the digital against its spread replication (or one of its
  greeks) vs spot; :func:`convergence_chart`, the replication converging to the digital as
  the spread width Δ shrinks.
- Autocallable: :func:`autocall_chart`, a few GBM paths against the autocall, coupon and
  protection barriers and the observation dates (the path-dependence made visible).
- Variance swap: :func:`strip_chart` (each OTM option's 1/K²-weighted contribution),
  :func:`smile_chart` (the smile priced on, with the fair vol) and :func:`skew_chart` (fair
  vol vs the skew slope).

Pure builders (data from :mod:`eqd_desk.app.ui.exotics_curves` in, Altair chart out; no
Streamlit): the views (:mod:`eqd_desk.app.ui.exotics_views`) cache and draw them.
"""

from __future__ import annotations

from typing import Final

import altair as alt
import pandas as pd

from eqd_desk.app.ui import charts, theme
from eqd_desk.app.ui.charts import HRule, RuleStyle, Series, VRule, level_text
from eqd_desk.app.ui.exotics_curves import (
    BARRIER_KIND_LABELS,
    DigitalPayout,
    autocall_levels,
    digital_series_labels,
    metric_axis_title,
    observation_times,
    vol_axis_domain,
)
from eqd_desk.app.ui.format import fmt_money, fmt_num, fmt_pct, to_fixed
from eqd_desk.content import ExoticMetric
from eqd_desk.engine import GREEK_UNITS
from eqd_desk.engine.exotics import AutocallInputs, BarrierInputs, DigitalInputs

AUTOCALL_X_TICK_COUNT: Final = 6
"""Tick-count hint of the autocall chart's time axis: half-year ticks up to a 4-year note
(``0.0`` … ``3.0`` at the default 3 years), whole years from 4.5 years on (the shared
:data:`~eqd_desk.app.ui.charts.X_TICK_COUNT` would keep half-year ticks, 12 of them, up
to 5.5 years)."""

# ------------------------------------------------------------------ barrier


def barrier_chart(
    curve: pd.DataFrame, i: BarrierInputs, metric: ExoticMetric, *, currency: str, vanilla: bool
) -> alt.LayerChart:
    """The barrier option's metric vs spot (optionally with the vanilla's, dashed), with
    barrier H (red dashed), strike K (dotted) and spot (accent).

    Args:
        curve: :func:`~eqd_desk.app.ui.exotics_curves.barrier_curve` output (columns ``S``,
            ``barrier``, ``vanilla``).
        i: the barrier option (its levels are marked).
        metric: what ``curve`` holds (the y-axis title).
        currency: premium currency (the price's axis title).
        vanilla: overlay the vanilla's curve.
    """
    series = [Series("barrier", f"{BARRIER_KIND_LABELS[i.kind]} {i.type}")]
    if vanilla:
        series.insert(0, Series("vanilla", f"Vanilla {i.type}", theme.TEXT_DIM, 1.5, (4, 3)))
    return charts.line_chart(
        curve,
        x="S",
        series=series,
        x_title="Spot",
        y_title=metric_axis_title(metric, currency),
        x_tooltip=level_text,
        vrules=[VRule(i.H, "barrier", "H"), VRule(i.K, "strike"), VRule(i.S, "current")],
        height=charts.TALL_HEIGHT,
    )


# ------------------------------------------------------------------ digital


def digital_chart(
    curve: pd.DataFrame,
    i: DigitalInputs,
    metric: ExoticMetric,
    *,
    currency: str,
    payout: DigitalPayout = "cash",
) -> alt.LayerChart:
    """The digital (blue) and its spread replication (orange) vs spot, or the selected
    greek of the digital; strike dotted, spot accent. ``curve`` is
    :func:`~eqd_desk.app.ui.exotics_curves.digital_curve` output."""
    u = GREEK_UNITS[metric]
    spread_label, digital_label = digital_series_labels(i.type, payout)
    series = (
        [Series("spread", spread_label, theme.PUT, 1.5), Series("digital", digital_label)]
        if metric == "price"
        else [Series("greek", u.label)]
    )
    return charts.line_chart(
        curve,
        x="S",
        series=series,
        x_title="Spot",
        y_title=metric_axis_title(metric, currency),
        x_tooltip=level_text,
        vrules=[VRule(i.K, "strike"), VRule(i.S, "current")],
        height=charts.TALL_HEIGHT,
    )


def convergence_chart(
    convergence: pd.DataFrame,
    width: float,
    *,
    currency: str,
    labels: tuple[str, str] = ("Call spread", "Digital"),
) -> alt.LayerChart:
    """The replication's price against the spread width Δ, beside the digital it converges
    to (``convergence``: :func:`~eqd_desk.app.ui.exotics_curves.spread_convergence` output;
    ``labels``: the replication's and the digital's legend labels); the current width is
    marked."""
    spread_label, digital_label = labels
    return charts.line_chart(
        convergence,
        x="width",
        series=[
            Series("spread", spread_label, theme.PUT, 1.5),
            Series("digital", digital_label),
        ],
        x_title="Replication width Δ",
        y_title=f"Value ({currency})",
        x_tooltip=fmt_money,
        y_tooltip=fmt_money,
        vrules=[VRule(width, "current")],
        y_zero=False,
        height=charts.SHORT_HEIGHT,
    )


# ------------------------------------------------------------------ autocallable


def autocall_chart(paths: pd.DataFrame, i: AutocallInputs) -> alt.LayerChart:
    """Sample GBM paths with the autocall (accent), coupon (orange) and protection (red)
    barriers and the observation dates (dim); hovering shows every path's level.

    ``paths`` is :func:`~eqd_desk.app.ui.exotics_curves.sample_paths` output (``t`` and one
    column per path). Hand-built rather than :func:`~eqd_desk.app.ui.charts.line_chart`,
    which draws one layer per series: the paths share one style, so ONE line layer grouped
    by path does it, and the chart builds and serialises ~3× faster. The look (terminal
    config, rule styles, hover crosshair) is the shared one.
    """
    levels = autocall_levels(i)
    cols = [c for c in paths.columns if c != "t"]
    long = paths.melt(id_vars="t", value_vars=cols, var_name="path", value_name="level")
    lines = (
        alt.Chart(long)
        .mark_line(interpolate="monotone", strokeWidth=1, opacity=0.55, color=theme.LINE, clip=True)
        .encode(
            x=alt.X(
                "t:Q",
                title="Time (years)",
                scale=alt.Scale(domain=[0.0, i.maturity], nice=False, zero=False),
                axis=alt.Axis(format=".1f", **charts.tidy_x_axis(AUTOCALL_X_TICK_COUNT)),
            ),
            y=alt.Y("level:Q", title="Index level", scale=alt.Scale(zero=False, nice=True)),
            detail="path:N",
        )
    )
    marker = charts.RULE_STYLES["marker"]
    layers: list[alt.Chart] = [
        alt.Chart(pd.DataFrame({"t": observation_times(i)[:-1]}))
        .mark_rule(color=marker.color, strokeDash=list(marker.dash), strokeWidth=1, clip=True)
        .encode(x="t:Q")
    ]
    # Each label sits just above its line: autocall and coupon at the right edge, protection
    # at the left (the paths start at spot, far above it), so close barriers do not collide.
    barriers: tuple[tuple[float, RuleStyle, bool], ...] = (
        (levels.autocall, "autocall", True),
        (levels.coupon, "coupon", True),
        (levels.protection, "protection", False),
    )
    for level, style, at_right in barriers:
        look = charts.RULE_STYLES[style]
        df = pd.DataFrame({"y": [level], "label": [style]})
        layers.append(
            alt.Chart(df)
            .mark_rule(color=look.color, strokeDash=list(look.dash), strokeWidth=1, clip=True)
            .encode(y="y:Q")
        )
        layers.append(
            alt.Chart(df)
            .mark_text(
                color=look.color,
                align="right" if at_right else "left",
                baseline="bottom",
                dx=-4 if at_right else 4,
                dy=-3,
                fontSize=10,
                clip=True,
            )
            .encode(x=alt.value("width" if at_right else 0), y="y:Q", text="label:N")
        )
    layers.append(lines)

    text = pd.DataFrame({"t": paths["t"], "t_text": [f"t = {to_fixed(t, 2)}y" for t in paths["t"]]})
    for c in cols:
        text[c] = [fmt_num(v, 4) for v in paths[c]]
    hover = alt.selection_point(
        name="hover", fields=["t"], nearest=True, on="pointerover", empty=False
    )
    layers.append(
        alt.Chart(text)
        .mark_rule(color=theme.TEXT_DIM, strokeWidth=1)
        .encode(
            x="t:Q",
            opacity=alt.when(hover).then(alt.value(0.5)).otherwise(alt.value(0.0)),
            tooltip=[alt.Tooltip("t_text:N", title="Time")]
            + [alt.Tooltip(f"{c}:N", title=f"Path {n + 1}") for n, c in enumerate(cols)],
        )
        .add_params(hover)
    )
    chart = alt.LayerChart(layer=layers).properties(height=charts.TALL_HEIGHT, width="container")
    return charts.style_chart(chart)


# ------------------------------------------------------------------ variance swap


def strip_chart(strip: pd.DataFrame, forward: float) -> alt.LayerChart:
    """Each OTM option's 1/K²-weighted contribution to the fair variance, forward marked
    (``strip``: :func:`~eqd_desk.app.ui.exotics_curves.strip_frame` output)."""
    return charts.line_chart(
        strip,
        x="K",
        series=Series("contribution", "Contribution", width=1.5, fill=theme.ACCENT_DIM),
        x_title="Strike",
        y_title="Weighted contribution",
        x_tooltip=level_text,
        y_tooltip=lambda v: fmt_num(v, 5),
        vrules=[VRule(forward, "forward", "F")],
        height=charts.MEDIUM_HEIGHT,
    )


def smile_chart(strip: pd.DataFrame, forward: float, fair_vol: float) -> alt.LayerChart:
    """The smile the strip is priced on, with the fair vol it produces (a flat smile gets a
    fixed 4-vol-point axis, :func:`~eqd_desk.app.ui.exotics_curves.vol_axis_domain`)."""
    return charts.line_chart(
        strip,
        x="K",
        series=Series("vol", "Implied vol", theme.PUT),
        x_title="Strike",
        y_title="Implied vol",
        y_format=".0%",
        x_tooltip=level_text,
        y_tooltip=fmt_pct,
        vrules=[VRule(forward, "forward")],
        hrules=[HRule(fair_vol, "marker", "fair vol", "below")],
        y_zero=False,
        y_domain=vol_axis_domain([*strip["vol"], fair_vol]),
        height=charts.SHORT_HEIGHT,
    )


def skew_chart(skew: pd.DataFrame, slope: float) -> alt.LayerChart:
    """Fair vol vs the skew slope (ATM fixed), the slope in use marked: the steeper the
    skew, the richer the variance (``skew``:
    :func:`~eqd_desk.app.ui.exotics_curves.skew_effect` output)."""
    return charts.line_chart(
        skew,
        x="slope",
        series=[
            Series("atm_vol", "ATM vol", theme.ACCENT, 1.5, (4, 3)),
            Series("fair_vol", "Fair vol"),
        ],
        x_title="Skew slope",
        y_title="Volatility",
        y_format=".1%",
        x_tooltip=lambda v: fmt_num(v, 3),
        y_tooltip=fmt_pct,
        vrules=[VRule(slope, "current")],
        y_zero=False,
        height=charts.SHORT_HEIGHT,
    )


__all__ = [
    "AUTOCALL_X_TICK_COUNT",
    "autocall_chart",
    "barrier_chart",
    "convergence_chart",
    "digital_chart",
    "skew_chart",
    "smile_chart",
    "strip_chart",
]
