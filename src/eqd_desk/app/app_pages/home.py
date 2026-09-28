"""Overview: what EQD Desk is for, the four tools, the seed market, and how every number is
computed."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from eqd_desk.app.ui import charts, state, theme
from eqd_desk.app.ui.charts import Series, VRule
from eqd_desk.app.ui.education import field_markdown
from eqd_desk.app.ui.format import fmt_level, fmt_num, fmt_pct
from eqd_desk.app.ui.nav import EXOTICS, GREEKS_LAB, SIMULATOR, STRATEGY_BUILDER, PageSpec
from eqd_desk.app.ui.widgets import section_header, sub_heading
from eqd_desk.content import EXOTIC_DOCS, KEY_RELATIONSHIPS, SIM_CONCEPTS, markdown_safe
from eqd_desk.content.exotics import EXOTIC_TAB_LABELS
from eqd_desk.data import SEED_T
from eqd_desk.engine import GREEK_NAMES, GREEK_UNITS
from eqd_desk.engine.presets import PRESETS

snap = state.snapshot()
cfg = state.underlying(snap)
surface = state.surface()

# ------------------------------------------------------------------ intro

st.title("Learn the index options desk", anchor=False)
st.markdown(
    f"EQD Desk replays the daily work of an equity-index derivatives market-maker on the "
    f"{markdown_safe(snap.name)}. Build intuition for the greeks of a single option, a "
    "structure and a whole book, then run the market-making loop yourself. Clarity beats "
    "realism: every price is computed transparently, and every tool has its explanation "
    "panel beside it."
)
loop = SIM_CONCEPTS[0]
with st.container(border=True):
    st.markdown(field_markdown(loop.title, loop.body))

# ------------------------------------------------------------------ the four tools


def badges(labels: list[str], color: str = "gray") -> str:
    """A run of inline Markdown badges."""
    return " ".join(f":{color}-badge[{markdown_safe(label)}]" for label in labels)


def tool_card(spec: PageSpec, inside: str, ideas: list[str]) -> None:
    """A bordered card: title, one-liner, what is inside, the key ideas, and a link."""
    with st.container(border=True, height="stretch"):
        st.markdown(f"#### :primary[{spec.icon}] {markdown_safe(spec.title)}", anchors=False)
        st.markdown(markdown_safe(spec.blurb))
        st.markdown(inside)
        if ideas:
            st.markdown("\n".join(f"- {markdown_safe(i)}" for i in ideas))
        st.page_link(
            str(spec.path),
            label=f"Open {spec.title.lower()}",
            icon=":material/arrow_forward:",
        )


section_header("Four tools, one engine", icon=":material/construction:")
tool_cols = st.columns(4)
with tool_cols[0]:
    tool_card(
        GREEKS_LAB,
        badges([GREEK_UNITS[k].label for k in GREEK_NAMES]),
        [r.title for r in KEY_RELATIONSHIPS],
    )
with tool_cols[1]:
    tool_card(STRATEGY_BUILDER, badges([p.label for p in PRESETS]), [])
with tool_cols[2]:
    tool_card(
        EXOTICS,
        badges(list(EXOTIC_TAB_LABELS.values())),
        [d.title for d in EXOTIC_DOCS.values()],
    )
with tool_cols[3]:
    tool_card(SIMULATOR, badges(["Simulated", "Replay"]), [c.title for c in SIM_CONCEPTS[1:]])

# ------------------------------------------------------------------ seed market

section_header(
    "Seed market",
    icon=":material/database:",
    badge=f"as of {snap.asof}",
    badge_color="orange",
)
st.caption(
    markdown_safe(
        f"A static snapshot of the {snap.name} ({snap.currency}): the starting point of every "
        "tool. The simulator then evolves it along a simulated (or replayed) path."
    )
)
with st.container(horizontal=True, gap="small"):
    st.metric(f"Spot · {cfg.index_ticker}", fmt_level(snap.spot, 3), border=True)
    st.metric(f"ATM vol 30d · {cfg.vol_index_ticker}", fmt_pct(snap.atm_vol_30d), border=True)
    st.metric(
        "Realised vol · 1y",
        fmt_pct(snap.realized_vol) if snap.realized_vol is not None else "—",
        border=True,
    )
    st.metric("Rate r", fmt_pct(snap.r), border=True)
    st.metric("Dividend yield q", fmt_pct(snap.q), border=True)
    st.metric(
        "Skew slope · curvature",
        f"{fmt_num(snap.skew.slope, 3)} · {fmt_num(snap.skew.curv, 3)}",
        border=True,
        help="Quadratic smile in log-moneyness k = ln(K/S): iv ≈ atm + slope·k + curv·k².",
    )

smile_col, term_col, notes_col = st.columns([1.15, 1, 1])
with smile_col, st.container(border=True, height="stretch"):
    section_header("Implied-vol smile", subtitle="30-day", highlight=cfg.options_proxy + " shape")
    strikes = charts.sweep_x(snap.spot * 0.7, snap.spot * 1.3, 120)
    smile = pd.DataFrame({"K": strikes, "iv": [surface.get_vol(k, SEED_T) for k in strikes]})
    charts.show_chart(
        charts.line_chart(
            smile,
            x="K",
            series=Series("iv", "Implied vol", color=theme.PUT),
            x_title="Strike",
            y_title="Implied vol",
            y_format=".0%",
            y_tooltip=fmt_pct,
            x_tooltip=lambda k: fmt_level(k, 0),
            vrules=[VRule(snap.spot, "current", "spot")],
            y_zero=False,
            height=charts.SHORT_HEIGHT,
        ),
        key="home.smile",
    )
    st.caption(
        "Equity skew: low strikes trade richer. Dashed: today's spot. The whole surface moves "
        "with spot in the simulator (the leverage effect)."
    )
with term_col, st.container(border=True, height="stretch"):
    section_header("ATM term structure", subtitle="by tenor")
    tenors = charts.sweep_x(7 / 365, 1.0, 120)
    term = pd.DataFrame({"T": tenors, "atm": [surface.atm_vol(t) for t in tenors]})
    charts.show_chart(
        charts.line_chart(
            term,
            x="T",
            series=Series("atm", "ATM vol"),
            x_title="Tenor (years)",
            y_title="ATM implied vol",
            y_format=".1%",
            y_tooltip=fmt_pct,
            x_tooltip=lambda t: f"{fmt_num(t, 3)} y",
            vrules=[VRule(SEED_T, "current", "30d")],
            y_zero=False,
            height=charts.SHORT_HEIGHT,
        ),
        key="home.term",
    )
    st.caption("ATM vol by expiry, interpolated between the snapshot's tenors.")
with notes_col, st.container(border=True, height="stretch"):
    section_header("Where the data comes from", icon=":material/info:")
    st.table(
        {
            "Index level": f"`{snap.tickers.index_ticker or cfg.index_ticker}`",
            "ATM vol anchor": f"`{snap.tickers.vol_ticker or cfg.vol_index_ticker}`",
            "Skew shape": f"`{snap.tickers.options_proxy or cfg.options_proxy}` option chain",
            "Currency": markdown_safe(snap.currency),
        },
        border="horizontal",
    )
    sub_heading("Source notes")
    for note in snap.source_notes:
        st.caption(markdown_safe(note))

# ------------------------------------------------------------------ how numbers are computed

section_header("How the numbers are computed", icon=":material/calculate:")
how_col, units_col = st.columns([1.1, 1])
with how_col, st.container(border=True, height="stretch"):
    st.markdown(
        "- **Black–Scholes–Merton with a continuous dividend yield**, implemented from "
        "scratch in `eqd_desk.engine`: no options library, every formula readable.\n"
        "- **Greeks are analytic**, and each one is checked in the test suite against a "
        "central finite-difference bump of the pricer, plus hard-coded reference values.\n"
        "- **Exotics** use closed forms where they exist (barriers, digitals, variance "
        "swap) and seeded Monte Carlo otherwise (the autocallable), with bump greeks.\n"
        "- **Conventions**: T is a year fraction of calendar days (days / 365); r and q are "
        "continuously compounded decimals; vols are decimals (0.146 = 14.6 vol points)."
    )
    st.latex(
        r"d_1 = \frac{\ln(S/K) + (r - q + \tfrac{1}{2}\sigma^2)\,T}{\sigma\sqrt{T}},"
        r"\qquad d_2 = d_1 - \sigma\sqrt{T}"
    )
    st.latex(
        r"C = S e^{-qT} N(d_1) - K e^{-rT} N(d_2),"
        r"\qquad P = K e^{-rT} N(-d_2) - S e^{-qT} N(-d_1)"
    )
with units_col, st.container(border=True, height="stretch"):
    section_header("Desk units", subtitle="how each greek is reported")
    units = pd.DataFrame(
        {
            "Greek": [GREEK_UNITS[k].label for k in ("price", *GREEK_NAMES)],
            "Reported": [markdown_safe(GREEK_UNITS[k].unit) for k in ("price", *GREEK_NAMES)],
            "From the raw partial": [
                markdown_safe(GREEK_UNITS[k].scale_note) for k in ("price", *GREEK_NAMES)
            ],
        }
    )
    st.table(units, border="horizontal", hide_index=True)
