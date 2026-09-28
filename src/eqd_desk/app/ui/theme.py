"""The terminal palette, for the places Streamlit's theme config cannot reach (Altair charts,
Pandas Styler tables).

The widget/markdown theme lives in ``app/.streamlit/config.toml``; the values here MIRROR it
and ``web/src/index.css`` (the React app's CSS variables), so a chart line, a table cell and a
``:green[…]`` markdown span are all the same colour. ``tests/ui/test_theme.py`` checks this
module against the TOML so the two cannot drift.

No custom CSS is injected anywhere: every visual here is applied through native APIs (Altair
config, Styler cell styles, Markdown colour directives).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal

# ------------------------------------------------------------------ surfaces (index.css :root)

BG: Final = "#090d13"
"""Page background (``--bg`` / ``theme.backgroundColor``)."""
PANEL: Final = "#10161f"
"""Panel / widget background (``--panel`` / ``theme.secondaryBackgroundColor``)."""
PANEL_2: Final = "#0c121a"
"""Inset surface: hero boxes, cards, code (``--panel-2`` / ``theme.codeBackgroundColor``)."""
PANEL_HI: Final = "#141c28"
"""Hover / subtle-tag surface (``--panel-hi``)."""
BORDER: Final = "#1d2734"
"""Hairline borders (``--border`` / ``theme.borderColor``)."""
GRID: Final = "#18212e"
"""Chart grid lines (``--grid``)."""
AXIS: Final = "#2a3645"
"""Chart axis domain/ticks and the zero line (``--axis``)."""

# ------------------------------------------------------------------ text

TEXT: Final = "#d4dded"
"""Body text (``--text`` / ``theme.textColor``)."""
TEXT_DIM: Final = "#74859b"
"""Secondary text: units, captions, axis labels (``--text-dim`` / ``theme.grayColor``)."""

# ------------------------------------------------------------------ semantic colours

ACCENT: Final = "#36d39b"
"""Teal-green accent: the CURRENT level (spot/vol/tenor marker), the option value now
(``--accent`` / ``theme.primaryColor``)."""
ACCENT_DIM: Final = "rgba(54, 211, 155, 0.16)"
"""Translucent accent: selected-row background, area fills (``--accent-dim``)."""
LINE: Final = "#5aa9ff"
"""The main curve of every chart (a greek, the payoff at expiry) (``--line`` /
``theme.blueColor``)."""
POS: Final = "#3fd07f"
"""Positive numbers / P&L up (``--pos`` / ``theme.greenColor``)."""
NEG: Final = "#ff5d6c"
"""Negative numbers / P&L down; barriers and capital-loss levels (``--neg`` /
``theme.redColor``)."""
CALL: Final = "#36d39b"
"""Calls (``--call``; same hue as the accent)."""
PUT: Final = "#ff8a5c"
"""Puts, and a chart's secondary series (implied vol, the replicating spread) (``--put`` /
``theme.orangeColor``)."""
VIOLET: Final = "#a78bfa"
"""Extra series colour (``theme.violetColor``)."""
YELLOW: Final = "#fbbf24"
"""Extra series colour / warnings (``theme.yellowColor``)."""

SERIES_COLORS: Final[tuple[str, ...]] = (LINE, ACCENT, PUT, VIOLET, YELLOW, NEG, TEXT_DIM)
"""Categorical order for multi-series charts (``theme.chartCategoricalColors``)."""

# ------------------------------------------------------------------ fonts

MONO_FONT: Final = (
    "'JetBrains Mono', ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace"
)
"""Numerics font (``--mono``; loaded by Streamlit as ``theme.codeFont``)."""
SANS_FONT: Final = "Inter, system-ui, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
"""Text font (``theme.font``)."""

# ------------------------------------------------------------------ tones

Tone = Literal["pos", "neg", "zero", "accent", "dim", "line", "call", "put"]
"""A semantic colour: ``pos``/``neg``/``zero`` are sign buckets (see
:func:`eqd_desk.app.ui.format.sign_class`), the rest name a palette role."""

TONE_COLORS: Final[Mapping[Tone, str]] = MappingProxyType(
    {
        "pos": POS,
        "neg": NEG,
        "zero": TEXT_DIM,
        "accent": ACCENT,
        "dim": TEXT_DIM,
        "line": LINE,
        "call": CALL,
        "put": PUT,
    }
)
"""Hex colour of every tone (for charts and Styler cells)."""

TONE_MARKDOWN: Final[Mapping[Tone, str]] = MappingProxyType(
    {
        "pos": "green",
        "neg": "red",
        "zero": "gray",
        "accent": "primary",
        "dim": "gray",
        "line": "blue",
        "call": "primary",
        "put": "orange",
    }
)
"""Streamlit Markdown colour name of every tone (``:green[…]``); the theme maps each name to
the same hex as :data:`TONE_COLORS`."""
