"""Streamlit renderers of the exotics page: one view per sub-tab (barrier, digital,
autocallable, variance swap), each laid out like its React counterpart
(``web/src/components/exotics/*View.tsx``) as a three-column terminal:

- LEFT: the instrument's controls, then its price / value and greeks readout;
- CENTER: the characteristic chart(s), captioned from :mod:`eqd_desk.content`;
- RIGHT: the Learn panel (``ExoticInfo.tsx``): what the instrument is, its behaviour and
  principal risk, then the price / greek chips and the selected metric's card.

This module holds only the Streamlit half: widgets, layout and caching. The pure halves are
unit-tested without Streamlit: the numbers in :mod:`eqd_desk.app.ui.exotics_curves`, the
charts in :mod:`eqd_desk.app.ui.exotics_charts`, the readout rows and notes in
:mod:`eqd_desk.app.ui.exotics_display`. Numbers are cached with ``st.cache_data`` and built
charts with ``st.cache_resource`` (:func:`chart_cache`), both keyed on their inputs.

Every input keeps its value under a plain ``exo.<view>.`` Session State key, seeded on first
use, so each view keeps its inputs when the user switches sub-tab or page; the widgets are
the remount-safe ones of :mod:`eqd_desk.app.ui.widgets` (see :mod:`eqd_desk.app.ui.inputs`),
so a quick series of slider moves never resets a control.

Controls beyond the React views (their defaults reproduce the React numbers): r and q on
the barrier and the digital, the barrier kind as a direction and a knock (switching side
mirrors H to the other side of spot), a vanilla overlay on the barrier chart, a cash / asset
payout on the digital, a skew switch and the strip's strike range and count on the variance
swap, and a Reset per view.

Metric selection mirrors React's shared ``metric`` state: the Learn chips
(:func:`~eqd_desk.app.ui.widgets.greek_picker`, key ``exo.<view>.metric``) own the value
and the chart's own selector (:func:`metric_selector`) writes to it through a callback.
React also selects a metric by clicking a readout row; here the selected row is highlighted
and selection goes through the chips or the chart selector.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Final, cast

import altair as alt
import streamlit as st

from eqd_desk.app.ui import charts, inputs, state
from eqd_desk.app.ui import exotics_charts as xc
from eqd_desk.app.ui.bounds import Bounds, listed_strike_step
from eqd_desk.app.ui.education import (
    exotic_doc_card,
    exotic_greek_card,
    learn_header,
    teaching_caption,
)
from eqd_desk.app.ui.exotics_curves import (
    BARRIER_CHART_METRICS,
    BARRIER_DIRECTION_LABELS,
    BARRIER_KNOCK_LABELS,
    DEFAULT_METRIC,
    DIGITAL_CHART_METRICS,
    DIGITAL_PAYOUT_LABELS,
    METRIC_CHIPS,
    PRICED_READOUT_KEYS,
    SAMPLE_PATHS,
    AutocallData,
    BarrierData,
    BarrierDirection,
    BarrierKnock,
    DigitalData,
    DigitalPayout,
    VarSwapControls,
    VarSwapData,
    autocall_bounds,
    autocall_data,
    autocall_detail,
    autocall_seed,
    autocall_spot_display,
    autocall_value_label,
    barrier_bounds,
    barrier_data,
    barrier_kind,
    barrier_seed,
    barrier_sides,
    digital_bounds,
    digital_data,
    digital_detail,
    digital_seed,
    digital_series_labels,
    digital_width_seed,
    maturity_display,
    mc_badge,
    payout_amount,
    pct_of_vanilla,
    reflected_barrier,
    varswap_bounds,
    varswap_data,
    varswap_seed,
    years_display,
)
from eqd_desk.app.ui.exotics_display import (
    asset_rows,
    autocall_readout_rows,
    barrier_note,
    barrier_readout_rows,
    convergence_note,
    digital_chart_caption,
    skew_note,
    varswap_readout_rows,
)
from eqd_desk.app.ui.format import (
    THUMB_LEVEL,
    THUMB_PERCENT,
    THUMB_YEARS,
    fmt_level,
    fmt_money,
    fmt_num,
    fmt_pct,
    fmt_years_days,
    to_fixed,
)
from eqd_desk.app.ui.readout import greek_rows
from eqd_desk.app.ui.widgets import (
    choice,
    greek_label,
    greek_picker,
    hero_number,
    number_slider,
    option_type_toggle,
    readout_table,
    reset_button,
    section_header,
    set_number,
    sub_heading,
    surface_vol_button,
    toggle,
)
from eqd_desk.content import ExoticKind, ExoticMetric, markdown_safe
from eqd_desk.content.exotics import (
    AUTOCALL_GAMMA_NOTE,
    AUTOCALL_MEMORY_HINT,
    AUTOCALL_PATHS_CAPTION,
    BARRIER_CHART_CAPTION,
    BARRIER_DIRECTION_HINT,
    BARRIER_KNOCK_HINT,
    DIGITAL_PAYOUT_HINT,
    EXOTIC_TAB_LABELS,
    RESET_VIEW_HINT,
    VARSWAP_FAIR_VOL_NOTE,
    VARSWAP_SKEW_HINT,
    VARSWAP_SKEW_SWITCH_HINT,
    VARSWAP_STRIP_CAPTION,
)
from eqd_desk.data import MarketSnapshot
from eqd_desk.engine import GREEK_UNITS, OptionType
from eqd_desk.engine.exotics import (
    AutocallInputs,
    BarrierInputs,
    DigitalInputs,
)

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

VANILLA_OVERLAY_HELP: Final = "Overlay the same metric of the vanilla (no barrier)"
"""Tooltip of the barrier chart's vanilla-overlay switch."""

