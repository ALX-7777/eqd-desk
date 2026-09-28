"""The Python teaching content is the TypeScript text, string for string.

Two kinds of source:

1. The doc objects of ``web/src/components/*.ts`` (education.ts, strategyDocs.ts,
   exoticsDocs.ts, simDocs.ts): compared with the golden exported by
   ``web/scripts/golden/content.golden.ts``, field by field (TS camelCase → snake_case).
2. The prose lifted out of ``.tsx`` markup (captions, card headings, hints, messages): not
   importable as data, so each string is looked up LITERALLY in its ``.tsx`` source after
   applying JSX's text rules (whitespace runs collapse to one space; ``&amp;``/``&apos;``
   decode), together with enough surrounding code to pin what it is attached to:
   - a card heading with the ``<dd>{doc.field}</dd>`` it introduces (whole ``<dl>``);
   - a caption / hint as the whole JSX text node it is (bounded by its tags);
   - a mapping value (e.g. premium side, RFQ verdict, hedge role) inside its whole ternary;
   - a message template with each placeholder replaced by the exact JS expression that
     fills it (so dropped text, renamed or swapped placeholders fail).
   Regression tests at the end confirm these checks reject such mutations. Skipped when
   the TypeScript sources are not present.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from string import Formatter
from typing import Any

import pytest

from eqd_desk.content import exotics, greeks, simulator, strategies
from tests.parity.golden_io import load_golden

GOLDEN = load_golden("content")

GREEK_FIELDS = {
    "key": "key",
    "title": "title",
    "order": "order",
    "measures": "measures",
    "intuition": "intuition",
    "whenLarge": "when_large",
    "desk": "desk",
}
STRATEGY_FIELDS = {f: f for f in ("name", "view", "structure", "greeks", "risk")}
EXOTIC_FIELDS = {f: f for f in ("kind", "title", "what", "behaviour", "risk")}
TITLE_BODY = {"title": "title", "body": "body"}
TERM_FIELDS = {"key": "key", "label": "label", "note": "note"}


def _assert_same(
    py_obj: object, ts_obj: dict[str, Any], fields: dict[str, str], where: str
) -> None:
    """Every TS field is mapped (no field silently dropped) and every string is identical."""
    assert set(ts_obj) == set(fields), f"{where}: TS fields {sorted(ts_obj)}"
    for ts_name, py_name in fields.items():
        assert getattr(py_obj, py_name) == ts_obj[ts_name], f"{where}.{py_name}"


# ------------------------------------------------------------ 1. doc objects vs golden


def test_greek_key_lists() -> None:
    assert list(greeks.GREEK_KEYS) == GOLDEN["greekKeys"]
    assert list(greeks.PLOTTABLE_KEYS) == GOLDEN["plottableKeys"]


def test_greek_docs() -> None:
    ts_docs: dict[str, dict[str, Any]] = GOLDEN["greekDocs"]
    assert list(greeks.GREEK_DOCS) == list(ts_docs)  # same keys, same display order
    for key, ts_doc in ts_docs.items():
        _assert_same(greeks.GREEK_DOCS[key], ts_doc, GREEK_FIELDS, f"GREEK_DOCS[{key}]")  # type: ignore[index]


def test_key_relationships() -> None:
    ts_rels: list[dict[str, Any]] = GOLDEN["keyRelationships"]
    assert len(greeks.KEY_RELATIONSHIPS) == len(ts_rels)
    for i, (py_rel, ts_rel) in enumerate(zip(greeks.KEY_RELATIONSHIPS, ts_rels, strict=True)):
        _assert_same(py_rel, ts_rel, TITLE_BODY, f"KEY_RELATIONSHIPS[{i}]")


def test_preset_names_match_the_typescript_engine() -> None:
    assert list(strategies.PRESET_NAMES) == [p["name"] for p in GOLDEN["presets"]]


def test_strategy_docs() -> None:
    ts_docs: dict[str, dict[str, Any]] = GOLDEN["strategyDocs"]
    assert list(strategies.STRATEGY_DOCS) == list(ts_docs)
    for name, ts_doc in ts_docs.items():
        py_doc = strategies.STRATEGY_DOCS[name]  # type: ignore[index]
        _assert_same(py_doc, ts_doc, STRATEGY_FIELDS, f"STRATEGY_DOCS[{name}]")


def test_exotic_docs_and_metrics() -> None:
    assert list(exotics.EXOTIC_METRICS) == GOLDEN["exoticMetrics"]
    ts_docs: dict[str, dict[str, Any]] = GOLDEN["exoticDocs"]
    assert list(exotics.EXOTIC_DOCS) == list(ts_docs)
    assert list(exotics.EXOTIC_KINDS) == list(ts_docs)
    for kind, ts_doc in ts_docs.items():
        py_doc = exotics.EXOTIC_DOCS[kind]  # type: ignore[index]
        _assert_same(py_doc, ts_doc, EXOTIC_FIELDS, f"EXOTIC_DOCS[{kind}]")


def test_sim_concepts() -> None:
    ts_concepts: list[dict[str, Any]] = GOLDEN["simConcepts"]
    assert len(simulator.SIM_CONCEPTS) == len(ts_concepts)
    for i, (py_c, ts_c) in enumerate(zip(simulator.SIM_CONCEPTS, ts_concepts, strict=True)):
        _assert_same(py_c, ts_c, TITLE_BODY, f"SIM_CONCEPTS[{i}]")


def test_attribution_terms() -> None:
    ts_terms: list[dict[str, Any]] = GOLDEN["attributionTerms"]
    assert len(simulator.ATTRIBUTION_TERMS) == len(ts_terms)
    for i, (py_t, ts_t) in enumerate(zip(simulator.ATTRIBUTION_TERMS, ts_terms, strict=True)):
        _assert_same(py_t, ts_t, TERM_FIELDS, f"ATTRIBUTION_TERMS[{i}]")


# ------------------------------------------------------ 2. prose lifted from .tsx markup

COMPONENTS = Path(__file__).resolve().parents[2] / "web" / "src" / "components"
needs_tsx = pytest.mark.skipif(
    not COMPONENTS.is_dir(), reason="TypeScript sources (web/src/components) not present"
)


@cache
def _jsx_text(file: str) -> str:
    """A .tsx source as JSX renders its text: whitespace runs → one space, entities decoded."""
    src = (COMPONENTS / file).read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", src).replace("&amp;", "&").replace("&apos;", "'")


def _pattern(*fragments: str) -> str:
    """Regex matching the fragments, each taken LITERALLY, in order within one source span.

    Only the gap between consecutive fragments is free (and may not leave a table row, so a
    readout row's label and note stay together); nothing inside a fragment is a wildcard."""
    return "(?:(?!</tr>).)*?".join(re.escape(f) for f in fragments)


def _row(note: exotics.ReadoutNote) -> tuple[str, ...]:
    return (
        f'<td className="g-label">{note.label}</td>',
        f'<td className="g-unit dim">{note.note}</td>',
    )


def _group(g: greeks.GreekGroup) -> str:
    keys = ", ".join(f"'{k}'" for k in g.keys)
    return f"{{ title: '{g.title}', keys: [{keys}] }}"


def _card[F: str](obj: str, labels: Mapping[F, str], ts_fields: Mapping[str, str]) -> str:
    """An education card's ``<dl>`` exactly as the source writes it: each ``<dt>`` heading
    followed by the ``<dd>{obj.<tsField>}</dd>`` it introduces, in display order, with no
    other row. Pins every heading to its field (a swapped label map fails), the order,
    and that the map covers the whole card. ``ts_fields`` maps TS field → Python field."""
    ts_name = {py: ts for ts, py in ts_fields.items()}
    rows = " ".join(
        f"<dt>{label}</dt> <dd>{{{obj}.{ts_name[field]}}}</dd>" for field, label in labels.items()
    )
    return f'<dl className="edu-dl"> {rows} </dl>'


# (source file under web/src/components, fragments that must appear there in order)
TSX_PROSE: list[tuple[str, tuple[str, ...]]] = [
    # greeks lab
    ("EducationPanel.tsx", (_card("doc", greeks.GREEK_DOC_FIELD_LABELS, GREEK_FIELDS),)),
    *[("GreeksReadout.tsx", (_group(g),)) for g in greeks.GREEK_GROUPS],
    *[("PositionReadout.tsx", (_group(g),)) for g in greeks.GREEK_GROUPS],
    ("PlotsPanel.tsx", (f"'{greeks.GREEK_SWEEP_CAPTION_SUFFIXES['S']}'",)),
    ("InputPanel.tsx", (f'title="{greeks.SURFACE_VOL_HINT}"',)),
    # strategy builder
    (
        "StrategyEducation.tsx",
        (_card("doc", strategies.STRATEGY_DOC_FIELD_LABELS, STRATEGY_FIELDS),),
    ),
    ("PositionReadout.tsx", (f'title="{strategies.NET_PREMIUM_NOTE}"',)),
    (
        "PositionReadout.tsx",  # :54 — premium_side() ↔ `isDebit` (price >= 0)
        (
            f"{{isDebit ? '{strategies.PREMIUM_SIDE_NOTES['debit']}' : "
            f"'{strategies.PREMIUM_SIDE_NOTES['credit']}'}}",
        ),
    ),
    # exotics
    ("ExoticInfo.tsx", (_card("doc", exotics.EXOTIC_DOC_FIELD_LABELS, EXOTIC_FIELDS),)),
    (
        "ExoticInfo.tsx",
        (
            _card(
                "greek",
                {f: greeks.GREEK_DOC_FIELD_LABELS[f] for f in exotics.EXOTIC_GREEK_DOC_FIELDS},
                GREEK_FIELDS,
            ),
        ),
    ),
    (
        "ExoticsLab.tsx",  # :13-18 — the whole tab list, in order
        (
            "= [ "
            + " ".join(
                f"{{ value: '{k}', label: '{v}' }}," for k, v in exotics.EXOTIC_TAB_LABELS.items()
            )
            + " ]",
        ),
    ),
    ("exotics/DigitalView.tsx", (f"'{exotics.DIGITAL_PRICE_CAPTION}'",)),
    ("exotics/DigitalView.tsx", (f"'{exotics.DIGITAL_GREEK_CAPTION}'",)),
    ("exotics/AutocallView.tsx", (f'title="{exotics.AUTOCALL_MEMORY_HINT}"',)),
    *[("exotics/AutocallView.tsx", _row(n)) for n in exotics.AUTOCALL_DIAGNOSTICS],
    (
        "exotics/VarSwapView.tsx",
        (
            f"<span>{exotics.VARSWAP_FAIR_VOL_NOTE.label}</span>",
            f'<span className="dim">{exotics.VARSWAP_FAIR_VOL_NOTE.note}</span>',
        ),
    ),
    *[("exotics/VarSwapView.tsx", _row(n)) for n in exotics.VARSWAP_READOUT],
    # simulator
    (
        "SimulatorView.tsx",  # :414 — each verdict's hint, whole ternary
        (
            f"title={{v === 'hedges' ? '{simulator.RFQ_VERDICT_HINTS['hedges']}' : "
            f"v === 'adds' ? '{simulator.RFQ_VERDICT_HINTS['adds']}' : ''}}",
        ),
    ),
    (
        "SimulatorView.tsx",  # :672 — the React UI prefixes a decorative icon, not ported
        (f'<span className="joint-title">⚖︎ {simulator.JOINT_HEDGE_TITLE}</span>',),
    ),
    (
        "SimulatorView.tsx",  # :684 — joint_hedge_role(), whole ternary
        (
            f"{{l.instrument === 'future' ? '{simulator.JOINT_HEDGE_ROLE_LABELS['future']}' : "
            f"l.tenorDays && l.tenorDays <= {simulator.JOINT_HEDGE_GAMMA_MAX_TENOR_DAYS} ? "
            f"'{simulator.JOINT_HEDGE_ROLE_LABELS['gamma']}' : "
            f"'{simulator.JOINT_HEDGE_ROLE_LABELS['vega']}'}}",
        ),
    ),
]


@needs_tsx
@pytest.mark.parametrize(
    ("file", "fragments"), TSX_PROSE, ids=[f"{f}:{fr[0][:32]}" for f, fr in TSX_PROSE]
)
def test_tsx_prose_matches_its_source(file: str, fragments: tuple[str, ...]) -> None:
    assert re.search(_pattern(*fragments), _jsx_text(file)), f"{fragments} not found in {file}"


# Captions and hints that are a JSX text node of their own: the Python string must be the
# WHOLE node (bounded by its tags; the optional space is a collapsed line break), so a
# truncated string, or one with a sentence dropped at either end, fails.
TSX_TEXT_NODES: list[tuple[str, str]] = [
    ("PlotsPanel.tsx", greeks.PAYOFF_CAPTION),
    ("StrategyEducation.tsx", strategies.CUSTOM_STRUCTURE_NOTE),
    ("StrategyPlots.tsx", strategies.PAYOFF_CAPTION),
    ("LegsEditor.tsx", strategies.EMPTY_LEGS_HINT),
    ("exotics/BarrierView.tsx", exotics.BARRIER_CHART_CAPTION),
    ("exotics/AutocallView.tsx", exotics.AUTOCALL_PATHS_CAPTION),
    ("exotics/VarSwapView.tsx", exotics.VARSWAP_SKEW_HINT),
    ("exotics/VarSwapView.tsx", exotics.VARSWAP_STRIP_CAPTION),
    ("SimulatorView.tsx", simulator.REPLAY_LENGTH_HINT),
    ("SimulatorView.tsx", simulator.EPISODE_ENDED_MESSAGE),
    ("SimulatorView.tsx", simulator.EMPTY_QUEUE_HINT),
    ("SimulatorView.tsx", simulator.OPTION_HEDGE_CAPTION),
    ("SimulatorView.tsx", simulator.EMPTY_BOOK_HINT),
    ("SimulatorView.tsx", simulator.ADVISOR_SUBTITLE),
    ("SimulatorView.tsx", simulator.JOINT_HEDGE_SUBTITLE),
]


def _text_node(text: str) -> str:
    return "> ?" + re.escape(text) + " ?<"


@needs_tsx
@pytest.mark.parametrize(
    ("file", "text"), TSX_TEXT_NODES, ids=[f"{f}:{t[:32]}" for f, t in TSX_TEXT_NODES]
)
def test_tsx_text_node_matches_its_source(file: str, text: str) -> None:
    assert re.search(_text_node(text), _jsx_text(file)), f"{text!r} is not a whole node of {file}"


# Message templates: each ``{placeholder}`` is replaced by the EXACT JS expression that fills
# it in the source, and the result must appear verbatim between the given delimiters. So a
# template cannot drop or add static text, rename a placeholder, or swap two of them (the
# fill message showing the edge as the price would fail).
# (source file, Python template, {placeholder: JS source expression}, text before, text after)
TSX_TEMPLATES: list[tuple[str, str, dict[str, str], str, str]] = [
    (
        "SimulatorView.tsx",  # :370 — JSX text with one embedded expression
        simulator.REPLAY_CAPTION_TEMPLATE,
        {"count": "{historyMeta.count}"},
        ">",
        "</div>",
    ),
    (
        "SimulatorView.tsx",  # :235 — JS template literal
        simulator.FILL_MESSAGE_TEMPLATE,
        {
            "side": "${f.youSide.toUpperCase()}",
            "size": "${rfq.size}",
            "label": "${rfq.label}",
            "price": "${fmtMoney(f.price)}",
            "edge": "${fmtMoney(f.edge)}",
        },
        "msg: `",
        "` }",
    ),
    (
        "SimulatorView.tsx",  # :237 — JS template literal
        simulator.MISS_MESSAGE_TEMPLATE,
        {"label": "${rfq.label}"},
        "msg: `",
        "` }",
    ),
]


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name is not None}


