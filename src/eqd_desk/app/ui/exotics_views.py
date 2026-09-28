"""Streamlit renderers of the exotics page: one view per sub-tab (barrier, digital,
autocallable, variance swap), each laid out like its React counterpart
(``web/src/components/exotics/*View.tsx``) as a three-column terminal:

- LEFT: the instrument's controls, then its price / value and greeks readout;
- CENTER: the characteristic chart(s), captioned from :mod:`eqd_desk.content`;
- RIGHT: the Learn panel (``ExoticInfo.tsx``): what the instrument is, its behaviour and
  principal risk, then the price / greek chips and the selected metric's card.

The numbers come from :mod:`eqd_desk.app.ui.exotics_curves` (pure, unit-tested): this
module wires them to widgets, caches them (``st.cache_data`` keyed on the inputs) and
draws the charts. Session state lives under ``exo.<view>.`` keys, seeded on first use, so
each view keeps its inputs when the user switches sub-tab or page.

Controls beyond the React views (their defaults reproduce the React numbers): r and q on
the barrier and the digital, a vanilla overlay on the barrier chart, a cash / asset payout on
the digital, a skew switch and the strip's strike range and count on the variance swap, and
a Reset per view.

Metric selection mirrors React's shared ``metric`` state: the Learn chips
(:func:`~eqd_desk.app.ui.widgets.greek_picker`, key ``exo.<view>.metric``) own the value
and the chart's own selector writes to it through a callback. React also selects a metric
by clicking a readout row; here the selected row is highlighted and selection goes through
the chips or the chart selector.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from typing import TYPE_CHECKING, Final, cast

import altair as alt
import pandas as pd
import streamlit as st

from eqd_desk.app.ui import charts, state, theme
from eqd_desk.app.ui.charts import HRule, RuleStyle, Series, VRule
from eqd_desk.app.ui.education import (
    exotic_doc_card,
    exotic_greek_card,
    learn_header,
    teaching_caption,
)
from eqd_desk.app.ui.exotics_curves import (
    AUTOCALL_READOUT_KEYS,
    BARRIER_CHART_METRICS,
    BARRIER_KIND_LABELS,
    DEFAULT_METRIC,
    DIGITAL_CHART_METRICS,
    DIGITAL_PAYOUT_LABELS,
    PRICED_READOUT_KEYS,
    SAMPLE_PATHS,
    AssetDecomposition,
    AutocallData,
    BarrierData,
    Bounds,
    DigitalData,
    DigitalPayout,
    VarSwapControls,
    VarSwapData,
    autocall_bounds,
    autocall_data,
    autocall_detail,
    autocall_levels,
    autocall_seed,
    autocall_spot_display,
    autocall_value_label,
    barrier_bounds,
    barrier_data,
    barrier_seed,
    digital_bounds,
    digital_data,
    digital_detail,
    digital_seed,
    digital_series_labels,
    digital_width_seed,
    maturity_display,
    mc_badge,
    metric_axis_title,
    observation_times,
    payout_amount,
    pct_of_vanilla,
    replication_recipe,
    varswap_bounds,
    varswap_data,
    varswap_seed,
    vol_axis_domain,
    years_display,
)
from eqd_desk.app.ui.format import (
    fmt_days,
    fmt_level,
    fmt_money,
    fmt_num,
    fmt_pct,
    fmt_signed,
    fmt_signed_pct,
    fmt_years_days,
    to_fixed,
)
from eqd_desk.app.ui.widgets import (
    ReadoutRow,
    choice,
    greek_label,
    greek_picker,
    greek_rows,
    group_row,
    hero_number,
    number_slider,
    option_type_toggle,
    readout_styler,
    section_header,
    set_number,
    sub_heading,
)
from eqd_desk.content import EXOTIC_METRICS, ExoticKind, ExoticMetric, markdown_safe
from eqd_desk.content.exotics import (
    AUTOCALL_DIAGNOSTICS,
    AUTOCALL_MEMORY_HINT,
    AUTOCALL_PATHS_CAPTION,
    BARRIER_CHART_CAPTION,
    DIGITAL_GREEK_CAPTION,
    DIGITAL_PRICE_CAPTION,
    EXOTIC_TAB_LABELS,
    VARSWAP_FAIR_VOL_NOTE,
    VARSWAP_READOUT,
    VARSWAP_SKEW_HINT,
    VARSWAP_STRIP_CAPTION,
)
from eqd_desk.content.greeks import SURFACE_VOL_HINT
from eqd_desk.data import MarketSnapshot
from eqd_desk.engine import GREEK_UNITS
from eqd_desk.engine.exotics import (
    AutocallInputs,
    BarrierInputs,
    BarrierKind,
    DigitalInputs,
)
from eqd_desk.engine.types import OptionType

if TYPE_CHECKING:
    from streamlit.delta_generator import DeltaGenerator

KIND_KEY: Final = "exo.kind"
"""Session key of the sub-tab picker."""

KIND_ICONS: Final[Mapping[ExoticKind, str]] = {
    "barrier": ":material/fence:",
    "digital": ":material/toggle_on:",
    "autocall": ":material/event_repeat:",
    "varswap": ":material/ssid_chart:",
}
"""Icon of each sub-tab."""

COLUMNS: Final = (1.0, 1.9, 1.0)
"""Widths of the controls · chart · Learn columns (React ``.layout`` grid)."""

BAR: Final = "exo.bar."
"""Session-key prefix of the barrier view."""
DIG: Final = "exo.dig."
"""Session-key prefix of the digital view."""
AC: Final = "exo.ac."
"""Session-key prefix of the autocallable view."""
VS: Final = "exo.vs."
"""Session-key prefix of the variance swap view."""

SPINNER_TEXT: Final = "Pricing the note by Monte Carlo…"
"""Shown while the autocallable is (re)priced on a cache miss."""

PARITY_HEADING: Final = "Knock\u2011in + knock\u2011out = vanilla"
"""Readout heading of the barrier's in/out rows (non-breaking hyphens keep it on one line)."""
ASSET_CALL_HEADING: Final = "Asset = K \u00d7 digital + vanilla"
"""Readout heading of an asset-or-nothing call's decomposition rows."""
ASSET_PUT_HEADING: Final = "Asset = K \u00d7 digital \u2212 vanilla"
"""Readout heading of an asset-or-nothing put's decomposition rows."""

