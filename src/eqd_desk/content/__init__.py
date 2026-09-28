"""In-app teaching content: the plain-language, desk-flavoured explanations that make
education a first-class feature of EQD Desk (a visible panel beside every tool, not a
tooltip). Pure data, no UI dependency.

Ported VERBATIM from the React app (``web/``, the spec), one module per tool:

- :mod:`eqd_desk.content.greeks`: ``web/src/components/education.ts``, plus prose from
  ``EducationPanel.tsx``, ``GreeksReadout.tsx``, ``PlotsPanel.tsx`` and ``InputPanel.tsx``.
- :mod:`eqd_desk.content.strategies`: ``web/src/components/strategyDocs.ts``, plus prose
  from ``StrategyEducation.tsx``, ``StrategyPlots.tsx``, ``PositionReadout.tsx`` and
  ``LegsEditor.tsx``.
- :mod:`eqd_desk.content.exotics`: ``web/src/components/exoticsDocs.ts``, plus prose from
  ``ExoticInfo.tsx``, ``ExoticsLab.tsx`` and ``exotics/*View.tsx``.
- :mod:`eqd_desk.content.simulator`: ``web/src/components/simDocs.ts``, plus prose from
  ``SimulatorView.tsx``.

The doc objects of the ``.ts`` files are checked string-for-string against the TypeScript
by ``tests/parity/test_content_parity.py`` (golden exported by
``web/scripts/golden/content.golden.ts``). The prose lifted out of ``.tsx`` markup carries
a ``file:line`` comment, and the same test finds it in that ``.tsx`` source.

The main doc objects are re-exported here; the per-tool captions and labels are imported
from their module::

    from eqd_desk.content import GREEK_DOCS, markdown_safe
    from eqd_desk.content.greeks import greek_sweep_caption

    GREEK_DOCS["gamma"].when_large  # "Sharply peaked at-the-money and explodes as T → 0. …"

Text format
-----------
Every string is PLAIN TEXT: the React UI renders it as-is (no Markdown, no HTML, no
**bold** or backticks). Emphasis is written in CAPITALS ("REALISED vol", "LONG-dated") and
the maths is inline Unicode (Γ, σ, Δ, √, ≈, ½, ², →, ·, −). A few strings contain characters
that Markdown or Streamlit would interpret, most importantly ``$`` (Streamlit typesets
``$…$`` as LaTeX; delta's definition says "a $1 move"). A UI rendering through
``st.markdown`` should therefore pass text through :func:`markdown_safe`, or use a
plain-text element.
"""

from __future__ import annotations

from typing import Final

from eqd_desk.content.exotics import (
    EXOTIC_DOCS,
    EXOTIC_KINDS,
    EXOTIC_METRICS,
    ExoticDoc,
    ExoticKind,
    ExoticMetric,
)
from eqd_desk.content.greeks import (
    GREEK_DOCS,
    GREEK_KEYS,
    KEY_RELATIONSHIPS,
    PLOTTABLE_KEYS,
    GreekDoc,
    GreekKey,
    Relationship,
)
from eqd_desk.content.simulator import (
    ATTRIBUTION_TERMS,
    SIM_CONCEPTS,
    AttributionTerm,
    SimConcept,
)
from eqd_desk.content.strategies import PRESET_NAMES, STRATEGY_DOCS, PresetName, StrategyDoc

MARKDOWN_SPECIAL_CHARS: Final = frozenset("\\`*_[]<>#|~$")
"""Characters :func:`markdown_safe` escapes: those with a meaning in CommonMark, GitHub
Markdown or Streamlit's ``st.markdown`` that can occur mid-sentence in plain text."""


def markdown_safe(text: str) -> str:
    """Backslash-escape the characters Markdown would interpret, so plain teaching text
    renders literally through ``st.markdown`` (or any CommonMark renderer).

    ``$`` matters most: Streamlit typesets ``$…$`` as inline LaTeX, so two dollar signs in
    one block (delta's "a $1 move" beside its "per $1 spot" unit, say) would turn the text
    between them into maths. The others: ``*``/``_`` (emphasis), backticks (code), ``[ ]``
    (links, and Streamlit's ``:color[…]`` directives), ``< >`` (HTML), ``#`` (headings),
    ``|`` (tables), ``~`` (strikethrough) and the backslash itself. CommonMark treats a
    backslash before any ASCII punctuation as an escape, so the rendered text is exactly
    the original.
    """
    return "".join(f"\\{c}" if c in MARKDOWN_SPECIAL_CHARS else c for c in text)


__all__ = [
    "ATTRIBUTION_TERMS",
    "EXOTIC_DOCS",
    "EXOTIC_KINDS",
    "EXOTIC_METRICS",
    "GREEK_DOCS",
    "GREEK_KEYS",
    "KEY_RELATIONSHIPS",
    "MARKDOWN_SPECIAL_CHARS",
    "PLOTTABLE_KEYS",
    "PRESET_NAMES",
    "SIM_CONCEPTS",
    "STRATEGY_DOCS",
    "AttributionTerm",
    "ExoticDoc",
    "ExoticKind",
    "ExoticMetric",
    "GreekDoc",
    "GreekKey",
    "PresetName",
    "Relationship",
    "SimConcept",
    "StrategyDoc",
    "markdown_safe",
]
