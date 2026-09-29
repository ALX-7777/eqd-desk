"""Shared Streamlit widgets: the pieces that make the four pages read as one product.

Mirrors the React components:

- :func:`app_header` — the top bar's brand + market strip (``App.tsx``).
- :func:`section_header` — a panel's title row with an optional badge / right-hand slot
  (``.panel-title-row``), rendered as a small heading so the page has an outline.
- :func:`number_slider` — the paired slider + fixed-width numeric field of
  ``InputPanel.tsx`` (or the slider-only ``LabeledSlider`` of ``Controls.tsx`` with
  ``compact=True``), both editing one canonical value.
- :func:`hero_number` — the big premium / P&L number (``.price-hero``).
- :func:`readout_table` / :func:`greek_readout` — the grouped, right-aligned greeks table of
  ``GreeksReadout.tsx`` / ``PositionReadout.tsx`` (and any label · value · unit list); the
  table model is the pure :mod:`eqd_desk.app.ui.readout`.
- :func:`choice`, :func:`option_type_toggle`, :func:`greek_picker`, :func:`toggle` —
  segmented controls / pills, the greek "chips" and an on/off switch.
- :func:`surface_vol_button` and :func:`reset_button` — the "σ ← surface" and "Reset"
  actions of the input panels.

Every input here follows the remount-safe contract of :mod:`eqd_desk.app.ui.inputs`: the
value lives in a plain Session State key (the ``key`` you pass, read it with
``st.session_state[key]``), the widgets use derived ``…__w<n>`` keys that are never written,
and a programmatic change goes through :func:`set_number` /
:func:`~eqd_desk.app.ui.inputs.set_value` (or :func:`reset_inputs` for a mixed set).

Text arguments (labels, titles, badges, ``help``) are plain text: every widget here escapes
them for Markdown itself, so callers never pass :func:`~eqd_desk.content.markdown_safe`
output (it would be escaped twice). ``icon`` arguments are ``:material/…:`` shortcodes.

The pure halves (header stats, the readout model) are separate functions so they can be
unit-tested without Streamlit.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

import streamlit as st

from eqd_desk.app.ui import state
from eqd_desk.app.ui.format import fmt_level, fmt_pct
from eqd_desk.app.ui.inputs import (
    LabelVisibility,
    clamp_number,
    remount,
    steady_choice,
    steady_key,
    steady_toggle,
)
from eqd_desk.app.ui.nav import APP_ICON, APP_NAME
from eqd_desk.app.ui.readout import HasAsDict, ReadoutRow, greek_rows, readout_styler
from eqd_desk.app.ui.theme import TONE_MARKDOWN, Tone
from eqd_desk.content import GREEK_KEYS, GreekKey, markdown_safe
from eqd_desk.content.greeks import GREEK_GROUPS, SURFACE_VOL_HINT, GreekGroup
from eqd_desk.engine import GREEK_UNITS, OptionType

if TYPE_CHECKING:
    from streamlit.delta_generator import DeltaGenerator

    from eqd_desk.data import MarketSnapshot, UnderlyingConfig

BadgeColor = Literal["red", "orange", "yellow", "blue", "green", "violet", "gray", "primary"]
"""Colours accepted by ``st.badge``."""


def md_color(text: str, tone: Tone | None) -> str:
    """Wrap Markdown ``text`` in the Streamlit colour directive of ``tone`` (``:green[…]``);
    ``None`` leaves it uncoloured. ``text`` must already be Markdown-safe."""
    return f":{TONE_MARKDOWN[tone]}[{text}]" if tone else text


def safe_help(text: str | None) -> str | None:
    """A plain-text tooltip made Markdown-safe (``None`` / empty → no tooltip)."""
    return markdown_safe(text) if text else None


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

SECTION_HEADING: Final = "###### "
"""Markdown prefix of a :func:`section_header` title: the smallest heading level (``<h6>``,
1 rem, the size of body text), so each panel title is a real heading that assistive
technology can jump between, without looking bigger than the React panel titles."""


def section_title(
    title: str,
    *,
    subtitle: str | None = None,
    highlight: str | None = None,
    icon: str | None = None,
) -> str:
    """The Markdown of a :func:`section_header` title (pure): a small heading holding the
    bold ``title``, a dim ``subtitle`` and an accent ``highlight``, after an optional dim
    icon — ``"###### **Delta** :gray[vs] :primary[spot]"``."""
    parts = [f"**{markdown_safe(title)}**"]
    if subtitle:
        parts.append(f":gray[{markdown_safe(subtitle)}]")
    if highlight:
        parts.append(f":primary[{markdown_safe(highlight)}]")
    heading = " ".join(parts)
    if icon:
        heading = f":gray[{icon}] {heading}"
    return f"{SECTION_HEADING}{heading}"


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
    """A panel's title row: the heading of :func:`section_title` (e.g.
    ``section_header("Delta", subtitle="vs", highlight="spot")`` → **Delta** vs spot), with
    an optional badge on the right.

    Returns the right-hand slot (a horizontal container) so a page can put a control there,
    like the React title rows::

        slot = section_header("Inputs", icon=":material/tune:")
        with slot:
            option_type = option_type_toggle(key="lab.type")
    """
    row = st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
        gap="small",
    )
    with row:
        st.markdown(
            section_title(title, subtitle=subtitle, highlight=highlight, icon=icon),
            help=safe_help(help),
            width="content",
            anchors=False,
        )
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

FIELD_WIDTH: Final = 96
"""Width in px of :func:`number_slider`'s numeric field (React: a 92 px column).

