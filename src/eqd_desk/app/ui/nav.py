"""The page registry: one source of truth for the product name and every page's file, title,
icon, URL and browser-tab title, used by the entrypoint (``st.navigation``,
``st.set_page_config``) and the overview's tool cards (``st.page_link``). Pure: no Streamlit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

APP_DIR: Final = Path(__file__).resolve().parents[1]
"""``eqd_desk/app``: the directory of the entrypoint script."""

APP_NAME: Final = "EQD Desk"
"""Product name shown in the header strip and the browser tab."""

APP_ICON: Final = ":material/finance_mode:"
"""App icon (browser tab + header brand mark)."""

TAB_TITLE_SEPARATOR: Final = " · "
"""Between a page's title and the product name in a browser tab ("Greeks lab · EQD Desk")."""


@dataclass(frozen=True, slots=True)
class PageSpec:
    """One page of the app."""

    file: str
    """Script path relative to the entrypoint's directory (``"app_pages/greeks_lab.py"``);
    also what ``AppTest.switch_page`` takes."""
    title: str
    """Navigation label (sentence case)."""
    icon: str
    """Material Symbols shortcode."""
    url_path: str
    """URL slug (empty for the default page)."""
    blurb: str
    """One-line description for the overview card."""

    @property
    def path(self) -> Path:
        """Absolute path of the page script."""
        return APP_DIR / self.file

    @property
    def tab_title(self) -> str:
        """The browser-tab title: ``"Greeks lab · EQD Desk"`` (the overview: the product
        name alone), so each tab and each history entry names its page."""
        if self.url_path == "":
            return APP_NAME
        return f"{self.title}{TAB_TITLE_SEPARATOR}{APP_NAME}"


HOME: Final = PageSpec(
    "app_pages/home.py",
    "Overview",
    ":material/home:",
    "",
    "What the desk is for, the seed market, and how every number is computed.",
)
GREEKS_LAB: Final = PageSpec(
    "app_pages/greeks_lab.py",
    "Greeks lab",
    ":material/functions:",
    "greeks-lab",
    "One vanilla option: its price and all ten greeks, live, swept against spot, vol and time.",
)
STRATEGY_BUILDER: Final = PageSpec(
    "app_pages/strategy_builder.py",
    "Strategy builder",
    ":material/stacked_line_chart:",
    "strategy-builder",
    "Compose vanilla legs into the standard index-desk structures and read the "
    "aggregate greeks and P&L.",
)
EXOTICS: Final = PageSpec(
    "app_pages/exotics.py",
    "Exotics",
    ":material/experiment:",
    "exotics",
    "Barriers, digitals, an autocallable and a variance swap: where vanilla "
    "intuition stops being enough.",
)
SIMULATOR: Final = PageSpec(
    "app_pages/simulator.py",
    "Simulator",
    ":material/candlestick_chart:",
    "simulator",
    "Make markets: quote client RFQs, warehouse the risk, hedge it and explain your P&L.",
)

PAGES: Final[tuple[PageSpec, ...]] = (HOME, GREEKS_LAB, STRATEGY_BUILDER, EXOTICS, SIMULATOR)
"""Every page, in navigation order (the first is the default)."""

TOOLS: Final[tuple[PageSpec, ...]] = PAGES[1:]
"""The four training tools (every page but the overview)."""


def page_spec(title: str) -> PageSpec:
    """The registered page with navigation ``title`` (what ``st.navigation`` returns as the
    page's ``title``); the overview for an unknown title."""
    return next((spec for spec in PAGES if spec.title == title), HOME)


__all__ = [
    "APP_DIR",
    "APP_ICON",
    "APP_NAME",
    "EXOTICS",
    "GREEKS_LAB",
    "HOME",
    "PAGES",
    "SIMULATOR",
    "STRATEGY_BUILDER",
    "TAB_TITLE_SEPARATOR",
    "TOOLS",
    "PageSpec",
    "page_spec",
]