SKEW_HELP: Final = "Off: a flat smile at the ATM vol (slope and curvature ignored)."
"""Tooltip of the variance swap's skew switch."""

CHART_CACHE_ENTRIES: Final = 48
"""Built charts kept per builder (see :func:`chart_cache`)."""

X_LABEL_BOUND_PX: Final = 8
"""Pixels by which an x tick label may spill past either end of the axis before it is
hidden (the chart's right padding is 10 px, so a label that is kept is never cut)."""
X_LABEL_GAP_PX: Final = 6
"""Minimum gap between neighbouring x tick labels; closer ones are thinned out."""

STRIKE_MULT_FORMAT: Final = "{} × F"
"""Display of a strip bound as a multiple of the forward."""


# ------------------------------------------------------------------ cached computations


@st.cache_data(max_entries=64, show_spinner=False)
def cached_barrier(i: BarrierInputs, metric: ExoticMetric, spot: float) -> BarrierData:
    """:func:`~eqd_desk.app.ui.exotics_curves.barrier_data`, cached on its inputs."""
    return barrier_data(i, metric, spot)


@st.cache_data(max_entries=64, show_spinner=False)
def cached_digital(
    i: DigitalInputs, width: float, metric: ExoticMetric, spot: float, payout: DigitalPayout
) -> DigitalData:
    """:func:`~eqd_desk.app.ui.exotics_curves.digital_data`, cached on its inputs."""
    return digital_data(i, width, metric, spot, payout)


@st.cache_data(max_entries=32, show_spinner=SPINNER_TEXT)
def cached_autocall(i: AutocallInputs) -> AutocallData:
    """:func:`~eqd_desk.app.ui.exotics_curves.autocall_data` (the Monte Carlo), cached on
    the note's inputs; a spinner shows on a cache miss."""
    return autocall_data(i)


@st.cache_data(max_entries=64, show_spinner=False)
def cached_varswap(c: VarSwapControls, S: float, r: float, q: float) -> VarSwapData:
    """:func:`~eqd_desk.app.ui.exotics_curves.varswap_data`, cached on its inputs."""
    return varswap_data(c, S=S, r=r, q=q)


# ------------------------------------------------------------------ shared pieces


def exotic_picker() -> ExoticKind:
    """The sub-tab picker (Barrier · Digital · Autocallable · Variance swap)."""
    labels = {k: f"{KIND_ICONS[k]} {markdown_safe(v)}" for k, v in EXOTIC_TAB_LABELS.items()}
    return choice("Exotic", labels, key=KIND_KEY, default="barrier")


def three_columns() -> tuple[DeltaGenerator, DeltaGenerator, DeltaGenerator]:
    """The controls · chart · Learn columns."""
    left, center, right = st.columns(COLUMNS, gap="medium")
    return left, center, right


def slider(
    label: str,
    key: str,
    bounds: Bounds,
    default: float,
    display: Callable[[float], str],
    *,
    symbol: str | None = None,
    fmt: str = "%.2f",
    integer: bool = False,
    disabled: bool = False,
) -> float:
    """A compact labelled slider over ``bounds`` (React ``LabeledSlider``): label and
    symbol on the left, ``display(value)`` on the right; ``disabled`` greys it out while
    another control makes it irrelevant (its value is kept)."""
    return number_slider(
        label,
        key=key,
        min_value=bounds.lo,
        max_value=bounds.hi,
        step=bounds.step,
        default=default,
        display=display,
        symbol=symbol,
        slider_format=fmt,
        integer=integer,
        compact=True,
        disabled=disabled,
    )