NOTE_ICON: Final = ":material/info:"
"""Icon of the barrier's "already knocked" note
(:func:`~eqd_desk.app.ui.exotics_display.barrier_note`)."""

CHART_CACHE_ENTRIES: Final = 48
"""Built charts kept per builder (see :func:`chart_cache`)."""

CHART_METRIC_SUFFIX: Final = "__chart"
"""The chart metric selector's canonical key is ``<metric key>__chart``."""

STRIKE_MULT_FORMAT: Final = "{} × F"
"""Display of a strip bound as a multiple of the forward."""
MULT_THUMB: Final = "%.2f × F"
"""Slider-thumb format of a strip bound, like its display (``0.50 × F``)."""


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


cached_barrier_chart: Final = chart_cache(xc.barrier_chart)
""":func:`~eqd_desk.app.ui.exotics_charts.barrier_chart`, cached (:func:`chart_cache`)."""
cached_digital_chart: Final = chart_cache(xc.digital_chart)
""":func:`~eqd_desk.app.ui.exotics_charts.digital_chart`, cached."""
cached_convergence_chart: Final = chart_cache(xc.convergence_chart)
""":func:`~eqd_desk.app.ui.exotics_charts.convergence_chart`, cached."""
cached_autocall_chart: Final = chart_cache(xc.autocall_chart)
""":func:`~eqd_desk.app.ui.exotics_charts.autocall_chart`, cached."""
cached_strip_chart: Final = chart_cache(xc.strip_chart)
""":func:`~eqd_desk.app.ui.exotics_charts.strip_chart`, cached."""
cached_smile_chart: Final = chart_cache(xc.smile_chart)
""":func:`~eqd_desk.app.ui.exotics_charts.smile_chart`, cached."""
cached_skew_chart: Final = chart_cache(xc.skew_chart)
""":func:`~eqd_desk.app.ui.exotics_charts.skew_chart`, cached."""


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
    fmt: str = THUMB_LEVEL,
    integer: bool = False,
    disabled: bool = False,
) -> float:
    """A compact labelled slider over ``bounds`` (React ``LabeledSlider``): label and
    symbol on the left, ``display(value)`` on the right; ``disabled`` greys it out while
    another control makes it irrelevant (its value is kept). ``fmt`` formats the thumb in
    the units of ``display`` (default: a grouped level, ``6,312.45``)."""
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
    ``useState<ExoticMetric>``); a value the view's chips do not offer falls back to the
    default."""
    state.ensure_state({metric_key: DEFAULT_METRIC[kind]})
    value = st.session_state[metric_key]
    return cast("ExoticMetric", value if value in METRIC_CHIPS[kind] else DEFAULT_METRIC[kind])


def chart_metric_key(base: str, shown: ExoticMetric | None) -> str:
    """The widget key to render a chart metric selector with (canonical key ``base``), given
    the metric it must show (``None``: no selection).

    The remount-safe contract of :mod:`eqd_desk.app.ui.inputs`, for a selector that may
    legitimately hold no selection: if the live widget shows anything else than ``shown``
    (the chips picked another metric), the generation is bumped so a fresh widget mounts
    with ``shown`` as its default. :func:`~eqd_desk.app.ui.inputs.steady_key` cannot do it
    here: it reads a live ``None`` as "no widget yet", so after the chips go theta → vega
    the selector would keep showing no selection.
    """
    wkey = inputs.current_widget_key(base)
    if wkey in st.session_state and st.session_state[wkey] != shown:
        inputs.remount(base)
        wkey = inputs.current_widget_key(base)
    return wkey


def metric_selector(metric_key: str, options: Sequence[ExoticMetric]) -> None:
    """The chart's own metric selector (a subset of the metrics). It writes the shared
    metric (the Learn chips' key) through a callback, and shows no selection while the
    shared metric is one it does not offer (theta, rho). Remount-safe: the widget is created
    with the shown metric as its default under :func:`chart_metric_key`, never written."""
    current = st.session_state.get(metric_key)
    shown = cast("ExoticMetric", current) if current in options else None
    wkey = chart_metric_key(f"{metric_key}{CHART_METRIC_SUFFIX}", shown)

    def adopt() -> None:
        picked = st.session_state.get(wkey)
        if picked is not None:
            st.session_state[metric_key] = picked

    st.segmented_control(
        "Chart metric",
        list(options),
        format_func=greek_label,
        default=shown,
        key=wkey,
        on_change=adopt,
        label_visibility="collapsed",
    )


def learn_panel(kind: ExoticKind, metric_key: str | None, *, note: str | None = None) -> None:
    """The right column (React ``ExoticInfo``): the instrument's desk card, then (for the
    priced exotics) the price & greek chips the view reports (:data:`METRIC_CHIPS
    <eqd_desk.app.ui.exotics_curves.METRIC_CHIPS>`), an optional ``note`` under them, and
    the selected metric's short card."""
    with st.container(border=True, height="stretch"):
        learn_header(badge="exotic")
        exotic_doc_card(kind)
        if metric_key is not None:
            sub_heading("Price & greeks")
            metric = greek_picker(
                key=metric_key,
                options=METRIC_CHIPS[kind],
                default=DEFAULT_METRIC[kind],
                label="Price & greeks",
            )
            if note:
                teaching_caption(note)
            exotic_greek_card(metric)


