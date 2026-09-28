"""The Python palette mirrors the Streamlit theme config and the React CSS variables, so
charts, Styler tables and Markdown colours can never drift apart."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

from eqd_desk.app.ui import theme
from eqd_desk.app.ui.nav import APP_DIR

ROOT = Path(__file__).resolve().parents[2]
CONFIG = APP_DIR / ".streamlit" / "config.toml"
INDEX_CSS = ROOT / "web" / "src" / "index.css"


def theme_config() -> dict[str, Any]:
    with CONFIG.open("rb") as fh:
        cfg: dict[str, Any] = tomllib.load(fh)["theme"]
    return cfg


def test_palette_matches_config_toml() -> None:
    cfg = theme_config()
    assert cfg["base"] == "dark"
    assert cfg["primaryColor"] == theme.ACCENT
    assert cfg["backgroundColor"] == theme.BG
    assert cfg["secondaryBackgroundColor"] == theme.PANEL
    assert cfg["codeBackgroundColor"] == theme.PANEL_2
    assert cfg["codeTextColor"] == theme.TEXT
    assert cfg["textColor"] == theme.TEXT
    assert cfg["borderColor"] == theme.BORDER
    assert cfg["greenColor"] == theme.POS
    assert cfg["redColor"] == theme.NEG
    assert cfg["blueColor"] == theme.LINE
    assert cfg["orangeColor"] == theme.PUT
    assert cfg["violetColor"] == theme.VIOLET
    assert cfg["yellowColor"] == theme.YELLOW
    assert cfg["grayColor"] == theme.TEXT_DIM
    assert tuple(cfg["chartCategoricalColors"]) == theme.SERIES_COLORS


@pytest.mark.parametrize("tone", list(theme.TONE_COLORS))
def test_markdown_tone_renders_the_same_hex(tone: theme.Tone) -> None:
    cfg = theme_config()
    name = theme.TONE_MARKDOWN[tone]
    key = "primaryColor" if name == "primary" else f"{name}Color"
    assert cfg[key] == theme.TONE_COLORS[tone]


def test_palette_matches_react_css_variables() -> None:
    css = dict(re.findall(r"--([\w-]+):\s*([^;]+);", INDEX_CSS.read_text("utf-8")))
    expected = {
        "bg": theme.BG,
        "panel": theme.PANEL,
        "panel-2": theme.PANEL_2,
        "panel-hi": theme.PANEL_HI,
        "border": theme.BORDER,
        "grid": theme.GRID,
        "axis": theme.AXIS,
        "text": theme.TEXT,
        "text-dim": theme.TEXT_DIM,
        "accent": theme.ACCENT,
        "accent-dim": theme.ACCENT_DIM,
        "line": theme.LINE,
        "pos": theme.POS,
        "neg": theme.NEG,
        "call": theme.CALL,
        "put": theme.PUT,
    }
    for var, value in expected.items():
        assert css[var].strip() == value, var
