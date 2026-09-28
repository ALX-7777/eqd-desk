"""Shared Streamlit widgets: the pieces that make the four pages read as one product.

Mirrors the React components:

- :func:`app_header` — the top bar's brand + market strip (``App.tsx``).
- :func:`section_header` — a panel's title row with an optional badge / right-hand slot
  (``.panel-title-row``).
- :func:`number_slider` — the paired slider + numeric field of ``InputPanel.tsx`` (or the
  slider-only ``LabeledSlider`` of ``Controls.tsx`` with ``compact=True``), kept in sync
  through Session State.
- :func:`hero_number` — the big premium / P&L number (``.price-hero``).
- :func:`readout_table` / :func:`greek_readout` — the grouped, right-aligned greeks table of
  ``GreeksReadout.tsx`` / ``PositionReadout.tsx`` (and any label · value · unit list).
- :func:`choice`, :func:`option_type_toggle`, :func:`greek_picker` — segmented controls and
  the greek "chips".

The pure halves (row builders, styles, header stats, clamping) are separate functions so
they can be unit-tested without Streamlit.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, Protocol

import pandas as pd
import streamlit as st

from eqd_desk.app.ui import theme
from eqd_desk.app.ui.format import (
    fmt_level,
    fmt_num,
    fmt_pct,
    sign_class,
)
from eqd_desk.app.ui.theme import TONE_COLORS, TONE_MARKDOWN, Tone
from eqd_desk.content import GREEK_KEYS, GreekKey, markdown_safe
from eqd_desk.content.greeks import GREEK_GROUPS, GreekGroup
from eqd_desk.engine import GREEK_UNITS, OptionType

if TYPE_CHECKING:
    from pandas.io.formats.style import Styler
    from streamlit.delta_generator import DeltaGenerator

    from eqd_desk.data import MarketSnapshot, UnderlyingConfig

BadgeColor = Literal["red", "orange", "yellow", "blue", "green", "violet", "gray", "primary"]
"""Colours accepted by ``st.badge``."""

APP_NAME: Final = "EQD Desk"
"""Product name shown in the header strip and the browser tab."""

APP_ICON: Final = ":material/finance_mode:"
"""App icon (browser tab + header brand mark)."""


def md_color(text: str, tone: Tone | None) -> str:
    """Wrap Markdown ``text`` in the Streamlit colour directive of ``tone`` (``:green[…]``);
    ``None`` leaves it uncoloured. ``text`` must already be Markdown-safe."""
    return f":{TONE_MARKDOWN[tone]}[{text}]" if tone else text


# ------------------------------------------------------------------ header strip


@dataclass(frozen=True, slots=True)
class HeaderStat:
    """One market badge of the header strip."""

    label: str
    value: str


def header_stats(snap: MarketSnapshot, cfg: UnderlyingConfig) -> tuple[HeaderStat, ...]:
    """The header's market strip, exactly as ``App.tsx`` prints it: index level (bare
    ``toLocaleString``), the vol index as the 30-day ATM vol, and r / q as percentages."""
    return (
        HeaderStat(cfg.index_ticker, fmt_level(snap.spot, 3)),
        HeaderStat(f"{cfg.vol_index_ticker} (ATM 30d)", fmt_pct(snap.atm_vol_30d)),
        HeaderStat("r", fmt_pct(snap.r)),
        HeaderStat("q", fmt_pct(snap.q)),
    )


def header_subtitle(snap: MarketSnapshot) -> str:
    """``"S&P 500 · BSM with dividend yield"`` (the brand sub-line)."""
    return f"{snap.name} · BSM with dividend yield"


def seed_badge_text(snap: MarketSnapshot) -> str:
    """``"Static seed · 2026-06-23"``: reminds the user the market is a fixed snapshot."""
    return f"Static seed · {snap.asof}"


def app_header(snap: MarketSnapshot, cfg: UnderlyingConfig) -> None:
    """The top strip shown above every page: brand + subtitle on the left, the seed market
    (spot, ATM vol, r, q) and the "static seed" badge (source notes on hover) on the right."""
    with st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
        key="app_header",
    ):
        st.markdown(
            f"**:primary[{APP_ICON}] {APP_NAME}**  \n"
            f":small[:gray[{markdown_safe(header_subtitle(snap))}]]",
            width="content",
        )
        with st.container(
            horizontal=True, vertical_alignment="center", width="content", gap="medium"
        ):
            for stat in header_stats(snap, cfg):
                st.markdown(
                    f":small[:gray[{markdown_safe(stat.label)}]]  \n`{stat.value}`",
                    text_alignment="right",
                    width="content",
                )
            st.badge(
                seed_badge_text(snap),
                icon=":material/database:",
                color="orange",
                help="\n\n".join(markdown_safe(n) for n in snap.source_notes) or None,
            )


# ------------------------------------------------------------------ titles


def section_header(
    title: str,
    *,
    subtitle: str | None = None,
    highlight: str | None = None,
    icon: str | None = None,
    badge: str | None = None,
    badge_color: BadgeColor = "primary",
    badge_icon: str | None = None,
    help: str | None = None,
) -> DeltaGenerator:
    """A panel's title row: bold ``title`` (+ a dim ``subtitle`` and an accent ``highlight``,
    e.g. ``section_header("Delta", subtitle="vs", highlight="spot")`` → **Delta** vs spot),
    with an optional badge on the right.

    Returns the right-hand slot (a horizontal container) so a page can put a control there,
    like the React title rows::

        slot = section_header("Inputs", icon=":material/tune:")
        with slot:
            option_type = option_type_toggle(key="lab.type")

    All text is plain (escaped here); ``icon`` is a ``:material/…:`` shortcode.
    """
    parts = [f"**{markdown_safe(title)}**"]
    if subtitle:
        parts.append(f":gray[{markdown_safe(subtitle)}]")
    if highlight:
        parts.append(f":primary[{markdown_safe(highlight)}]")
    heading = " ".join(parts)
    if icon:
        heading = f":gray[{icon}] {heading}"
    row = st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
        gap="small",
    )
    with row:
        st.markdown(heading, help=help, width="content")
        slot = st.container(
            horizontal=True,
            horizontal_alignment="right",
            vertical_alignment="center",
            width="content",
            gap="small",
        )
        if badge:
            slot.badge(markdown_safe(badge), color=badge_color, icon=badge_icon)
    return slot


def sub_heading(text: str) -> None:
    """A small dim heading inside a panel (React ``.sub-head``: "Payoff at expiry",
    "Key relationships")."""
    st.markdown(f":small[:gray[**{markdown_safe(text)}**]]")


# ------------------------------------------------------------------ paired slider + field


def clamp(value: float, lo: float, hi: float) -> float:
    """``value`` limited to ``[lo, hi]`` (NaN → ``lo``)."""
    if math.isnan(value):
        return lo
    return min(max(value, lo), hi)


def slider_keys(key: str) -> tuple[str, str]:
    """Session-state keys of the slider and numeric-field widgets behind
    :func:`number_slider` ``key`` (the canonical value lives at ``key`` itself)."""
    return f"{key}__slider", f"{key}__input"


def _coerce(value: float, integer: bool) -> float:
    return float(round(value)) if integer else float(value)


def _on_slider(key: str) -> None:
    slider_key, input_key = slider_keys(key)
    v = st.session_state[slider_key]
    st.session_state[key] = v
    st.session_state[input_key] = v


def _on_input(key: str, lo: float, hi: float, integer: bool) -> None:
    slider_key, input_key = slider_keys(key)
    raw = st.session_state[input_key]
    v = clamp(_coerce(float(raw), integer), lo, hi) if raw is not None else st.session_state[key]
    v = int(v) if integer else v
    st.session_state[key] = v
    st.session_state[slider_key] = v
    st.session_state[input_key] = v


def set_number(key: str, value: float) -> None:
    """Programmatically set a :func:`number_slider` (e.g. "Reset to snapshot", "σ ← surface").

    Call it from a widget callback (``on_click``/``on_change``) or before the slider renders
    in the run; both widgets pick the value up when they render.
    """
    st.session_state[key] = value


def number_slider(
    label: str,
    *,
    key: str,
    min_value: float,
    max_value: float,
    step: float,
    default: float | None = None,
    display: str | Callable[[float], str] | None = None,
    symbol: str | None = None,
    slider_format: str | None = None,
    input_format: str | None = None,
    integer: bool = False,
    compact: bool = False,
    help: str | None = None,
    on_change: Callable[[], None] | None = None,
    disabled: bool = False,
) -> float:
    """A labelled numeric input: a header row (label, optional italic ``symbol`` like *S*,
    and a mono ``display`` of the value with units on the right), then a slider paired with a
    numeric field (React ``InputPanel`` ``Field``), both editing the same value.

    The canonical value lives in ``st.session_state[key]`` (a plain, non-widget key, so it
    survives page switches); the two widgets use :func:`slider_keys` and are re-synced from
    it on every run, so moving either one — or calling :func:`set_number` — moves both.

    Args:
        label: sentence-case label ("Spot", "Time to expiry").
        key: unique, page-prefixed session-state key ("lab.S").
        min_value, max_value, step: bounds and increment (the field clamps typed values).
        default: initial value (first run only); defaults to ``min_value``.
        display: text (or ``value -> text``) shown on the right of the header, e.g.
            ``lambda v: fmt_with_unit(fmt_level(v), "USD")``; ``None`` hides it.
        symbol: the variable's symbol, shown dim after the label ("S", "σ").
        slider_format, input_format: printf-style formats for the slider thumb and the
            field (``"%.4f"``); the thumb defaults to the field's format.
        integer: integer-valued control (returns an ``int``-valued float).
        compact: slider only, no numeric field (React ``LabeledSlider``).
        help: tooltip on the label.
        on_change: extra callback after the value changed.
        disabled: grey out both widgets.

    Returns:
        The current value.
    """
    slider_format = slider_format or input_format
    lo, hi = _coerce(min_value, integer), _coerce(max_value, integer)
    stp = _coerce(step, integer) if integer else float(step)
    if key not in st.session_state:
        st.session_state[key] = clamp(_coerce(lo if default is None else default, integer), lo, hi)
    value = clamp(_coerce(float(st.session_state[key]), integer), lo, hi)
    typed: float = int(value) if integer else value
    st.session_state[key] = typed
    slider_key, input_key = slider_keys(key)
    for wkey in (slider_key, input_key):
        if st.session_state.get(wkey) != typed:
            st.session_state[wkey] = typed

    def _after_slider() -> None:
        _on_slider(key)
        if on_change is not None:
            on_change()

    def _after_input() -> None:
        _on_input(key, lo, hi, integer)
        if on_change is not None:
            on_change()

    head = f"{markdown_safe(label)}"
    if symbol:
        head += f" :gray[*{markdown_safe(symbol)}*]"
    shown = display(typed) if callable(display) else display
    with st.container(gap="xsmall"):
        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="bottom",
            gap="small",
        ):
            st.markdown(head, help=help, width="content")
            if shown:
                st.markdown(f"`{shown}`", width="content")
        lo_arg: float = int(lo) if integer else lo
        hi_arg: float = int(hi) if integer else hi
        step_arg: float = int(stp) if integer else stp
        if compact:
            st.slider(
                label,
                min_value=lo_arg,
                max_value=hi_arg,
                step=step_arg,
                format=slider_format,
                key=slider_key,
                on_change=_after_slider,
                label_visibility="collapsed",
                disabled=disabled,
            )
        else:
            left, right = st.columns([2.3, 1], vertical_alignment="center", gap="small", wrap=False)
            with left:
                st.slider(
                    label,
                    min_value=lo_arg,
                    max_value=hi_arg,
                    step=step_arg,
                    format=slider_format,
                    key=slider_key,
                    on_change=_after_slider,
                    label_visibility="collapsed",
                    disabled=disabled,
                )
            with right:
                st.number_input(
                    f"{label} value",
                    min_value=lo_arg,
                    max_value=hi_arg,
                    step=step_arg,
                    format=input_format,
                    key=input_key,
                    on_change=_after_input,
                    label_visibility="collapsed",
                    disabled=disabled,
                )
    return typed


# ------------------------------------------------------------------ hero number


def hero_number(
    label: str,
    value: str,
    *,
    detail: str | None = None,
    tone: Tone | None = None,
    help: str | None = None,
) -> None:
    """The big number of a readout (React ``.price-hero``): a bordered metric with a caption.

    Args:
        label: what the number is, with its unit ("Premium (USD)", "Net premium (USD)").
        value: already formatted (``fmt_money(price)``).
        detail: small dim line under the value ("intrinsic 12.45 · time value 107.16").
        tone: colour the value (e.g. ``sign_class(pnl)``); ``None`` = plain text.
        help: tooltip on the label.
    """
    st.metric(
        markdown_safe(label),
        md_color(markdown_safe(value), tone),
        delta="" if detail else None,
        delta_description=markdown_safe(detail) if detail else None,
        border=True,
        help=help,
    )


# ------------------------------------------------------------------ readout table

RowKind = Literal["row", "group"]
"""A value row, or a group heading ("First order")."""


@dataclass(frozen=True, slots=True)
class ReadoutRow:
    """One line of a :func:`readout_table`: label · right-aligned mono value · dim unit."""

    label: str
    value: float = math.nan
    """The number (kept numeric so the column right-aligns)."""
    text: str | None = None
    """Display text; default :func:`~eqd_desk.app.ui.format.fmt_num` of ``value``."""
    unit: str = ""
    tone: Tone | None = None
    """Value colour; default the sign of ``value`` (green / red / dim)."""
    selected: bool = False
    """Highlight the row (the greek currently plotted / explained)."""
    kind: RowKind = "row"


def group_row(title: str) -> ReadoutRow:
    """A group heading row ("First order", "Diagnostics")."""
    return ReadoutRow(title, kind="group")


def row_text(row: ReadoutRow) -> str:
    """The value text a row displays (empty for a group heading)."""
    if row.kind == "group":
        return ""
    return row.text if row.text is not None else fmt_num(row.value)


def row_tone(row: ReadoutRow) -> Tone:
    """The value colour of a row: its explicit tone, else the sign of its value."""
    return row.tone if row.tone is not None else sign_class(row.value)


def row_styles(row: ReadoutRow) -> tuple[str, str, str]:
    """CSS of the (label, value, unit) cells of a row — the React ``.greeks-table`` look."""
    if row.kind == "group":
        head = (
            f"color: {theme.TEXT_DIM}; font-size: 10.5px; letter-spacing: 0.6px; "
            "text-transform: uppercase; padding-top: 12px; white-space: nowrap"
        )
        # The heading sits in the label cell only (a Styler table has no colspan):
        # max-width 0 keeps it from widening the label column; it overflows into the
        # (empty) value and unit cells of its row instead.
        return f"{head}; max-width: 0; overflow: visible", head, head
    sel = f"background-color: {theme.ACCENT_DIM}; " if row.selected else ""
    label = sel + ("font-weight: 600; " if row.selected else "") + "font-size: 13px"
    label += "; white-space: nowrap"
    if row.selected:
        label += f"; box-shadow: inset 2px 0 0 {theme.ACCENT}"
    value = (
        sel
        + f"font-family: {theme.MONO_FONT}; font-variant-numeric: tabular-nums; "
        + f"font-weight: 600; white-space: nowrap; color: {TONE_COLORS[row_tone(row)]}"
    )
    unit = sel + f"color: {theme.TEXT_DIM}; font-size: 11px; white-space: nowrap"
    return label, value, unit


def readout_frame(rows: Sequence[ReadoutRow]) -> pd.DataFrame:
    """The table's data: ``label`` (Markdown-escaped), numeric ``value`` (NaN for group
    headings) and ``unit`` (escaped)."""
    return pd.DataFrame(
        {
            "label": [markdown_safe(r.label) for r in rows],
            "value": [math.nan if r.kind == "group" else float(r.value) for r in rows],
            "unit": [markdown_safe(r.unit) for r in rows],
        }
    )


def readout_styler(rows: Sequence[ReadoutRow]) -> Styler:
    """A Pandas Styler: display text per row (the value column stays numeric, so Streamlit
    right-aligns it) and the per-cell CSS of :func:`row_styles`."""
    df = readout_frame(rows)
    styles = [row_styles(r) for r in rows]
    sty = df.style.hide(axis="index")
    for i, r in enumerate(rows):
        # (slice(i, i), slice(c, c)) is the single cell (i, c) under label-based .loc rules.
        sty = sty.format(
            _const(markdown_safe(row_text(r))), subset=(slice(i, i), slice("value", "value"))
        )
        # Units and group headings must not break mid-phrase (the Markdown cell ignores
        # `white-space`), so they are displayed with non-breaking spaces.
        sty = sty.format(
            _const(_unbreakable(markdown_safe(r.unit))), subset=(slice(i, i), slice("unit", "unit"))
        )
        if r.kind == "group":
            sty = sty.format(
                _const(_unbreakable(markdown_safe(r.label))),
                subset=(slice(i, i), slice("label", "label")),
            )
    return sty.apply(
        lambda frame: pd.DataFrame(styles, index=frame.index, columns=frame.columns), axis=None
    )


def _const(text: str) -> Callable[[object], str]:
    """A Styler formatter that ignores the cell value and prints ``text``."""
    return lambda _value: text


NBSP: Final = " "
"""Non-breaking space."""


def _unbreakable(text: str) -> str:
    """``text`` with its spaces made non-breaking (kept on one line)."""
    return text.replace(" ", NBSP)


def readout_table(rows: Sequence[ReadoutRow]) -> None:
    """Render rows as a dense, right-aligned table (label · value · unit), group headings in
    small dim capitals and the selected row highlighted — React's ``.greeks-table``."""
    if not rows:
        return
    st.table(readout_styler(rows), border="horizontal", hide_index=True, hide_header=True)