def _template_in_source(
    file: str, template: str, js: Mapping[str, str], before: str, after: str
) -> bool:
    """True iff the template uses exactly the placeholders of ``js`` and, with each one
    replaced by its JS expression, appears verbatim between ``before`` and ``after``."""
    if _placeholders(template) != set(js):
        return False
    return f"{before}{template.format_map(js)}{after}" in _jsx_text(file)


@needs_tsx
@pytest.mark.parametrize(
    ("file", "template", "js", "before", "after"),
    TSX_TEMPLATES,
    ids=[t[:24] for _, t, *_ in TSX_TEMPLATES],
)
def test_tsx_template_matches_its_source(
    file: str, template: str, js: dict[str, str], before: str, after: str
) -> None:
    assert _placeholders(template) == set(js), "placeholders differ from the JS expressions"
    assert _template_in_source(file, template, js, before, after), f"{template!r} not in {file}"


# ------------------------------------------- regression: the checks above reject mutations


@needs_tsx
def test_template_check_rejects_dropped_text_renamed_and_swapped_placeholders() -> None:
    replay, fill, miss = TSX_TEMPLATES
    file, _, js, before, after = replay
    dropped = "Undisclosed slice of real S&P 500 / VIX history ({count})."
    assert not _template_in_source(file, dropped, js, before, after)

    file, template, js, before, after = fill
    swapped = template.replace("{price}", "{tmp}").replace("{edge}", "{price}")
    swapped = swapped.replace("{tmp}", "{edge}")
    assert swapped != template
    assert not _template_in_source(file, swapped, js, before, after)
    assert not _template_in_source(file, template.replace("{size}", "{qty}"), js, before, after)

    file, template, js, before, after = miss
    assert not _template_in_source(file, template.removesuffix(" elsewhere"), js, before, after)