# ------------------------------------------------------------------ barrier


def mirror_barrier(bounds: Bounds, step: float) -> None:
    """``on_change`` of the barrier's direction: if barrier H now sits on the breached side
    of spot (a down barrier switched to up is below spot), move it to the mirrored level on
    the other side (:func:`~eqd_desk.app.ui.exotics_curves.reflected_barrier`), so the new
    option does not start out already knocked in or out."""
    S = float(st.session_state[f"{BAR}S"])
    H = float(st.session_state[f"{BAR}H"])
    direction = cast("BarrierDirection", st.session_state[f"{BAR}dir"])
    mirrored = reflected_barrier(S, H, direction, bounds, step)
    if mirrored != H:
        set_number(f"{BAR}H", mirrored)


def barrier_view(snap: MarketSnapshot) -> None:
    """Single-barrier option: inputs incl. barrier H, its direction and knock, price and
    greeks against the vanilla, the in/out parity, and the selected metric swept against
    spot so the gamma blow-up at the barrier is visible."""
    seed = barrier_seed(snap)
    seed_direction, seed_knock = barrier_sides(seed.kind)
    b = barrier_bounds(snap.spot)
    metric_key = f"{BAR}metric"
    metric = current_metric(metric_key, "barrier")
    left, center, right = three_columns()

    def on_direction() -> None:
        mirror_barrier(b["H"], listed_strike_step(snap.spot))

    with left, st.container(border=True):
        with section_header("Barrier", icon=":material/tune:"):
            option: OptionType = option_type_toggle(key=f"{BAR}type", default=seed.type)
        with st.container(horizontal=True, gap="small"):
            direction: BarrierDirection = choice(
                "Direction",
                BARRIER_DIRECTION_LABELS,
                key=f"{BAR}dir",
                default=seed_direction,
                help=BARRIER_DIRECTION_HINT,
                label_visibility="visible",
                on_change=on_direction,
            )
            knock: BarrierKnock = choice(
                "Knock",
                BARRIER_KNOCK_LABELS,
                key=f"{BAR}knock",
                default=seed_knock,
                help=BARRIER_KNOCK_HINT,
                label_visibility="visible",
            )
        S = slider("Spot", f"{BAR}S", b["S"], seed.S, fmt_money, symbol="S")
        K = slider("Strike", f"{BAR}K", b["K"], seed.K, fmt_money, symbol="K")
        H = slider("Barrier", f"{BAR}H", b["H"], seed.H, fmt_money, symbol="H")
        T = slider("Time", f"{BAR}T", b["T"], seed.T, years_display, symbol="T", fmt="%.2f y")
        vol = slider(
            "Vol", f"{BAR}sigma", b["sigma"], seed.sigma, fmt_pct, symbol="σ", fmt=THUMB_PERCENT
        )
        r = slider("Rate", f"{BAR}r", b["r"], seed.r, fmt_pct, symbol="r", fmt=THUMB_PERCENT)
        q = slider(
            "Dividend yield", f"{BAR}q", b["q"], seed.q, fmt_pct, symbol="q", fmt=THUMB_PERCENT
        )
        with st.container(horizontal=True):
            surface_vol_button(BAR)
            numbers = ("S", "K", "H", "T", "sigma", "r", "q")
            reset_button(
                {
                    f"{BAR}type": seed.type,
                    f"{BAR}dir": seed_direction,
                    f"{BAR}knock": seed_knock,
                    **{f"{BAR}{k}": getattr(seed, k) for k in numbers},
                },
                key=f"{BAR}reset",
                help=RESET_VIEW_HINT,
            )

    kind = barrier_kind(direction, knock)
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
        readout_table(barrier_readout_rows(data, metric, snap.currency))

    with center, st.container(border=True, height="stretch"):
        with section_header(GREEK_UNITS[metric].label, subtitle="vs", highlight="spot"):
            show_vanilla = toggle(
                "Vanilla", key=f"{BAR}vanilla", default=True, help=VANILLA_OVERLAY_HELP
            )
            metric_selector(metric_key, BARRIER_CHART_METRICS)
        note = barrier_note(i)
        if note is not None:
            st.info(markdown_safe(note), icon=NOTE_ICON)
        charts.show_chart(
            cached_barrier_chart(
                data.curve, i, metric, currency=snap.currency, vanilla=show_vanilla
            ),
            key=f"{BAR}chart",
        )
        teaching_caption(BARRIER_CHART_CAPTION)

    with right:
        learn_panel("barrier", metric_key)


