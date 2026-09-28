"""The teaching content is complete and well-formed: every greek, preset, exotic and
P&L-explain term has its explanation, and no string is empty or malformed.

(String-for-string equality with the TypeScript is checked in
``tests/parity/test_content_parity.py``.)
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from eqd_desk import content
from eqd_desk.content import exotics, greeks, markdown_safe, simulator, strategies
from eqd_desk.engine import GREEK_NAMES, GREEK_UNITS

MODULES = (greeks, strategies, exotics, simulator)
PRESETS_TS = Path(__file__).resolve().parents[2] / "web" / "src" / "engine" / "presets.ts"


def _strings(value: Any, where: str) -> Iterator[tuple[str, str]]:
    """Yield (location, text) for every string reachable from a content value."""
    if isinstance(value, str):
        yield where, value
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for f in dataclasses.fields(value):
            yield from _strings(getattr(value, f.name), f"{where}.{f.name}")
    elif isinstance(value, Mapping):
        for k, v in value.items():
            yield from _strings(k, f"{where}[key]")
            yield from _strings(v, f"{where}[{k!r}]")
    elif isinstance(value, tuple | list | frozenset):
        for i, v in enumerate(value):
            yield from _strings(v, f"{where}[{i}]")


def _all_content_strings() -> list[tuple[str, str]]:
    """Every string of every public UPPER_CASE constant of the four content modules."""
    out: list[tuple[str, str]] = []
    for mod in MODULES:
        for name in dir(mod):
            if name.isupper() and not name.startswith("_"):
                out.extend(_strings(getattr(mod, name), f"{mod.__name__}.{name}"))
    return out


# ----------------------------------------------------------------------------- greeks


def test_every_greek_and_the_price_has_a_complete_doc() -> None:
    for key in ("price", *GREEK_NAMES):
        doc = greeks.GREEK_DOCS[key]  # type: ignore[index]
        assert doc.key == key
        for f in dataclasses.fields(doc):
            assert getattr(doc, f.name), f"{key}.{f.name} is empty"


def test_greek_keys_match_the_engine() -> None:
    assert ("price", *GREEK_NAMES) == greeks.GREEK_KEYS
    assert tuple(greeks.GREEK_DOCS) == greeks.GREEK_KEYS  # display order
    assert greeks.PLOTTABLE_KEYS == greeks.GREEK_KEYS
    # every key has reporting-unit metadata for its label / unit tag
    assert set(GREEK_UNITS) == set(greeks.GREEK_KEYS)


def test_greek_groups_partition_the_greeks_by_order() -> None:
    grouped = [k for g in greeks.GREEK_GROUPS for k in g.keys]
    assert sorted(grouped) == sorted(GREEK_NAMES)
    assert len(grouped) == len(set(grouped))
    expected_order = {"First order": "first", "Second order / cross": "second"}
    expected_order["Third order"] = "third"
    for group in greeks.GREEK_GROUPS:
        for key in group.keys:
            assert greeks.GREEK_DOCS[key].order == expected_order[group.title], key
    assert greeks.GREEK_DOCS["price"].order == "value"


def test_field_labels_cover_the_prose_fields_in_order() -> None:
    assert tuple(greeks.GREEK_DOC_FIELD_LABELS) == ("measures", "intuition", "when_large", "desk")
    assert tuple(strategies.STRATEGY_DOC_FIELD_LABELS) == ("view", "structure", "greeks", "risk")
    assert tuple(exotics.EXOTIC_DOC_FIELD_LABELS) == ("what", "behaviour", "risk")
    field_sets = (
        (greeks.GreekDoc, greeks.GREEK_DOC_FIELD_LABELS),
        (strategies.StrategyDoc, strategies.STRATEGY_DOC_FIELD_LABELS),
        (exotics.ExoticDoc, exotics.EXOTIC_DOC_FIELD_LABELS),
    )
    for cls, labels in field_sets:
        names = {f.name for f in dataclasses.fields(cls)}
        assert set(labels) <= names, cls
    assert set(exotics.EXOTIC_GREEK_DOC_FIELDS) <= set(greeks.GREEK_DOC_FIELD_LABELS)


@pytest.mark.parametrize(
    ("x_axis", "suffix"),
    [
        ("S", " — dashed: current spot; dotted: strike."),
        ("sigma", " — dashed: current vol."),
        ("T", " — dashed: current tenor."),
    ],
)
def test_greek_sweep_caption(x_axis: greeks.XAxisKey, suffix: str) -> None:
    for key in greeks.GREEK_KEYS:
        assert greeks.greek_sweep_caption(key, x_axis) == greeks.GREEK_DOCS[key].measures + suffix


# ------------------------------------------------------------------------- strategies


def test_every_preset_has_complete_docs() -> None:
    assert tuple(strategies.STRATEGY_DOCS) == strategies.PRESET_NAMES
    for name in strategies.PRESET_NAMES:
        doc = strategies.STRATEGY_DOCS[name]
        assert doc.name == name
        for f in dataclasses.fields(doc):
            assert getattr(doc, f.name), f"{name}.{f.name} is empty"


@pytest.mark.skipif(not PRESETS_TS.exists(), reason="TypeScript sources (web/) not present")
def test_every_preset_of_the_typescript_engine_has_docs() -> None:
    source = PRESETS_TS.read_text(encoding="utf-8")
    block = re.search(r"export const PRESETS[^=]*=\s*\[(.*?)\n\]", source, re.DOTALL)
    assert block is not None
    ts_names = re.findall(r"name: '([a-z-]+)'", block.group(1))
    assert len(ts_names) == 8
    assert tuple(ts_names) == strategies.PRESET_NAMES
    assert set(ts_names) == set(strategies.STRATEGY_DOCS)


@pytest.mark.parametrize(
    ("net_premium", "side"), [(12.5, "debit"), (0.0, "debit"), (-0.01, "credit")]
)
def test_premium_side(net_premium: float, side: str) -> None:
    assert strategies.premium_side(net_premium) == side
    assert strategies.PREMIUM_SIDE_NOTES[strategies.premium_side(net_premium)].endswith(f"({side})")


# ---------------------------------------------------------------------------- exotics


def test_every_exotic_has_complete_docs() -> None:
    assert tuple(exotics.EXOTIC_DOCS) == exotics.EXOTIC_KINDS
    assert set(exotics.EXOTIC_TAB_LABELS) == set(exotics.EXOTIC_KINDS)
    for kind in exotics.EXOTIC_KINDS:
        doc = exotics.EXOTIC_DOCS[kind]
        assert doc.kind == kind
        for f in dataclasses.fields(doc):
            assert getattr(doc, f.name), f"{kind}.{f.name} is empty"


def test_exotic_metrics_are_documented_greeks() -> None:
    assert exotics.EXOTIC_METRICS == ("price", "delta", "gamma", "vega", "theta", "rho")
    for metric in exotics.EXOTIC_METRICS:
        assert metric in greeks.GREEK_DOCS
        assert metric in GREEK_UNITS


# -------------------------------------------------------------------------- simulator


def test_attribution_terms_cover_the_taylor_explain_in_order() -> None:
    keys = tuple(t.key for t in simulator.ATTRIBUTION_TERMS)
    assert keys == ("delta", "gamma", "theta", "vega", "vanna", "volga", "residual")


def test_sim_concepts_start_with_the_loop_and_end_with_the_explain() -> None:
    titles = [c.title for c in simulator.SIM_CONCEPTS]
    assert len(titles) == 5
    assert titles[0] == "The market-making loop"
    assert titles[-1] == "Reading a P&L explain"


def test_message_templates_format() -> None:
    fill = simulator.FILL_MESSAGE_TEMPLATE.format(
        side="SELL", size=10, label="C 5000 30d", price="12.34", edge="0.61"
    )
    assert fill == "Filled — you SELL 10× C 5000 30d @ 12.34 · edge 0.61"
    miss = simulator.MISS_MESSAGE_TEMPLATE.format(label="P 4800 60d")
    assert miss == "Missed P 4800 60d — client traded elsewhere"
    replay = simulator.REPLAY_CAPTION_TEMPLATE.format(count=2012)
    assert replay == "Undisclosed slice of real S&P 500 / VIX history (2012 days on file)."


@pytest.mark.parametrize(
    ("instrument", "tenor_days", "role"),
    [
        ("future", None, "cleans up Δ (last)"),
        ("future", 10, "cleans up Δ (last)"),
        ("option", 7, "gamma"),
        ("option", 30, "gamma"),
        ("option", 31, "vega"),
        ("option", 90, "vega"),
        ("option", None, "vega"),  # no tenor: TS `l.tenorDays && …` is falsy
        ("option", 0, "vega"),
    ],
)
def test_joint_hedge_role(instrument: Any, tenor_days: float | None, role: str) -> None:
    assert simulator.joint_hedge_role(instrument, tenor_days) == role


# ------------------------------------------------------------------ whole-content checks


def test_no_empty_or_malformed_strings() -> None:
    texts = _all_content_strings()
    assert len(texts) > 150  # sanity: the walk actually reached the docs
    for where, text in texts:
        assert text.strip(), f"{where} is empty"
        assert "\n" not in text, f"{where} has a line break"
        assert "\t" not in text, f"{where} has a tab"
        assert "  " not in text, f"{where} has a double space"
        # JSX entities must have been decoded when lifting prose out of the markup
        assert "&amp;" not in text, where
        assert "&apos;" not in text, where
        # only the documented str.format templates carry {placeholders}
        if "{" in text or "}" in text:
            assert where.split(".")[-1].endswith("_TEMPLATE"), where


def test_prose_is_trimmed_except_the_caption_suffixes() -> None:
    for where, text in _all_content_strings():
        if "GREEK_SWEEP_CAPTION_SUFFIXES" in where and "[key]" not in where:
            assert text.startswith(" — "), where
            assert text == text.rstrip(), where
        else:
            assert text == text.strip(), where


def test_value_types_are_frozen_and_mappings_read_only() -> None:
    doc = greeks.GREEK_DOCS["delta"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        doc.title = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        greeks.GREEK_DOCS["delta"] = doc  # type: ignore[index]
    with pytest.raises(TypeError):
        strategies.STRATEGY_DOCS["straddle"] = strategies.STRATEGY_DOCS["strangle"]  # type: ignore[index]


def test_package_reexports() -> None:
    assert content.GREEK_DOCS is greeks.GREEK_DOCS
    assert content.STRATEGY_DOCS is strategies.STRATEGY_DOCS
    assert content.EXOTIC_DOCS is exotics.EXOTIC_DOCS
    assert content.SIM_CONCEPTS is simulator.SIM_CONCEPTS
    for name in content.__all__:
        assert hasattr(content, name), name


@pytest.mark.parametrize("mod", [content, *MODULES], ids=lambda m: m.__name__)
def test_every_module_says_where_its_text_came_from(mod: ModuleType) -> None:
    assert mod.__doc__ is not None
    assert "web/src/components/" in mod.__doc__


# ------------------------------------------------------------------------ markdown_safe


def test_markdown_safe_escapes_latex_dollars() -> None:
    measures = greeks.GREEK_DOCS["delta"].measures
    assert "$1" in measures
    assert markdown_safe(measures) == measures.replace("$", r"\$")
    assert markdown_safe("a $1 move vs per $1 spot") == r"a \$1 move vs per \$1 spot"


def test_markdown_safe_escapes_every_special_char_and_nothing_else() -> None:
    specials = "\\`*_[]<>#|~$"
    assert set(specials) == content.MARKDOWN_SPECIAL_CHARS
    assert markdown_safe(specials) == "".join("\\" + c for c in specials)
    plain = "Gamma (Γ) ≈ ½·Γ·S²·(σ² − σ²) — P&L, (r − q), 1/K², T → 0."
    assert markdown_safe(plain) == plain


def test_markdown_safe_round_trips_all_content() -> None:
    unescape = re.compile(r"\\(.)")
    for where, text in _all_content_strings():
        escaped = markdown_safe(text)
        assert unescape.sub(r"\1", escaped) == text, where
        # no unescaped special character survives
        stripped = unescape.sub("", escaped)
        assert not set(stripped) & content.MARKDOWN_SPECIAL_CHARS, where
