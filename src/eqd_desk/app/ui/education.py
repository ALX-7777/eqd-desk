"""Renderers for the teaching content (the "Learn" panels).

All prose comes from :mod:`eqd_desk.content` (ported verbatim from the React app) and goes
through :func:`~eqd_desk.content.markdown_safe` before reaching ``st.markdown``: the text is
plain and contains ``$`` (Streamlit would typeset ``$…$`` as LaTeX), ``*``, ``_`` and so on.
Nothing here re-types teaching text.

The look mirrors ``EducationPanel.tsx`` / ``StrategyEducation.tsx`` / ``ExoticInfo.tsx`` /
the simulator's Learn panel: a bordered card with a title and labelled fields (label in
small accent capitals-style bold, text below), relationships and concepts as expanders.

Typical use (a greeks-lab right column; the picker's key holds the selected greek)::

    selected = st.session_state.get("lab.greek", "delta")
    with st.container(border=True):
        learn_header(badge=greek_unit(selected, snap.currency))
        greek_picker(key="lab.greek")
        greek_doc_card(selected)
        key_relationships()
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from eqd_desk.app.ui.widgets import BadgeColor, section_header, sub_heading
from eqd_desk.content import (
    ATTRIBUTION_TERMS,
    EXOTIC_DOCS,
    GREEK_DOCS,
    KEY_RELATIONSHIPS,
    SIM_CONCEPTS,
    STRATEGY_DOCS,
    ExoticKind,
    GreekKey,
    PresetName,
    markdown_safe,
)
from eqd_desk.content.exotics import (
    EXOTIC_DOC_FIELD_LABELS,
    EXOTIC_GREEK_DOC_FIELDS,
    ExoticDocField,
)
from eqd_desk.content.greeks import GREEK_DOC_FIELD_LABELS, GreekDocField
from eqd_desk.content.strategies import (
    CUSTOM_STRUCTURE_NOTE,
    STRATEGY_DOC_FIELD_LABELS,
    StrategyDocField,
)

GREEK_DOC_FIELDS: tuple[GreekDocField, ...] = tuple(GREEK_DOC_FIELD_LABELS)
"""Every field of the greek card, in display order (measures, intuition, when large, desk)."""


def field_markdown(label: str, text: str) -> str:
    """One labelled field of a card as Markdown: a small accent label, the text below it.
    Both are escaped (plain teaching text in, safe Markdown out)."""
    return f":small[:primary[**{markdown_safe(label)}**]]  \n{markdown_safe(text)}"


def doc_fields(pairs: Sequence[tuple[str, str]]) -> None:
    """Render (label, text) pairs as stacked labelled fields (React ``<dl class="edu-dl">``)."""
    for label, text in pairs:
        st.markdown(field_markdown(label, text))


def card_title(title: str) -> None:
    """The title of an education card ("Delta (Δ)")."""
    st.markdown(f"##### {markdown_safe(title)}", anchors=False)


def teaching_caption(text: str) -> None:
    """A chart caption / hint from the content modules, rendered as a dim caption."""
    st.caption(markdown_safe(text))


def learn_header(
    *, badge: str | None = None, badge_color: BadgeColor = "gray", title: str = "Learn"
) -> None:
    """The "Learn" title row of an education panel, with an optional tag (the greek's unit,
    see :func:`~eqd_desk.app.ui.units.greek_unit`; the preset name, "exotic",
    "market-making")."""
    section_header(title, icon=":material/school:", badge=badge, badge_color=badge_color)


# ------------------------------------------------------------------ greeks


def greek_doc_card(key: GreekKey, *, fields: Sequence[GreekDocField] = GREEK_DOC_FIELDS) -> None:
    """The education card of one greek (or the price): title plus the chosen fields —
    measures, intuition, when it's large, on the desk (all four by default)."""
    doc = GREEK_DOCS[key]
    with st.container(border=True):
        card_title(doc.title)
        doc_fields([(GREEK_DOC_FIELD_LABELS[f], getattr(doc, f)) for f in fields])


def key_relationships(*, heading: str | None = "Key relationships") -> None:
    """The standing relationships every trainee must internalise (gamma↔theta, gamma vs vega
    across maturities, pin risk, the moving surface), one expander each."""
    if heading:
        sub_heading(heading)
    for rel in KEY_RELATIONSHIPS:
        with st.expander(markdown_safe(rel.title)):
            st.markdown(markdown_safe(rel.body))


# ------------------------------------------------------------------ strategies


STRATEGY_FIELDS: tuple[StrategyDocField, ...] = tuple(STRATEGY_DOC_FIELD_LABELS)
"""Every field of the strategy card, in display order (view, structure, greeks, risk)."""


def strategy_doc_card(preset: PresetName | None, *, title: str) -> None:
    """The desk rationale of a preset structure (the view, structure, greek signature,
    principal risk) titled with its display label; ``preset=None`` (legs edited by hand)
    shows only the dim "custom structure" note, untitled, as ``StrategyEducation.tsx`` does
    (the Learn header's tag already names the structure), so ``title`` is not shown then."""
    with st.container(border=True):
        if preset is None:
            st.markdown(f":gray[{markdown_safe(CUSTOM_STRUCTURE_NOTE)}]")
            return
        doc = STRATEGY_DOCS[preset]
        card_title(title)
        doc_fields([(STRATEGY_DOC_FIELD_LABELS[f], getattr(doc, f)) for f in STRATEGY_FIELDS])


# ------------------------------------------------------------------ exotics


EXOTIC_FIELDS: tuple[ExoticDocField, ...] = tuple(EXOTIC_DOC_FIELD_LABELS)
"""Every field of the exotic card, in display order (what it is, behaviour, risk)."""


def exotic_doc_card(kind: ExoticKind) -> None:
    """The desk card of an exotic: what it is, the behaviour that matters, principal risk."""
    doc = EXOTIC_DOCS[kind]
    with st.container(border=True):
        card_title(doc.title)
        doc_fields([(EXOTIC_DOC_FIELD_LABELS[f], getattr(doc, f)) for f in EXOTIC_FIELDS])


def exotic_greek_card(metric: GreekKey) -> None:
    """The short greek card shown beside an exotic: definition and intuition only
    (:data:`~eqd_desk.content.exotics.EXOTIC_GREEK_DOC_FIELDS`)."""
    greek_doc_card(metric, fields=EXOTIC_GREEK_DOC_FIELDS)


# ------------------------------------------------------------------ simulator


def sim_concepts(*, heading: str | None = None) -> None:
    """The market-making concepts (the loop, spread vs fill, gamma scalping, …), one
    expander each, in reading order."""
    if heading:
        sub_heading(heading)
    for concept in SIM_CONCEPTS:
        with st.expander(markdown_safe(concept.title)):
            st.markdown(markdown_safe(concept.body))


def attribution_terms(*, heading: str | None = "P&L explain terms") -> None:
    """How to read each bar of the P&L explain (delta, gamma, theta, vega, vanna, volga,
    residual), as labelled fields."""
    if heading:
        sub_heading(heading)
    doc_fields([(t.label, t.note) for t in ATTRIBUTION_TERMS])


__all__ = [
    "EXOTIC_FIELDS",
    "GREEK_DOC_FIELDS",
    "STRATEGY_FIELDS",
    "attribution_terms",
    "card_title",
    "doc_fields",
    "exotic_doc_card",
    "exotic_greek_card",
    "field_markdown",
    "greek_doc_card",
    "key_relationships",
    "learn_header",
    "sim_concepts",
    "strategy_doc_card",
    "teaching_caption",
]