# ------------------------------------------------------------------ digital


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
            "Payout",
            DIGITAL_PAYOUT_LABELS,
            key=f"{DIG}payout",
            default="cash",
            help=DIGITAL_PAYOUT_HINT,
            label_visibility="visible",
        )
        S = slider("Spot", f"{DIG}S", b["S"], seed.S, fmt_money, symbol="S")
        K = slider("Strike", f"{DIG}K", b["K"], seed.K, fmt_money, symbol="K")
        T = slider("Time", f"{DIG}T", b["T"], seed.T, fmt_years_days, symbol="T", fmt=THUMB_YEARS)
        vol = slider(
            "Vol", f"{DIG}sigma", b["sigma"], seed.sigma, fmt_pct, symbol="σ", fmt=THUMB_PERCENT
        )
        r = slider("Rate", f"{DIG}r", b["r"], seed.r, fmt_pct, symbol="r", fmt=THUMB_PERCENT)
        q = slider(
            "Dividend yield", f"{DIG}q", b["q"], seed.q, fmt_pct, symbol="q", fmt=THUMB_PERCENT
        )
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
                {
                    f"{DIG}type": seed.type,
                    f"{DIG}payout": "cash",
                    f"{DIG}width": width_seed,
                    **{f"{DIG}{k}": getattr(seed, k) for k in numbers},
                },
                key=f"{DIG}reset",
                help=RESET_VIEW_HINT,
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
        rows = greek_rows(
            g, groups=None, keys=PRICED_READOUT_KEYS, selected=metric, currency=snap.currency
        )
        if data.decomposition is not None:
            rows.extend(asset_rows(data.decomposition, g.price, option))
        readout_table(rows)

    with center, st.container(border=True, height="stretch"):
        is_price = metric == "price"
        title = "Value" if is_price else GREEK_UNITS[metric].label
        with section_header(title, subtitle="vs", highlight="spot"):
            metric_selector(metric_key, DIGITAL_CHART_METRICS)
        charts.show_chart(
            cached_digital_chart(data.curve, i, metric, currency=snap.currency, payout=payout),
            key=f"{DIG}chart",
        )
        teaching_caption(digital_chart_caption(is_price, payout, option))

        section_header(labels[0], subtitle="vs", highlight="width Δ")
        charts.show_chart(
            cached_convergence_chart(
                data.convergence, width, currency=snap.currency, labels=labels
            ),
            key=f"{DIG}convergence",
        )
        st.caption(markdown_safe(convergence_note(data.spread, g.price, i, width, payout)))

    with right:
        learn_panel("digital", metric_key)