Streamlit adds +/- step buttons to a number input wider than 7.5rem (105 px with this
theme's 14 px base font), and they squeeze the value to four or five characters ("6312.4",
"0.082"). A 96 px field never grows them and shows "6312.45" whole in the mono font."""


def slider_keys(key: str) -> tuple[str, str]:
    """The BASE keys of the slider and of the numeric field behind :func:`number_slider`
    ``key`` (the canonical value lives at ``key`` itself). Each base has its own widget
    generation, so the widget keys are ``widget_key_in(state, base)`` (``"lab.S__slider__w0"``,
    see :mod:`eqd_desk.app.ui.inputs`): moving the slider remounts only the field, and typing
    in the field remounts only the slider."""
    return f"{key}__slider", f"{key}__input"


def _store(key: str, wkey: str, lo: float, hi: float, integer: bool) -> None:
    """Copy a widget's value to the canonical key, within the bounds (an emptied field keeps
    the previous value)."""
    raw = st.session_state.get(wkey)
    if raw is not None:
        v = clamp_number(float(raw), lo, hi, integer=integer)
        st.session_state[key] = int(v) if integer else v


def _on_edit(
    key: str,
    wkey: str,
    lo: float,
    hi: float,
    integer: bool,
    after: Callable[[], None] | None,
) -> None:
    """``on_change`` of the slider and of the field: store the new value as the canonical
    value (the other widget then disagrees and remounts at the new value on the next render),
    then run the caller's ``on_change``."""
    _store(key, wkey, lo, hi, integer)
    if after is not None:
        after()