@needs_tsx
def test_card_check_pins_each_heading_to_its_field() -> None:
    labels = greeks.GREEK_DOC_FIELD_LABELS
    swapped = dict(zip(labels, list(labels.values())[::-1], strict=True))
    assert list(swapped) == list(labels)  # same key order: only the association changed
    src = _jsx_text("EducationPanel.tsx")
    assert re.search(_pattern(_card("doc", labels, GREEK_FIELDS)), src)
    assert not re.search(_pattern(_card("doc", swapped, GREEK_FIELDS)), src)
    # a map missing a heading no longer covers the whole card
    partial = {k: v for k, v in labels.items() if k != "desk"}
    assert not re.search(_pattern(_card("doc", partial, GREEK_FIELDS)), src)


@needs_tsx
def test_text_node_check_rejects_a_truncated_caption() -> None:
    src = _jsx_text("SimulatorView.tsx")
    caption = simulator.OPTION_HEDGE_CAPTION
    assert re.search(_text_node(caption), src)
    assert not re.search(_text_node(caption.split(";")[0] + "."), src)


@needs_tsx
def test_greek_sweep_caption_suffixes_for_vol_and_time() -> None:
    # PlotsPanel.tsx:147 builds these two from one JS template literal.
    m = re.search(
        r"` — dashed: current \$\{xAxis === 'sigma' \? '(\w+)' : '(\w+)'\}\.`",
        _jsx_text("PlotsPanel.tsx"),
    )
    assert m is not None
    suffixes = greeks.GREEK_SWEEP_CAPTION_SUFFIXES
    assert suffixes["sigma"] == f" — dashed: current {m.group(1)}."
    assert suffixes["T"] == f" — dashed: current {m.group(2)}."
