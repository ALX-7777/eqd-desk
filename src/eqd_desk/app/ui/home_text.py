"""The overview page's derived text (pure: no Streamlit).

- :func:`skew_source`: where the seed smile's SHAPE came from, a fit to the options proxy's
  listed chain or the parametric fallback, so the page never claims a fit that did not
  happen.
- :func:`note_markdown`: a snapshot source note as Markdown, with its inline code (the
  refresh command) kept as code.
- :func:`structure_ideas`: the key ideas on the Strategy-builder tool card, the view each
  headline structure expresses.
- :data:`BSM_LATEX`: the pricing formulas shown under "How the numbers are computed".
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from eqd_desk.content import markdown_safe
from eqd_desk.engine.presets import PRESETS, PresetName

# ------------------------------------------------------------------ skew provenance


@dataclass(frozen=True, slots=True)
class SkewSource:
    """Where the seed smile's shape (slope and curvature in log-moneyness) came from.

    The ATM LEVEL always comes from the vol index; only the shape has two possible sources.
    """

    fitted: bool
    """``True``: fitted to the options proxy's listed chain; ``False``: the parametric
    equity-skew fallback (the committed static seed, or a refresh whose chain fetch failed)."""
    tag: str
    """Short tag for the smile chart title: ``"SPY shape"`` or ``"parametric shape"``."""
    detail: str
    """Markdown for the provenance table, the ticker as inline code."""


def skew_is_fallback(notes: Iterable[str]) -> bool:
    """Do the snapshot's source notes say the skew shape is the parametric fallback?

    The snapshot JSON has no structured field for this; ``scripts/fetch_snapshot.py``
    records it in ``source_notes`` ("proxy SPY skew unavailable; using parametric
    fallback"), and the committed static seed says its "skew shape (...) is a parametric
    equity-skew fallback". A note that names both the skew and a fallback marks it; a note
    about another fallback (the whole "STATIC FALLBACK SEED", a missing vol index) does not.
    ``tests/ui/test_home_text.py`` runs the script offline to keep this in step with it.
    """
    return any("skew" in n.lower() and "fallback" in n.lower() for n in notes)


def skew_source(notes: Iterable[str], proxy: str) -> SkewSource:
    """The skew provenance for a snapshot with these source ``notes``.

    Args:
        notes: the snapshot's ``source_notes``.
        proxy: the listed ETF whose chain a refresh fits the shape to (e.g. ``"SPY"``).
    """
    if skew_is_fallback(notes):
        return SkewSource(
            fitted=False,
            tag="parametric shape",
            detail=f"Parametric fallback (a refresh fits the `{proxy}` chain)",
        )
    return SkewSource(fitted=True, tag=f"{proxy} shape", detail=f"`{proxy}` option chain")


# ------------------------------------------------------------------ source notes

_CODE_SPAN: Final = re.compile(r"`[^`\n]+`")
"""A single-backtick inline code span on one line (the notes never nest backticks)."""


def note_markdown(note: str) -> str:
    """A source note as Markdown: the prose escaped with
    :func:`~eqd_desk.content.markdown_safe` (so ``$``, ``*``, ``~`` stay literal), but each
    inline code span (text between single backticks) kept as code, so a refresh command
    renders as code rather than with literal backticks. A lone, unmatched backtick is
    escaped like the prose.
    """
    parts: list[str] = []
    pos = 0
    for span in _CODE_SPAN.finditer(note):
        parts.append(markdown_safe(note[pos : span.start()]))
        parts.append(span.group(0))
        pos = span.end()
    parts.append(markdown_safe(note[pos:]))
    return "".join(parts)


# ------------------------------------------------------------------ tool-card ideas

STRUCTURE_VIEWS: Final[Mapping[PresetName, str]] = MappingProxyType(
    {
        "straddle": "realised vs implied vol",
        "risk-reversal": "a skew bet",
        "butterfly": "a vol-of-vol bet",
        "calendar": "a term-structure bet",
    }
)
"""The view each headline structure expresses, condensed from its
:data:`~eqd_desk.content.STRATEGY_DOCS` entry (the Strategy builder's Learn panel)."""


def structure_ideas() -> list[str]:
    """The Strategy-builder card's key ideas, in preset display order: "Risk reversal — a
    skew bet", and so on."""
    return [f"{p.label} — {STRUCTURE_VIEWS[p.name]}" for p in PRESETS if p.name in STRUCTURE_VIEWS]


# ------------------------------------------------------------------ formulas

BSM_ROWS: Final = (
    r"d_1 &= \frac{\ln(S/K) + (r - q + \tfrac{1}{2}\sigma^2)\,T}{\sigma\sqrt{T}}",
    r"d_2 &= d_1 - \sigma\sqrt{T}",
    r"C &= S e^{-qT} N(d_1) - K e^{-rT} N(d_2)",
    r"P &= K e^{-rT} N(-d_2) - S e^{-qT} N(-d_1)",
)
"""The rows of :data:`BSM_LATEX`, each aligned at its ``&=``."""

BSM_LATEX: Final = r"\begin{aligned}" + r" \\[2pt] ".join(BSM_ROWS) + r"\end{aligned}\,"
"""Black–Scholes–Merton with a continuous dividend yield (``eqd_desk.engine.bsm``), ONE
formula per row, aligned on "=": d1 and d2, then the call and the put. One row each keeps
every line narrow enough for a phone-width card; two formulas side by side overflowed it,
hiding the second behind an unmarked horizontal scroll.

The trailing thin space (``\\,``, about 3 px) is not decoration: KaTeX's table columns end
in a 2 px strut that hangs past their measured width, and Streamlit sizes the formula's box
to that measured width, so without it the box scrolls by 2 px and browsers with classic
scrollbars (Windows) draw a horizontal scrollbar under the formulas."""