def current_metric(metric_key: str, kind: ExoticKind) -> ExoticMetric:
    """The shared metric of a view, seeded with the view's default (React
    ``useState<ExoticMetric>``)."""
    state.ensure_state({metric_key: DEFAULT_METRIC[kind]})
    value = st.session_state[metric_key]
    return cast("ExoticMetric", value if value in EXOTIC_METRICS else DEFAULT_METRIC[kind])


def metric_selector(metric_key: str, options: Sequence[ExoticMetric]) -> None:
    """The chart's own metric selector (a subset of the metrics). It writes the shared
    metric (the Learn chips' key) through a callback, and shows no selection while the
    shared metric is one it does not offer (theta, rho)."""
    widget_key = f"{metric_key}__chart"
    current = st.session_state.get(metric_key)
    st.session_state[widget_key] = current if current in options else None

    def adopt() -> None:
        picked = st.session_state.get(widget_key)
        if picked is not None:
            st.session_state[metric_key] = picked

    st.segmented_control(
        "Chart metric",
        list(options),
        format_func=greek_label,
        key=widget_key,
        on_change=adopt,
        label_visibility="collapsed",
    )


def learn_panel(kind: ExoticKind, metric_key: str | None) -> None:
    """The right column (React ``ExoticInfo``): the instrument's desk card, then (for the
    priced exotics) the price & greeks chips and the selected metric's short card."""
    with st.container(border=True, height="stretch"):
        learn_header(badge="exotic")
        exotic_doc_card(kind)
        if metric_key is not None:
            sub_heading("Price & greeks")
            metric = greek_picker(
                key=metric_key,
                options=EXOTIC_METRICS,
                default=DEFAULT_METRIC[kind],
                label="Price & greeks",
            )
            exotic_greek_card(metric)


def readout(rows: Sequence[ReadoutRow], *, plain: Collection[int] = ()) -> None:
    """A :func:`~eqd_desk.app.ui.widgets.readout_table` in which the rows at indices
    ``plain`` print their value in the body-text colour rather than a sign colour
    (probabilities, levels and vols, which React prints uncoloured)."""
    sty = readout_styler(rows)
    if plain:

        def paint(frame: pd.DataFrame) -> pd.DataFrame:
            css = pd.DataFrame("", index=frame.index, columns=frame.columns)
            css["value"] = [f"color: {theme.TEXT}" if n in plain else "" for n in range(len(frame))]
            return css

        sty = sty.apply(paint, axis=None)
    st.table(sty, border="horizontal", hide_index=True, hide_header=True)


def flush(chart: alt.LayerChart) -> alt.LayerChart:
    """Keep the x tick labels whole and apart: a label exactly at an end of the axis (0 and
    the maturity on the autocall's time axis) is aligned inside the plot (Vega
    ``labelFlush``); one that would still spill more than :data:`X_LABEL_BOUND_PX` past an
    end is hidden rather than cut in half (``labelBound``); and labels closer than
    :data:`X_LABEL_GAP_PX` are thinned (``labelSeparation`` with the default parity
    overlap rule), so the ends never crowd."""
    return cast(
        "alt.LayerChart",
        chart.configure_axisX(
            labelFlush=True, labelBound=X_LABEL_BOUND_PX, labelSeparation=X_LABEL_GAP_PX
        ),
    )


def chart_cache[**P](builder: Callable[P, alt.LayerChart]) -> Callable[P, alt.LayerChart]:
    """Cache a chart builder's result per argument set (``st.cache_resource``: the built
    chart is shared, never copied, and never mutated).

    Building an Altair chart costs more than computing its numbers, so a rerun that leaves
    a chart's inputs unchanged (switching sub-tab and back, picking a greek that chart
    does not plot) reuses it instead of rebuilding it.
    """
    return cast(
        "Callable[P, alt.LayerChart]",
        st.cache_resource(max_entries=CHART_CACHE_ENTRIES, show_spinner=False)(builder),
    )


def level_tooltip(v: float) -> str:
    """A spot / strike level in a tooltip, in whole points like React (``Spot: 6312``)."""
    return to_fixed(v, 0)


def surface_vol_button(prefix: str) -> None:
    """React's "σ ← surface": set σ to the seed vol surface at the current K and T."""

    def snap_vol() -> None:
        K = float(st.session_state[f"{prefix}K"])
        T = float(st.session_state[f"{prefix}T"])
        set_number(f"{prefix}sigma", state.surface().get_vol(K, T))

    st.button(
        "σ ← surface",
        key=f"{prefix}surface",
        help=markdown_safe(SURFACE_VOL_HINT),
        on_click=snap_vol,
        width="stretch",
    )


def reset_button(prefix: str, values: Mapping[str, object]) -> None:
    """Restore a view's opening inputs (``values``: session key → seed value)."""
    st.button(
        "Reset",
        key=f"{prefix}reset",
        icon=":material/restart_alt:",
        help="Restore the opening inputs",
        on_click=state.reset_state,
        args=(dict(values),),
        width="stretch",
    )


# ------------------------------------------------------------------ barrier


