"""The readout table as data: rows, their text and colours, and the Pandas Styler that draws
them (React ``.greeks-table``: label · right-aligned mono value · dim unit, grouped under
small capitals headings, the selected row highlighted).

Pure (Pandas, no Streamlit), so every page's rows and styles are unit-testable; the
Streamlit half is :func:`eqd_desk.app.ui.widgets.readout_table`, which renders
:func:`readout_styler` with ``st.table``.

Line breaking. ``st.table`` clips a table wider than its column (no horizontal scroll), and
its cells are Markdown, which ignores CSS ``white-space``, so what may wrap is decided in the
text itself, to let the table shrink to a narrow column (a 1280 px laptop) instead:

- values never wrap (mono, no spaces; :func:`value_text` keeps an exponent's ``e-7`` whole);
- units wrap between words (:func:`unit_text`), never inside a quantity ("$1 spot",
  "1 vol pt") nor leaving an operator alone at the start or end of a line;
- labels wrap only at spaces, and only when the column is too narrow for them; a hyphenated
  word stays whole (:func:`label_text`: "Down‑out", never "Down-" / "out");
- group headings sit on one line (:func:`keep_together`) and overflow into the empty value
  and unit cells.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, Protocol

import pandas as pd

from eqd_desk.app.ui import theme
from eqd_desk.app.ui.format import fmt_num, sign_class
from eqd_desk.app.ui.theme import TONE_COLORS, Tone
from eqd_desk.app.ui.units import greek_unit
from eqd_desk.content import markdown_safe
from eqd_desk.content.greeks import GREEK_GROUPS, GreekGroup
from eqd_desk.engine import GREEK_UNITS

if TYPE_CHECKING:
    from pandas.io.formats.style import Styler

RowKind = Literal["row", "group"]
"""A value row, or a group heading ("First order")."""

RowTone = Tone | Literal["text"]
"""Colour of a row's value: a theme :data:`~eqd_desk.app.ui.theme.Tone`, or ``"text"`` for
the plain body colour (probabilities, levels and vols, which React prints uncoloured)."""

NBSP: Final = "\u00a0"
"""Non-breaking space."""

NB_HYPHEN: Final = "\u2011"
"""Non-breaking hyphen."""

WORD_JOINER: Final = "\u2060"
"""Invisible, zero-width: no line break on either side of it."""


@dataclass(frozen=True, slots=True)
class ReadoutRow:
    """One line of a readout table: label · right-aligned mono value · dim unit."""

    label: str
    value: float = math.nan
    """The number (kept numeric so the column right-aligns)."""
    text: str | None = None
    """Display text; default :func:`~eqd_desk.app.ui.format.fmt_num` of ``value``."""
    unit: str = ""
    tone: RowTone | None = None
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


def row_tone(row: ReadoutRow) -> RowTone:
    """The value colour of a row: its explicit tone, else the sign of its value."""
    return row.tone if row.tone is not None else sign_class(row.value)


def tone_color(tone: RowTone) -> str:
    """Hex colour of a value tone (``"text"`` is the body text colour)."""
    return theme.TEXT if tone == "text" else TONE_COLORS[tone]


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
    if row.selected:
        label += f"; box-shadow: inset 2px 0 0 {theme.ACCENT}"
    value = (
        sel
        + f"font-family: {theme.MONO_FONT}; font-variant-numeric: tabular-nums; "
        + f"font-weight: 600; white-space: nowrap; color: {tone_color(row_tone(row))}"
    )
    unit = sel + f"color: {theme.TEXT_DIM}; font-size: 11px"
    return label, value, unit


# ------------------------------------------------------------------ line breaking

_GLUED_SPACES: Final = re.compile(r"(?<=\d) | (?=pt\b)| (?==)|(?<=[−÷×+]) ")
"""Spaces a unit must not break at: after a digit ("$1 spot", "1 vol"), before "pt", before
"=" ("desk =") and after an arithmetic operator ("− ATM"), so no line of a unit starts with
"=" or ends with a bare operator."""


def keep_together(text: str) -> str:
    """``text`` on one line: every space and hyphen made non-breaking."""
    return text.replace(" ", NBSP).replace("-", NB_HYPHEN)


def label_text(label: str) -> str:
    """A row label as the label column prints it: hyphens made non-breaking, so a word like
    "Down-out" never splits at its hyphen; the label may still wrap at a space when the
    column is too narrow for all of it."""
    return label.replace("-", NB_HYPHEN)


def value_text(text: str) -> str:
    """A value as the value column prints it: never split after a hyphen (a browser would
    break ``-9.56186e-7`` after its ``e-``). A word joiner follows each hyphen, so the text
    looks, and copies, the same."""
    return text.replace("-", "-" + WORD_JOINER)


def unit_text(unit: str) -> str:
    """A unit as the unit column prints it: breakable between its words, but not inside a
    quantity or next to an operator (:data:`_GLUED_SPACES`): ``"Δdelta per $1 spot"`` may
    break as "Δdelta" / "per" / "$1 spot", ``"per 1 vol pt"`` only after "per", and
    ``"desk = raw ÷100"`` as "desk =" / "raw" / "÷100"."""
    return _GLUED_SPACES.sub(NBSP, unit)


# ------------------------------------------------------------------ the table


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


def _const(text: str) -> Callable[[object], str]:
    """A Styler formatter that ignores the cell value and prints ``text``."""
    return lambda _value: text


def readout_styler(rows: Sequence[ReadoutRow]) -> Styler:
    """A Pandas Styler: display text per row (the value column stays numeric, so Streamlit
    right-aligns it), the line breaking of the module docstring (:func:`label_text`,
    :func:`value_text`, :func:`unit_text`; :func:`keep_together` for a heading) and the
    per-cell CSS of
    :func:`row_styles`."""
    df = readout_frame(rows)
    styles = [row_styles(r) for r in rows]
    sty = df.style.hide(axis="index")
    for i, r in enumerate(rows):
        # (slice(i, i), slice(c, c)) is the single cell (i, c) under label-based .loc rules.
        label = markdown_safe(r.label)
        cells = {
            "label": keep_together(label) if r.kind == "group" else label_text(label),
            "value": value_text(markdown_safe(row_text(r))),
            "unit": unit_text(markdown_safe(r.unit)),
        }
        for column, text in cells.items():
            sty = sty.format(_const(text), subset=(slice(i, i), slice(column, column)))
    return sty.apply(
        lambda frame: pd.DataFrame(styles, index=frame.index, columns=frame.columns), axis=None
    )


# ------------------------------------------------------------------ greeks


class HasAsDict(Protocol):
    """Anything that exposes its fields as a dict (engine ``Greeks``, ``ExoticGreeks``)."""

    def as_dict(self) -> dict[str, float]: ...


def greek_rows(
    values: Mapping[str, float] | HasAsDict,
    *,
    groups: Sequence[GreekGroup] | None = GREEK_GROUPS,
    keys: Sequence[str] | None = None,
    selected: str | None = None,
    currency: str | None = None,
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
        currency: premium currency of the units (``"per €1 spot"`` for EUR, see
            :func:`~eqd_desk.app.ui.units.greek_unit`); ``None`` keeps the engine's
            wording.
    """
    data = values if isinstance(values, Mapping) else values.as_dict()

    def row(k: str) -> ReadoutRow:
        return ReadoutRow(
            GREEK_UNITS[k].label,
            float(data[k]),
            unit=greek_unit(k, currency),
            selected=k == selected,
        )

    if groups is None:
        return [row(k) for k in (keys or ())]
    out: list[ReadoutRow] = []
    for g in groups:
        out.append(group_row(g.title))
        out.extend(row(k) for k in g.keys)
    return out


__all__ = [
    "NBSP",
    "NB_HYPHEN",
    "WORD_JOINER",
    "HasAsDict",
    "ReadoutRow",
    "RowKind",
    "RowTone",
    "greek_rows",
    "group_row",
    "keep_together",
    "label_text",
    "readout_frame",
    "readout_styler",
    "row_styles",
    "row_text",
    "row_tone",
    "tone_color",
    "unit_text",
    "value_text",
]