# ------------------------------------------------------------------ autocallable


def autocall_view(snap: MarketSnapshot) -> None:
    """Phoenix autocallable: structural inputs, the Monte-Carlo value with its diagnostics
    (early-redemption and capital-loss probabilities, expected life) and greeks, and sample
    paths against the barriers to make the path-dependence visible."""
    seed = autocall_seed(snap)
    s0 = seed.S0
    b = autocall_bounds(s0)
    metric_key = f"{AC}metric"
    metric = current_metric(metric_key, "autocall")
    left, center, right = three_columns()

    with left, st.container(border=True):
        with section_header("Autocallable", icon=":material/tune:"):
            memory = toggle(
                "Memory",
                key=f"{AC}memory",
                default=seed.memory,
                help=AUTOCALL_MEMORY_HINT,
            )
        S = slider(
            "Spot", f"{AC}S", b["S"], seed.S, lambda v: autocall_spot_display(v, s0), symbol="S"
        )
        maturity = slider(
            "Maturity",
            f"{AC}maturity",
            b["maturity"],
            seed.maturity,
            maturity_display,
            fmt="%.1f y",
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
            fmt=THUMB_PERCENT,
        )
        ab = slider(
            "Autocall barrier",
            f"{AC}ab",
            b["autocall_barrier"],
            seed.autocall_barrier,
            fmt_pct,
            fmt=THUMB_PERCENT,
        )
        cb = slider(
            "Coupon barrier",
            f"{AC}cb",
            b["coupon_barrier"],
            seed.coupon_barrier,
            fmt_pct,
            fmt=THUMB_PERCENT,
        )
        pb = slider(
            "Protection barrier",
            f"{AC}pb",
            b["protection_barrier"],
            seed.protection_barrier,
            fmt_pct,
            fmt=THUMB_PERCENT,
        )
        vol = slider(
            "Vol", f"{AC}sigma", b["sigma"], seed.sigma, fmt_pct, symbol="σ", fmt=THUMB_PERCENT
        )
        reset_button(
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
            key=f"{AC}reset",
            help=RESET_VIEW_HINT,
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
        readout_table(autocall_readout_rows(data, metric, snap.currency))

    with center, st.container(border=True, height="stretch"):
        section_header(
            "Sample paths",
            subtitle="&",
            highlight="barriers",
            badge=f"{SAMPLE_PATHS} GBM paths",
            badge_color="gray",
        )
        charts.show_chart(cached_autocall_chart(data.paths, i), key=f"{AC}chart")
        teaching_caption(AUTOCALL_PATHS_CAPTION)

    with right:
        learn_panel("autocall", metric_key, note=AUTOCALL_GAMMA_NOTE)


# ------------------------------------------------------------------ variance swap


def varswap_view(snap: MarketSnapshot) -> None:
    """Variance swap: a controllable smile feeds the model-free 1/K² replication; the
    readout compares the fair vol with ATM (the convexity premium) and the charts show the
    strip, the smile and how the skew moves the fair vol."""
    seed = varswap_seed(snap)
    b = varswap_bounds()
    left, center, right = three_columns()

    def mult(v: float) -> str:
        return STRIKE_MULT_FORMAT.format(to_fixed(v, 2))

    def three_dp(v: float) -> str:
        return fmt_num(v, 3)

    with left, st.container(border=True):
        with section_header("Variance swap", icon=":material/tune:"):
            skew_on = toggle(
                "Skew",
                key=f"{VS}skew",
                default=seed.skew,
                help=VARSWAP_SKEW_SWITCH_HINT,
            )
        T = slider("Tenor", f"{VS}T", b["T"], seed.T, fmt_years_days, symbol="T", fmt=THUMB_YEARS)
        atm = slider("ATM vol", f"{VS}atm", b["atm_vol"], seed.atm_vol, fmt_pct, fmt=THUMB_PERCENT)
        slope = slider(
            "Skew slope",
            f"{VS}slope",
            b["slope"],
            seed.slope,
            three_dp,
            fmt="%.3f",
            disabled=not skew_on,
        )
        curv = slider(
            "Smile curvature",
            f"{VS}curv",
            b["curv"],
            seed.curv,
            three_dp,
            fmt="%.3f",
            disabled=not skew_on,
        )
        teaching_caption(VARSWAP_SKEW_HINT)
        sub_heading("Replication strip")
        lo = slider("Lowest strike", f"{VS}lo", b["lo_mult"], seed.lo_mult, mult, fmt=MULT_THUMB)
        hi = slider("Highest strike", f"{VS}hi", b["hi_mult"], seed.hi_mult, mult, fmt=MULT_THUMB)
        n = slider(
            "Strikes", f"{VS}n", b["n_strikes"], seed.n_strikes, fmt_level, fmt="%d", integer=True
        )
        reset_button(
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
            key=f"{VS}reset",
            help=RESET_VIEW_HINT,
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
        readout_table(varswap_readout_rows(data, snap.currency))

    with center, st.container(border=True, height="stretch"):
        section_header("Replication strip", subtitle="(weighted 1/K²)")
        charts.show_chart(cached_strip_chart(data.strip, data.forward), key=f"{VS}strip")
        teaching_caption(VARSWAP_STRIP_CAPTION)
        sub_heading("Implied-vol smile")
        charts.show_chart(
            cached_smile_chart(data.strip, data.forward, data.fair_vol), key=f"{VS}smile"
        )
        section_header("Skew effect", subtitle="fair vol vs", highlight="skew slope")
        charts.show_chart(cached_skew_chart(data.skew, c.smile_slope), key=f"{VS}skew_chart")
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


__all__ = [
    "AC",
    "BAR",
    "CHART_CACHE_ENTRIES",
    "CHART_METRIC_SUFFIX",
    "COLUMNS",
    "DIG",
    "KIND_ICONS",
    "KIND_KEY",
    "MULT_THUMB",
    "NOTE_ICON",
    "SPINNER_TEXT",
    "STRIKE_MULT_FORMAT",
    "VANILLA_OVERLAY_HELP",
    "VIEWS",
    "VS",
    "autocall_view",
    "barrier_view",
    "cached_autocall",
    "cached_autocall_chart",
    "cached_barrier",
    "cached_barrier_chart",
    "cached_convergence_chart",
    "cached_digital",
    "cached_digital_chart",
    "cached_skew_chart",
    "cached_smile_chart",
    "cached_strip_chart",
    "cached_varswap",
    "chart_cache",
    "chart_metric_key",
    "current_metric",
    "digital_view",
    "exotic_picker",
    "learn_panel",
    "metric_selector",
    "mirror_barrier",
    "slider",
    "three_columns",
    "varswap_view",
]