@chart_cache
def barrier_chart(
    curve: pd.DataFrame, i: BarrierInputs, metric: ExoticMetric, *, currency: str, vanilla: bool
) -> alt.LayerChart:
    """The barrier option's metric vs spot (optionally with the vanilla's, dashed), with
    barrier H (red dashed), strike K (dotted) and spot (accent)."""
    u = GREEK_UNITS[metric]
    series = [Series("barrier", f"{BARRIER_KIND_LABELS[i.kind]} {i.type}")]
    if vanilla:
        series.insert(0, Series("vanilla", f"Vanilla {i.type}", theme.TEXT_DIM, 1.5, (4, 3)))
    return flush(
        charts.line_chart(
            curve,
            x="S",
            series=series,
            x_title="Spot",
            y_title=metric_axis_title(u.label, u.unit, currency, metric),
            x_tooltip=level_tooltip,
            vrules=[VRule(i.H, "barrier", "H"), VRule(i.K, "strike"), VRule(i.S, "current")],
            height=charts.TALL_HEIGHT,
        )
    )


def barrier_readout_rows(data: BarrierData, metric: ExoticMetric) -> list[ReadoutRow]:
    """The greeks (selected metric highlighted), then the knock-in + knock-out = vanilla
    rows."""
    p = data.parity
    return [
        *greek_rows(data.greeks, groups=None, keys=PRICED_READOUT_KEYS, selected=metric),
        group_row(PARITY_HEADING),
        ReadoutRow(BARRIER_KIND_LABELS[p.out_kind], p.knock_out, fmt_money(p.knock_out)),
        ReadoutRow(BARRIER_KIND_LABELS[p.in_kind], p.knock_in, fmt_money(p.knock_in)),
        ReadoutRow("Sum", p.total, fmt_money(p.total), unit=f"vanilla {fmt_money(p.vanilla)}"),
    ]


def barrier_view(snap: MarketSnapshot) -> None:
    """Single-barrier option: inputs incl. barrier H and kind, price and greeks against the
    vanilla, the in/out parity, and the selected metric swept against spot so the gamma
    blow-up at the barrier is visible."""
    seed = barrier_seed(snap)
    b = barrier_bounds(snap.spot)
    metric_key = f"{BAR}metric"
    metric = current_metric(metric_key, "barrier")
    state.ensure_state({f"{BAR}vanilla": True})
    left, center, right = three_columns()

    with left, st.container(border=True):
        with section_header("Barrier", icon=":material/tune:"):
            option: OptionType = option_type_toggle(key=f"{BAR}type", default=seed.type)
        kind: BarrierKind = choice(
            "Barrier kind", BARRIER_KIND_LABELS, key=f"{BAR}kind", default=seed.kind
        )
        S = slider("Spot", f"{BAR}S", b["S"], seed.S, fmt_money, symbol="S")
        K = slider("Strike", f"{BAR}K", b["K"], seed.K, fmt_money, symbol="K")
        H = slider("Barrier", f"{BAR}H", b["H"], seed.H, fmt_money, symbol="H")
        T = slider("Time", f"{BAR}T", b["T"], seed.T, years_display, symbol="T")
        vol = slider("Vol", f"{BAR}sigma", b["sigma"], seed.sigma, fmt_pct, symbol="σ", fmt="%.4f")
        r = slider("Rate", f"{BAR}r", b["r"], seed.r, fmt_pct, symbol="r", fmt="%.4f")
        q = slider("Dividend yield", f"{BAR}q", b["q"], seed.q, fmt_pct, symbol="q", fmt="%.4f")
        with st.container(horizontal=True):
            surface_vol_button(BAR)
            numbers = ("S", "K", "H", "T", "sigma", "r", "q")
            reset_button(
                BAR,
                {
                    f"{BAR}type": seed.type,
                    f"{BAR}kind": seed.kind,
                    **{f"{BAR}{k}": getattr(seed, k) for k in numbers},
                },
            )

    i = BarrierInputs(S=S, K=K, T=T, r=r, q=q, sigma=vol, type=option, H=H, kind=kind)
    data = cached_barrier(i, metric, snap.spot)
    g, p = data.greeks, data.parity

    with left, st.container(border=True):
        section_header(
            "Price & greeks",
            badge=f"{pct_of_vanilla(g.price, p.vanilla)}% of vanilla",
            badge_color="primary",
        )
        hero_number(
            f"Barrier premium ({snap.currency})",
            fmt_money(g.price),
            detail=f"vanilla {fmt_money(p.vanilla)}",
        )
        rows = barrier_readout_rows(data, metric)
        readout(rows, plain=range(len(rows) - 3, len(rows)))

    with center, st.container(border=True, height="stretch"):
        with section_header(GREEK_UNITS[metric].label, subtitle="vs", highlight="spot"):
            show_vanilla = st.toggle(
                "Vanilla",
                key=f"{BAR}vanilla",
                help="Overlay the same metric of the vanilla (no barrier)",
                persist_state="session",
            )
            metric_selector(metric_key, BARRIER_CHART_METRICS)
        charts.show_chart(
            barrier_chart(data.curve, i, metric, currency=snap.currency, vanilla=show_vanilla),
            key=f"{BAR}chart",
        )
        teaching_caption(BARRIER_CHART_CAPTION)

    with right:
        learn_panel("barrier", metric_key)


