"""The overview page's derived text: skew provenance, source-note Markdown, the
Strategy-builder card's ideas and the BSM formulas."""

from __future__ import annotations

import importlib.util
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

from eqd_desk.app.ui.home_text import (
    BSM_LATEX,
    BSM_ROWS,
    STRUCTURE_VIEWS,
    note_markdown,
    skew_is_fallback,
    skew_source,
    structure_ideas,
)
from eqd_desk.content import STRATEGY_DOCS, markdown_safe
from eqd_desk.data import load_snapshot, validate_snapshot
from eqd_desk.engine.presets import PRESETS, PresetName

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "fetch_snapshot.py"


def test_module_is_pure() -> None:
    code = "import sys, eqd_desk.app.ui.home_text; print('streamlit' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=120
    )
    assert out.stdout.strip() == "False"


# ------------------------------------------------------------------ skew provenance


def test_committed_seed_is_labelled_as_the_parametric_fallback() -> None:
    """The static seed's own note says its skew is the parametric fallback, so the page
    must not claim an SPY fit."""
    snap = load_snapshot()
    src = skew_source(snap.source_notes, "SPY")
    assert not src.fitted
    assert src.tag == "parametric shape"
    assert "Parametric fallback" in src.detail
    assert "`SPY`" in src.detail


def test_a_fitted_skew_is_labelled_with_the_proxy() -> None:
    src = skew_source(["all fields fetched live"], "FEZ")
    assert src.fitted
    assert src.tag == "FEZ shape"
    assert src.detail == "`FEZ` option chain"


@pytest.mark.parametrize(
    ("notes", "fallback"),
    [
        ([], False),
        (["all fields fetched live"], False),
        (["STATIC FALLBACK SEED — placeholder values"], False),  # not about the skew
        (["vol index ^VIX unavailable; atm_vol_30d defaulted to 0.18"], False),
        (["proxy SPY skew unavailable; using parametric fallback"], True),
        (["x", "Skew shape is a parametric equity-skew FALLBACK"], True),
    ],
)
def test_skew_is_fallback_reads_the_notes(notes: list[str], fallback: bool) -> None:
    assert skew_is_fallback(notes) is fallback


def _load_script() -> ModuleType:
    if not SCRIPT.is_file():
        pytest.skip(f"{SCRIPT} not present")
    spec = importlib.util.spec_from_file_location("_eqd_script_fetch_snapshot_home", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("proxy_ok", [True, False], ids=["proxy-fit", "proxy-failed"])
def test_skew_provenance_tracks_what_the_refresh_script_writes(
    proxy_ok: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the real ``build_snapshot`` offline (fetchers faked) and check the label follows
    whether the proxy chain was fitted: the contract between the script's notes and
    :func:`skew_is_fallback`."""
    script = _load_script()
    term = [{"t": 0.08, "atm_iv": 0.15}]
    skew = {"slope": -0.5, "curv": 0.7}
    monkeypatch.setattr(script, "fetch_spot_and_realized", lambda t: (6000.0, 0.12, "2026-01-02"))
    monkeypatch.setattr(script, "fetch_atm_vol", lambda t: 0.16)
    monkeypatch.setattr(
        script, "fetch_skew_and_term", lambda t: (dict(skew) if proxy_ok else None, term)
    )
    monkeypatch.setattr(script, "estimate_div_yield", lambda t, fallback: fallback)
    snap = validate_snapshot(script.build_snapshot("spx"))
    src = skew_source(snap.source_notes, snap.tickers.options_proxy)
    assert src.fitted is proxy_ok
    assert src.tag == ("SPY shape" if proxy_ok else "parametric shape")


# ------------------------------------------------------------------ source notes


def test_note_markdown_keeps_inline_code_and_escapes_the_prose() -> None:
    note = "Run `uv run python x.py --a $1` to refresh *now* ~14.6"
    assert note_markdown(note) == (
        "Run `uv run python x.py --a $1` " + markdown_safe("to refresh *now* ~14.6")
    )


@pytest.mark.parametrize("note", ["plain text, no code", "a lone ` backtick", "$5 and $6", ""])
def test_note_markdown_without_code_equals_markdown_safe(note: str) -> None:
    assert note_markdown(note) == markdown_safe(note)


def test_seed_refresh_command_is_current() -> None:
    """The seed's refresh note shows a command that works from the repo root today: uv with
    the ``scripts`` group, the script's default output (both app copies), and not the
    pre-Python ``src/data/`` path (which no longer exists)."""
    snap = load_snapshot()
    commands = [c for n in snap.source_notes for c in re.findall(r"`([^`]+)`", n)]
    assert len(commands) == 1
    argv = shlex.split(commands[0])
    assert argv[:5] == ["uv", "run", "--group", "scripts", "python"]
    assert argv[5] == "scripts/fetch_snapshot.py"
    assert "--out" not in argv
    assert "src/data" not in commands[0]
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))
    assert "scripts" in pyproject["dependency-groups"]


# ------------------------------------------------------------------ tool-card ideas


def test_structure_ideas_name_real_presets_in_display_order() -> None:
    labels = [p.label for p in PRESETS]
    ideas = structure_ideas()
    assert len(ideas) == 4  # as many as the other tool cards
    heads = [i.split(" — ")[0] for i in ideas]
    assert heads == sorted(heads, key=labels.index)


@pytest.mark.parametrize(
    ("name", "keyword"),
    [
        ("straddle", "realised"),
        ("risk-reversal", "skew"),
        ("butterfly", "vol-of-vol"),
        ("calendar", "term-structure"),
    ],
)
def test_structure_views_agree_with_the_strategy_docs(name: PresetName, keyword: str) -> None:
    """Each condensed view is the one its Learn panel states."""
    assert keyword in STRUCTURE_VIEWS[name]
    assert keyword in STRATEGY_DOCS[name].view.lower()


# ------------------------------------------------------------------ formulas


def test_bsm_latex_puts_one_formula_on_each_row() -> None:
    assert BSM_LATEX.startswith(r"\begin{aligned}")
    # the thin space after the table absorbs KaTeX's 2 px column overhang (no scrollbar)
    assert BSM_LATEX.endswith(r"\end{aligned}\,")
    assert r"\qquad" not in BSM_LATEX  # no two formulas side by side
    assert [row.split("&=")[0].strip() for row in BSM_ROWS] == ["d_1", "d_2", "C", "P"]
    assert all(row.count("&=") == 1 for row in BSM_ROWS)
    assert BSM_LATEX.count(r"\\") == len(BSM_ROWS) - 1