def set_number(key: str, value: float) -> None:
    """Programmatically set a :func:`number_slider` (e.g. "Reset to snapshot", "σ ← surface").

    Call it from a widget callback (``on_click``/``on_change``) or before the slider renders
    in the run: it writes the canonical value and remounts both widgets, which show the new
    value when they render (clamped to the bounds).
    """
    st.session_state[key] = value
    for base in slider_keys(key):
        remount(base)


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
    field_width: int = FIELD_WIDTH,
) -> float:
    """A labelled numeric input: a header row (label, optional italic ``symbol`` like *S*,
    and a mono ``display`` of the value with units on the right), then a slider with a
    fixed-width numeric field beside it (React ``InputPanel`` ``Field``), both editing the
    same value; or the slider alone with ``compact=True`` (React ``LabeledSlider``).

    The canonical value lives in ``st.session_state[key]`` (a plain, non-widget key, so it
    survives page switches). The widgets are remount-safe (:mod:`eqd_desk.app.ui.inputs`):
    each is created with ``value=`` the canonical value under a generation-suffixed key
    derived from :func:`slider_keys`, so moving either one — or calling :func:`set_number`,
    or writing ``key`` from a callback — moves both, and a frontend remount never resets
    them to ``min_value``.

    Args:
        label: sentence-case label ("Spot", "Time to expiry").
        key: unique, page-prefixed session-state key ("lab.S").
        min_value, max_value, step: bounds and increment (the field clamps typed values).
        default: initial value (first run only); defaults to ``min_value``.
        display: text (or ``value -> text``) shown on the right of the header, e.g.
            ``lambda v: fmt_with_unit(fmt_level(v), "USD")``; ``None`` hides it.
        symbol: the variable's symbol, shown dim after the label ("S", "σ").
        slider_format: format of the slider thumb, a printf string (``"%.3f y"``) or a
            Streamlit preset: pass :data:`~eqd_desk.app.ui.format.THUMB_PERCENT` for a
            decimal shown as a percentage and :data:`~eqd_desk.app.ui.format.THUMB_LEVEL`
            for a level, so the thumb reads in the units of ``display``. Defaults to
            ``input_format``.
        input_format: printf format of the numeric field (``"%.4f"``).
        integer: integer-valued control (returns an ``int``).
        compact: slider only, no numeric field (React ``LabeledSlider``).
        help: tooltip on the label (plain text).
        on_change: extra callback after the value changed.
        disabled: grey out the widgets.
        field_width: width of the numeric field in px (default :data:`FIELD_WIDTH`, which
            keeps Streamlit's +/- buttons away; the slider takes the rest of the row).

    Returns:
        The current value.
    """
    slider_format = slider_format or input_format
    lo = clamp_number(min_value, min_value, None, integer=integer)
    hi = clamp_number(max_value, max_value, None, integer=integer)
    if key not in st.session_state:
        st.session_state[key] = lo if default is None else default
    value = clamp_number(float(st.session_state[key]), lo, hi, integer=integer)
    typed: float = int(value) if integer else value
    st.session_state[key] = typed
    slider_base, field_base = slider_keys(key)

    head = markdown_safe(label)
    if symbol:
        head += f" :gray[*{markdown_safe(symbol)}*]"
    shown = display(typed) if callable(display) else display
    lo_arg: float = int(lo) if integer else lo
    hi_arg: float = int(hi) if integer else hi
    step_arg: float = round(step) if integer else float(step)

    def slider() -> None:
        wkey = steady_key(slider_base, typed)
        st.slider(
            label,
            min_value=lo_arg,
            max_value=hi_arg,
            step=step_arg,
            value=typed,
            format=slider_format,
            key=wkey,
            on_change=_on_edit,
            args=(key, wkey, lo, hi, integer, on_change),
            label_visibility="collapsed",
            disabled=disabled,
            width="stretch",
        )

    with st.container(gap="xsmall"):
        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="bottom",
            gap="small",
        ):
            st.markdown(head, help=safe_help(help), width="content")
            if shown:
                st.markdown(f"`{shown}`", width="content")
        if compact:
            slider()
        else:
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                slider()
                wkey = steady_key(field_base, typed)
                st.number_input(
                    f"{label} value",
                    min_value=lo_arg,
                    max_value=hi_arg,
                    step=step_arg,
                    value=typed,
                    format=input_format,
                    key=wkey,
                    on_change=_on_edit,
                    args=(key, wkey, lo, hi, integer, on_change),
                    label_visibility="collapsed",
                    disabled=disabled,
                    width=field_width,
                )
    return typed


# ------------------------------------------------------------------ panel actions


def reset_inputs(values: Mapping[str, object]) -> None:
    """Set canonical keys to new values (a "Reset" callback) whatever widget shows each one
    (a :func:`number_slider`, a choice, a toggle or a number field): the value is written
    and every widget that can show the key is remounted, so each displays its new value
    on the next run. Call it from a callback, like :func:`set_number`."""
    for key, value in values.items():
        st.session_state[key] = value
        for base in (key, *slider_keys(key)):
            remount(base)


def reset_button(
    values: Mapping[str, object],
    *,
    key: str,
    help: str = "Restore the opening inputs",
    label: str = "Reset",
) -> None:
    """A full-width "Reset" button that restores ``values`` (canonical key → value) through
    :func:`reset_inputs`."""
    st.button(
        label,
        key=key,
        icon=":material/restart_alt:",
        help=safe_help(help),
        on_click=reset_inputs,
        args=(dict(values),),
        width="stretch",
    )


SURFACE_VOL_LABEL: Final = "σ ← surface"
"""Label of :func:`surface_vol_button` (React's button text)."""


def surface_vol_from(prefix: str) -> None:
    """Set ``<prefix>sigma`` to the seed vol surface at the strike ``<prefix>K`` and tenor
    ``<prefix>T`` (every input panel with a σ keys its inputs this way: ``"lab."``,
    ``"exo.bar."``). A callback: the sliders show the new σ on the next run."""
    K = float(st.session_state[f"{prefix}K"])
    T = float(st.session_state[f"{prefix}T"])
    set_number(f"{prefix}sigma", state.surface().get_vol(K, T))