# ------------------------------------------------------------------ digital


@chart_cache
def digital_chart(
    curve: pd.DataFrame,
    i: DigitalInputs,
    metric: ExoticMetric,
    *,
    currency: str,
    payout: DigitalPayout = "cash",
) -> alt.LayerChart:
    """The digital (blue) and its spread replication (orange) vs spot, or the selected
    greek of the digital; strike dotted, spot accent."""
    u = GREEK_UNITS[metric]
    spread_label, digital_label = digital_series_labels(i.type, payout)
    series = (
        [Series("spread", spread_label, theme.PUT, 1.5), Series("digital", digital_label)]
        if metric == "price"
        else [Series("greek", u.label)]
    )
    return flush(
        charts.line_chart(
            curve,
            x="S",
            series=series,
            x_title="Spot",
            y_title=metric_axis_title(u.label, u.unit, currency, metric),
            x_tooltip=level_tooltip,
            vrules=[VRule(i.K, "strike"), VRule(i.S, "current")],
            height=charts.TALL_HEIGHT,
        )
    )


@chart_cache
def convergence_chart(
    convergence: pd.DataFrame,
    width: float,
    *,
    currency: str,
    labels: tuple[str, str] = ("Call spread", "Digital"),
) -> alt.LayerChart:
    """The replication's price against the spread width Δ, beside the digital it converges
    to (``labels``: the replication's and the digital's legend labels)."""
    spread_label, digital_label = labels
    return flush(
        charts.line_chart(
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
    )


def convergence_note(
    spread: float, digital: float, i: DigitalInputs, width: float, payout: DigitalPayout
) -> str:
    """The numbers under the convergence chart: the replication vs the digital at the
    chosen width, and what the replication holds."""
    name = "spread" if payout == "cash" else "replication"
    return (
        f"At Δ = {fmt_money(width)}: {name} {fmt_money(spread)} vs digital "
        f"{fmt_money(digital)} (difference {fmt_signed(spread - digital, 3)}), "
        f"{replication_recipe(i, width, payout)}."
    )


def asset_rows(d: AssetDecomposition, price: float, option: OptionType) -> list[ReadoutRow]:
    """Asset-or-nothing = K cash digitals ± the vanilla, as readout rows that add up to the
    premium shown above them."""
    vanilla = d.sign * d.vanilla
    heading = ASSET_CALL_HEADING if option == "call" else ASSET_PUT_HEADING
    return [
        group_row(heading),
        ReadoutRow("K × cash digital", d.k_digitals, fmt_money(d.k_digitals)),
        ReadoutRow(f"Vanilla {option}", vanilla, fmt_money(vanilla)),
        ReadoutRow("Sum", d.total, fmt_money(d.total), unit=f"premium {fmt_money(price)}"),
    ]


def digital_view(snap: MarketSnapshot) -> None:
    """Digital: cash-or-nothing (React) or asset-or-nothing; price and greeks, the spread
    replication with its (payout/Δ) size, the digital vs the replication against spot, and
    the replication converging as Δ → 0."""
    seed = digital_seed(snap)
    width_seed = digital_width_seed(snap.spot)
    b = digital_bounds(snap.spot)
    metric_key = f"{DIG}metric"
    metric = current_metric(metric_key, "digital")
    left, center, right = three_columns()

    with left, st.container(border=True):
        with section_header("Digital", icon=":material/tune:"):
            option: OptionType = option_type_toggle(key=f"{DIG}type", default=seed.type)
        payout: DigitalPayout = choice(
            "Payout", DIGITAL_PAYOUT_LABELS, key=f"{DIG}payout", default="cash"
        )
        S = slider("Spot", f"{DIG}S", b["S"], seed.S, fmt_money, symbol="S")
        K = slider("Strike", f"{DIG}K", b["K"], seed.K, fmt_money, symbol="K")
        T = slider("Time", f"{DIG}T", b["T"], seed.T, fmt_years_days, symbol="T", fmt="%.3f")
        vol = slider("Vol", f"{DIG}sigma", b["sigma"], seed.sigma, fmt_pct, symbol="σ", fmt="%.4f")
        r = slider("Rate", f"{DIG}r", b["r"], seed.r, fmt_pct, symbol="r", fmt="%.4f")
        q = slider("Dividend yield", f"{DIG}q", b["q"], seed.q, fmt_pct, symbol="q", fmt="%.4f")
        cash = slider(
            "Cash payout",
            f"{DIG}cash",
            b["cash"],
            seed.cash,
            fmt_money,
            symbol="Q",
            disabled=payout == "asset",
        )
        width = slider(
            "Replication width", f"{DIG}width", b["width"], width_seed, fmt_money, symbol="Δ"
        )
        with st.container(horizontal=True):
            surface_vol_button(DIG)
            numbers = ("S", "K", "T", "sigma", "r", "q", "cash")
            reset_button(
                DIG,
                {
                    f"{DIG}type": seed.type,
                    f"{DIG}payout": "cash",
                    f"{DIG}width": width_seed,
                    **{f"{DIG}{k}": getattr(seed, k) for k in numbers},
                },
            )

    i = DigitalInputs(S=S, K=K, T=T, r=r, q=q, sigma=vol, type=option, cash=cash)
    data = cached_digital(i, width, metric, snap.spot, payout)
    g = data.greeks
    labels = digital_series_labels(option, payout)

    with left, st.container(border=True):
        section_header("Price & greeks")
        hero_number(
            f"Digital premium ({snap.currency})",
            fmt_money(g.price),
            detail=digital_detail(
                data.spread,
                payout_amount(i, payout),
                width,
                label="spread" if payout == "cash" else "replication",
            ),
        )
        rows = greek_rows(g, groups=None, keys=PRICED_READOUT_KEYS, selected=metric)
        if data.decomposition is None:
            readout(rows)
        else:
            parts = asset_rows(data.decomposition, g.price, option)
            readout([*rows, *parts], plain=range(len(rows) + 1, len(rows) + len(parts)))

    with center, st.container(border=True, height="stretch"):
        is_price = metric == "price"
        title = "Value" if is_price else GREEK_UNITS[metric].label
        with section_header(title, subtitle="vs", highlight="spot"):
            metric_selector(metric_key, DIGITAL_CHART_METRICS)
        charts.show_chart(
            digital_chart(data.curve, i, metric, currency=snap.currency, payout=payout),
            key=f"{DIG}chart",
        )
        teaching_caption(DIGITAL_PRICE_CAPTION if is_price else DIGITAL_GREEK_CAPTION)

        section_header(labels[0], subtitle="vs", highlight="width Δ")
        charts.show_chart(
            convergence_chart(data.convergence, width, currency=snap.currency, labels=labels),
            key=f"{DIG}convergence",
        )
        st.caption(markdown_safe(convergence_note(data.spread, g.price, i, width, payout)))

    with right:
        learn_panel("digital", metric_key)


# ------------------------------------------------------------------ autocallable


@chart_cache
def autocall_chart(paths: pd.DataFrame, i: AutocallInputs) -> alt.LayerChart:
    """Sample GBM paths with the autocall (accent), coupon (orange) and protection (red)
    barriers and the observation dates (dim); hovering shows every path's level.

    Hand-built rather than :func:`~eqd_desk.app.ui.charts.line_chart`, which draws one
    layer per series: the paths share one style, so ONE line layer grouped by path does
    it, and the chart builds and serialises ~3× faster. The look (terminal config, rule
    styles, hover crosshair) is the shared one.
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
                axis=alt.Axis(format=".1f", tickCount=6),
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
    return flush(charts.style_chart(chart))


def autocall_readout_rows(data: AutocallData, metric: ExoticMetric) -> list[ReadoutRow]:
    """Diagnostics (P(autocall), P(capital loss), expected life), then the MC greeks."""
    res = data.result
    p_call, p_loss, life = AUTOCALL_DIAGNOSTICS
    return [
        group_row("Diagnostics"),
        ReadoutRow(p_call.label, res.prob_autocall, fmt_pct(res.prob_autocall, 1), p_call.note),
        ReadoutRow(
            p_loss.label,
            res.prob_capital_loss,
            fmt_pct(res.prob_capital_loss, 1),
            p_loss.note,
            tone="neg",
        ),
        ReadoutRow(life.label, res.expected_life, fmt_num(res.expected_life, 3), life.note),
        group_row("Greeks (MC)"),
        *greek_rows(data.greeks, groups=None, keys=AUTOCALL_READOUT_KEYS, selected=metric),
    ]


def autocall_view(snap: MarketSnapshot) -> None:
    """Phoenix autocallable: structural inputs, the Monte-Carlo value with its diagnostics
    (early-redemption and capital-loss probabilities, expected life) and greeks, and sample
    paths against the barriers to make the path-dependence visible."""
    seed = autocall_seed(snap)
    s0 = seed.S0
    b = autocall_bounds(s0)
    metric_key = f"{AC}metric"
    metric = current_metric(metric_key, "autocall")
    state.ensure_state({f"{AC}memory": seed.memory})
    left, center, right = three_columns()

    with left, st.container(border=True):
        with section_header("Autocallable", icon=":material/tune:"):
            memory = st.toggle(
                "Memory",
                key=f"{AC}memory",
                help=markdown_safe(AUTOCALL_MEMORY_HINT),
                persist_state="session",
            )
        S = slider(
            "Spot", f"{AC}S", b["S"], seed.S, lambda v: autocall_spot_display(v, s0), symbol="S"
        )
        maturity = slider(
            "Maturity", f"{AC}maturity", b["maturity"], seed.maturity, maturity_display, fmt="%.1f"
        )
        n_obs = slider(
            "Observations", f"{AC}n_obs", b["n_obs"], seed.n_obs, fmt_level, fmt="%d", integer=True
        )
        coupon = slider(
            "Coupon / period",
            f"{AC}coupon",
            b["coupon_rate"],
            seed.coupon_rate,
            fmt_pct,
            fmt="%.4f",
        )
        ab = slider(
            "Autocall barrier", f"{AC}ab", b["autocall_barrier"], seed.autocall_barrier, fmt_pct
        )
        cb = slider("Coupon barrier", f"{AC}cb", b["coupon_barrier"], seed.coupon_barrier, fmt_pct)
        pb = slider(
            "Protection barrier",
            f"{AC}pb",
            b["protection_barrier"],
            seed.protection_barrier,
            fmt_pct,
        )
        vol = slider("Vol", f"{AC}sigma", b["sigma"], seed.sigma, fmt_pct, symbol="σ", fmt="%.4f")
        reset_button(
            AC,
            {
                f"{AC}memory": seed.memory,
                f"{AC}S": seed.S,
                f"{AC}maturity": seed.maturity,
                f"{AC}n_obs": seed.n_obs,
                f"{AC}coupon": seed.coupon_rate,
                f"{AC}ab": seed.autocall_barrier,
                f"{AC}cb": seed.coupon_barrier,
                f"{AC}pb": seed.protection_barrier,
                f"{AC}sigma": seed.sigma,
            },
        )

    i = AutocallInputs(
        S=S,
        S0=s0,
        sigma=vol,
        r=seed.r,
        q=seed.q,
        maturity=maturity,
        n_obs=int(n_obs),
        coupon_rate=coupon,
        autocall_barrier=ab,
        coupon_barrier=cb,
        protection_barrier=pb,
        memory=memory,
        notional=seed.notional,
    )
    with left:
        data = cached_autocall(i)  # the spinner (cache miss only) shows here
    res = data.result

    with left, st.container(border=True):
        section_header("Value & greeks", badge=mc_badge(res.stderr), badge_color="gray")
        hero_number(
            autocall_value_label(i.notional),
            fmt_money(res.price),
            detail=autocall_detail(res.price, i.notional),
        )
        readout(autocall_readout_rows(data, metric), plain=(1, 3))

    with center, st.container(border=True, height="stretch"):
        section_header(
            "Sample paths",
            subtitle="&",
            highlight="barriers",
            badge=f"{SAMPLE_PATHS} GBM paths",
            badge_color="gray",
        )
        charts.show_chart(autocall_chart(data.paths, i), key=f"{AC}chart")
        teaching_caption(AUTOCALL_PATHS_CAPTION)

    with right:
        learn_panel("autocall", metric_key)


# ------------------------------------------------------------------ variance swap


@chart_cache
def strip_chart(strip: pd.DataFrame, forward: float) -> alt.LayerChart:
    """Each OTM option's 1/K²-weighted contribution to the fair variance, forward marked."""
    return flush(
        charts.line_chart(
            strip,
            x="K",
            series=Series("contribution", "Contribution", width=1.5, fill=theme.ACCENT_DIM),
            x_title="Strike",
            y_title="Weighted contribution",
            x_tooltip=level_tooltip,
            y_tooltip=lambda v: fmt_num(v, 5),
            vrules=[VRule(forward, "forward", "F")],
            height=250,
        )
    )


@chart_cache
def smile_chart(strip: pd.DataFrame, forward: float, fair_vol: float) -> alt.LayerChart:
    """The smile the strip is priced on, with the fair vol it produces (a flat smile gets a
    fixed 4-vol-point axis, :func:`~eqd_desk.app.ui.exotics_curves.vol_axis_domain`)."""
    return flush(
        charts.line_chart(
            strip,
            x="K",
            series=Series("vol", "Implied vol", theme.PUT),
            x_title="Strike",
            y_title="Implied vol",
            y_format=".0%",
            x_tooltip=level_tooltip,
            y_tooltip=fmt_pct,
            vrules=[VRule(forward, "forward")],
            hrules=[HRule(fair_vol, "marker", "fair vol", "below")],
            y_zero=False,
            y_domain=vol_axis_domain([*strip["vol"], fair_vol]),
            height=charts.SHORT_HEIGHT,
        )
    )


@chart_cache
def skew_chart(skew: pd.DataFrame, slope: float) -> alt.LayerChart:
    """Fair vol vs the skew slope (ATM fixed): the steeper the skew, the richer the
    variance."""
    return flush(
        charts.line_chart(
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
    )


def varswap_readout_rows(data: VarSwapData, currency: str) -> list[ReadoutRow]:
    """Fair variance, ATM vol, the convexity premium (fair − ATM) and the forward."""
    fair_var, atm, premium = VARSWAP_READOUT
    cp = data.convexity_premium
    return [
        ReadoutRow(
            fair_var.label, data.fair_variance, fmt_num(data.fair_variance, 5), fair_var.note
        ),
        ReadoutRow(atm.label, data.atm_vol, fmt_pct(data.atm_vol), atm.note),
        ReadoutRow(
            premium.label, cp, fmt_signed_pct(cp), premium.note, "pos" if cp >= 0 else "neg"
        ),
        ReadoutRow("Forward", data.forward, fmt_money(data.forward), currency),
    ]


def skew_note(data: VarSwapData, c: VarSwapControls) -> str:
    """The numbers under the skew-effect chart: fair vs ATM at the current slope (or with
    the skew off), and the strip the fair variance was replicated with."""
    where = f"At slope {fmt_num(c.slope, 3)}" if c.skew else "Skew off (flat smile)"
    return (
        f"{where}: fair vol {fmt_pct(data.fair_vol)} vs ATM "
        f"{fmt_pct(data.atm_vol)} ({fmt_signed_pct(data.convexity_premium)}); strip "
        f"{fmt_level(c.lo_mult * data.forward, 0)} to {fmt_level(c.hi_mult * data.forward, 0)}, "
        f"{c.n_strikes} strikes."
    )


def varswap_view(snap: MarketSnapshot) -> None:
    """Variance swap: a controllable smile feeds the model-free 1/K² replication; the
    readout compares the fair vol with ATM (the convexity premium) and the charts show the
    strip, the smile and how the skew moves the fair vol."""
    seed = varswap_seed(snap)
    b = varswap_bounds()
    state.ensure_state({f"{VS}skew": seed.skew})
    left, center, right = three_columns()

    def mult(v: float) -> str:
        return STRIKE_MULT_FORMAT.format(to_fixed(v, 2))

    def three_dp(v: float) -> str:
        return fmt_num(v, 3)

    with left, st.container(border=True):
        with section_header("Variance swap", icon=":material/tune:"):
            skew_on = st.toggle("Skew", key=f"{VS}skew", help=SKEW_HELP, persist_state="session")
        T = slider("Tenor", f"{VS}T", b["T"], seed.T, fmt_days, symbol="T", fmt="%.4f")
        atm = slider("ATM vol", f"{VS}atm", b["atm_vol"], seed.atm_vol, fmt_pct, fmt="%.4f")
        slope = slider(
            "Skew slope", f"{VS}slope", b["slope"], seed.slope, three_dp, disabled=not skew_on
        )
        curv = slider(
            "Smile curvature", f"{VS}curv", b["curv"], seed.curv, three_dp, disabled=not skew_on
        )
        teaching_caption(VARSWAP_SKEW_HINT)
        sub_heading("Replication strip")
        lo = slider("Lowest strike", f"{VS}lo", b["lo_mult"], seed.lo_mult, mult)
        hi = slider("Highest strike", f"{VS}hi", b["hi_mult"], seed.hi_mult, mult)
        n = slider(
            "Strikes", f"{VS}n", b["n_strikes"], seed.n_strikes, fmt_level, fmt="%d", integer=True
        )
        reset_button(
            VS,
            {
                f"{VS}skew": seed.skew,
                f"{VS}T": seed.T,
                f"{VS}atm": seed.atm_vol,
                f"{VS}slope": seed.slope,
                f"{VS}curv": seed.curv,
                f"{VS}lo": seed.lo_mult,
                f"{VS}hi": seed.hi_mult,
                f"{VS}n": seed.n_strikes,
            },
        )

    c = VarSwapControls(
        T=T,
        atm_vol=atm,
        slope=slope,
        curv=curv,
        lo_mult=lo,
        hi_mult=hi,
        n_strikes=int(n),
        skew=skew_on,
    )
    data = cached_varswap(c, snap.spot, snap.r, snap.q)

    with left, st.container(border=True):
        section_header("Fair variance", badge="VIX-style", badge_color="primary")
        note = VARSWAP_FAIR_VOL_NOTE
        hero_number(note.label.capitalize(), fmt_pct(data.fair_vol), detail=note.note)
        readout(varswap_readout_rows(data, snap.currency), plain=(0, 1, 3))

    with center, st.container(border=True, height="stretch"):
        section_header("Replication strip", subtitle="(weighted 1/K²)")
        charts.show_chart(strip_chart(data.strip, data.forward), key=f"{VS}strip")
        teaching_caption(VARSWAP_STRIP_CAPTION)
        sub_heading("Implied-vol smile")
        charts.show_chart(smile_chart(data.strip, data.forward, data.fair_vol), key=f"{VS}smile")
        section_header("Skew effect", subtitle="fair vol vs", highlight="skew slope")
        charts.show_chart(skew_chart(data.skew, c.smile_slope), key=f"{VS}skew_chart")
        st.caption(markdown_safe(skew_note(data, c)))

    with right:
        learn_panel("varswap", None)


# ------------------------------------------------------------------ dispatch

VIEWS: Final[Mapping[ExoticKind, Callable[[MarketSnapshot], None]]] = {
    "barrier": barrier_view,
    "digital": digital_view,
    "autocall": autocall_view,
    "varswap": varswap_view,
}
"""The renderer of each sub-tab."""