class HasAsDict(Protocol):
    """Anything that exposes its fields as a dict (engine ``Greeks``, ``ExoticGreeks``)."""

    def as_dict(self) -> dict[str, float]: ...


def greek_rows(
    values: Mapping[str, float] | HasAsDict,
    *,
    groups: Sequence[GreekGroup] | None = GREEK_GROUPS,
    keys: Sequence[str] | None = None,
    selected: str | None = None,
) -> list[ReadoutRow]:
    """Readout rows for greeks in REPORTED desk units, labelled and unit-tagged from
    :data:`eqd_desk.engine.GREEK_UNITS`.

    Args:
        values: reported greeks (``analysis.reported``, an ``ExoticGreeks``, or a mapping).
        groups: titled groups (default: first order / second order & cross / third order,
            as in the React readout); ``None`` = one flat list of ``keys``.
        keys: the greeks of a flat list (used when ``groups`` is None), e.g.
            ``("delta", "gamma", "vega", "theta", "rho")`` for an exotic.
        selected: the greek to highlight.
    """
    data = values if isinstance(values, Mapping) else values.as_dict()

    def row(k: str) -> ReadoutRow:
        u = GREEK_UNITS[k]
        return ReadoutRow(u.label, float(data[k]), unit=u.unit, selected=k == selected)

    if groups is None:
        return [row(k) for k in (keys or ())]
    out: list[ReadoutRow] = []
    for g in groups:
        out.append(group_row(g.title))
        out.extend(row(k) for k in g.keys)
    return out