def surface_vol_button(prefix: str, *, key: str | None = None) -> None:
    """React's "σ ← surface" (full width): snap σ to the seed surface at the current strike
    and tenor, to feel the skew (:func:`surface_vol_from`). ``key`` defaults to
    ``<prefix>surface``."""
    st.button(
        SURFACE_VOL_LABEL,
        key=key or f"{prefix}surface",
        icon=":material/ssid_chart:",
        help=safe_help(SURFACE_VOL_HINT),
        on_click=surface_vol_from,
        args=(prefix,),
        width="stretch",
    )


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
        help: tooltip on the label (plain text).
    """
    st.metric(
        markdown_safe(label),
        md_color(markdown_safe(value), tone),
        delta="" if detail else None,
        delta_description=markdown_safe(detail) if detail else None,
        border=True,
        help=safe_help(help),
    )


# ------------------------------------------------------------------ readout table


def readout_table(rows: Sequence[ReadoutRow]) -> None:
    """Render rows (:class:`~eqd_desk.app.ui.readout.ReadoutRow`) as a dense, right-aligned
    table (label · value · unit), group headings in small dim capitals and the selected row
    highlighted — React's ``.greeks-table``. The model and its styles are the pure
    :mod:`eqd_desk.app.ui.readout`."""
    if not rows:
        return
    st.table(readout_styler(rows), border="horizontal", hide_index=True, hide_header=True)


def greek_readout(
    values: Mapping[str, float] | HasAsDict,
    *,
    groups: Sequence[GreekGroup] | None = GREEK_GROUPS,
    keys: Sequence[str] | None = None,
    selected: str | None = None,
    currency: str | None = None,
) -> None:
    """Render :func:`~eqd_desk.app.ui.readout.greek_rows` as a :func:`readout_table` (every
    greek, grouped by order, in the desk units of ``currency``, the selected one
    highlighted)."""
    readout_table(
        greek_rows(values, groups=groups, keys=keys, selected=selected, currency=currency)
    )


# ------------------------------------------------------------------ choices


def choice[T: str](
    label: str,
    options: Mapping[T, str],
    *,
    key: str,
    default: T,
    kind: Literal["segmented", "pills"] = "segmented",
    help: str | None = None,
    label_visibility: LabelVisibility = "collapsed",
    on_change: Callable[[], None] | None = None,
) -> T:
    """A segmented control (or pills, ``kind="pills"``) over ``options`` (value → display
    label, Markdown) that always has a selection (``required``). The value lives at the
    canonical ``key`` for the session (remount-safe, see :mod:`eqd_desk.app.ui.inputs`);
    ``on_change`` runs after a user pick is stored there.

    Returns the selected VALUE (not its label).
    """
    return steady_choice(
        label,
        options,
        key=key,
        default=default,
        kind=kind,
        help=help,
        label_visibility=label_visibility,
        on_change=on_change,
    )


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
    on_change: Callable[[], None] | None = None,
) -> GreekKey:
    """The greek "chips" (React ``.edu-chips``): pills over ``options`` (price + every greek
    by default), one always selected; drives which greek is plotted and explained. The value
    lives at the canonical ``key`` (remount-safe, like :func:`choice`)."""
    return choice(
        label,
        {k: greek_label(k) for k in options},
        key=key,
        default=default,
        kind="pills",
        help=help,
        on_change=on_change,
    )


def toggle(
    label: str,
    *,
    key: str,
    default: bool = False,
    help: str | None = None,
    on_change: Callable[[], None] | None = None,
    disabled: bool = False,
) -> bool:
    """An on/off switch (``st.toggle``) whose value lives at the canonical ``key``, seeded
    with ``default`` (remount-safe, like :func:`choice`). Returns the current value."""
    return steady_toggle(
        label,
        key=key,
        default=default,
        help=help,
        on_change=on_change,
        disabled=disabled,
    )


__all__ = [
    "FIELD_WIDTH",
    "OPTION_TYPE_LABELS",
    "SECTION_HEADING",
    "SURFACE_VOL_LABEL",
    "BadgeColor",
    "HeaderStat",
    "app_header",
    "choice",
    "greek_label",
    "greek_picker",
    "greek_readout",
    "header_stats",
    "header_subtitle",
    "hero_number",
    "md_color",
    "number_slider",
    "option_type_toggle",
    "readout_table",
    "reset_button",
    "reset_inputs",
    "safe_help",
    "section_header",
    "section_title",
    "seed_badge_text",
    "set_number",
    "slider_keys",
    "sub_heading",
    "surface_vol_button",
    "surface_vol_from",
    "toggle",
]