def greek_readout(
    values: Mapping[str, float] | HasAsDict,
    *,
    groups: Sequence[GreekGroup] | None = GREEK_GROUPS,
    keys: Sequence[str] | None = None,
    selected: str | None = None,
) -> None:
    """Render :func:`greek_rows` as a :func:`readout_table` (every greek, grouped by order,
    in desk units, the selected one highlighted)."""
    readout_table(greek_rows(values, groups=groups, keys=keys, selected=selected))


# ------------------------------------------------------------------ choices


def choice[T: str](
    label: str,
    options: Mapping[T, str],
    *,
    key: str,
    default: T,
    help: str | None = None,
    label_visibility: Literal["visible", "hidden", "collapsed"] = "collapsed",
) -> T:
    """A segmented control over ``options`` (value → display label) that always has a
    selection (``required``), kept for the session under ``key``.

    Returns the selected VALUE (not its label).
    """
    if st.session_state.get(key) not in options:
        st.session_state[key] = default
    picked = st.segmented_control(
        label,
        list(options),
        format_func=lambda v: options[v],
        key=key,
        required=True,
        help=help,
        label_visibility=label_visibility,
        persist_state="session",
    )
    return picked if picked is not None else default


OPTION_TYPE_LABELS: Final[Mapping[OptionType, str]] = {"call": "Call", "put": "Put"}
"""Display labels of the call/put toggle."""


def option_type_toggle(*, key: str, default: OptionType = "call") -> OptionType:
    """The CALL | PUT toggle of the React panels; returns ``"call"`` or ``"put"``."""
    return choice("Option type", OPTION_TYPE_LABELS, key=key, default=default)


def greek_label(key: str) -> str:
    """Display label of a greek key (``"delta"`` → ``"Delta"``)."""
    return GREEK_UNITS[key].label


def greek_picker(
    *,
    key: str,
    options: Sequence[GreekKey] = GREEK_KEYS,
    default: GreekKey = "delta",
    label: str = "Greek",
    help: str | None = None,
) -> GreekKey:
    """The greek "chips" (React ``.edu-chips``): pills over ``options`` (price + every greek
    by default), one always selected; drives which greek is plotted and explained."""
    if st.session_state.get(key) not in options:
        st.session_state[key] = default
    picked = st.pills(
        label,
        list(options),
        format_func=greek_label,
        key=key,
        required=True,
        help=help,
        label_visibility="collapsed",
        persist_state="session",
    )
    return picked if picked is not None else default
