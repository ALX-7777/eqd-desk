"""The greeks lab page, driven headless: what it shows equals the engine for the inputs on
screen, and every control (sliders, fields, call/put, reset, σ ← surface, greek and x-axis
pickers) changes what it should."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pandas as pd
import pytest
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
from streamlit.testing.v1 import AppTest

from eqd_desk.app.ui import greeks_lab_curves as curves
from eqd_desk.app.ui.format import fmt_money, fmt_num, to_precision
from eqd_desk.content import GREEK_DOCS, KEY_RELATIONSHIPS, markdown_safe
from eqd_desk.content.greeks import GREEK_GROUPS, PAYOFF_CAPTION, greek_sweep_caption
from eqd_desk.data import default_surface, load_snapshot, seed_inputs
from eqd_desk.engine import GREEK_UNITS, BsmInputs, OptionType, analyze_option

from .conftest import AppTestFactory

pytestmark = pytest.mark.app

PAGE = "app_pages/greeks_lab.py"
SNAP = load_snapshot()
SEED = seed_inputs(SNAP)
GREEK_ORDER = [k for g in GREEK_GROUPS for k in g.keys]


@pytest.fixture
def lab(app_test: AppTestFactory) -> AppTest:
    """The app on the greeks lab page, first run."""
    at = app_test()
    at.run()
    at.switch_page(PAGE).run()
    assert not at.exception, at.exception
    return at


# ------------------------------------------------------------------ readers


def texts(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown]


def current_inputs(at: AppTest) -> BsmInputs:
    ss = at.session_state
    return BsmInputs(
        S=ss["lab.S"],
        K=ss["lab.K"],
        T=ss["lab.T"],
        r=ss["lab.r"],
        q=ss["lab.q"],
        sigma=ss["lab.sigma"],
    )


def premium(at: AppTest) -> tuple[str, str]:
    """(value, detail line) of the premium hero."""
    (metric,) = at.metric
    assert metric.label == "Premium (USD)"
    return metric.value, metric.proto.delta_description


def readout(at: AppTest) -> dict[str, float]:
    """The greeks table as label → value (group headings dropped)."""
    table = at.table[0].value
    values = table[table["value"].notna()]
    return dict(zip(values["label"], values["value"], strict=True))


def assert_shows(at: AppTest, inputs: BsmInputs, option_type: OptionType) -> None:
    """The hero, the readout and the badge are those of ``analyze_option(inputs, type)``."""
    assert not at.exception, at.exception
    a = analyze_option(inputs, option_type)
    split = curves.premium_split(a)
    assert premium(at) == (
        fmt_money(a.reported.price),
        f"intrinsic {fmt_money(split.intrinsic)} · time value {fmt_money(split.time_value)}",
    )
    assert readout(at) == {GREEK_UNITS[k].label: getattr(a.reported, k) for k in GREEK_ORDER}
    badge = ":primary-badge[CALL]" if option_type == "call" else ":orange-badge[PUT]"
    assert any(badge in t for t in texts(at))


def chart_lines(at: AppTest, index: int) -> list[pd.DataFrame]:
    """The data behind each line of chart ``index`` (0: greek sweep, 1: payoff)."""
    el: Any = at.get("vega_lite_chart")[index]
    spec = json.loads(el.proto.spec)
    data = {d.name: convert_arrow_bytes_to_pandas_df(d.data.data) for d in el.proto.datasets}
    return [
        data[layer["data"]["name"]]
        for layer in spec["layer"]
        if (layer["mark"]["type"] if isinstance(layer["mark"], dict) else layer["mark"]) == "line"
    ]


# ------------------------------------------------------------------ defaults


def test_defaults_match_the_react_screenshot(lab: AppTest) -> None:
    assert current_inputs(lab) == SEED
    assert lab.session_state["lab.type"] == "call"
    assert premium(lab) == ("119.61", "intrinsic 12.45 · time value 107.16")
    shown = readout(lab)
    assert fmt_num(shown["Delta"]) == "0.54994"
    assert fmt_num(shown["Vega"]) == "7.1541"
    assert fmt_num(shown["Theta"]) == "-2.0121"
    assert fmt_num(shown["Rho"]) == "2.7550"
    assert fmt_num(shown["Gamma"]) == "0.0014962"
    assert fmt_num(shown["Vanna"]) == "-0.0023055"
    assert fmt_num(shown["Volga"]) == "0.0052990"
    assert_shows(lab, SEED, "call")
    # the input headers print the React displays
    for display in ("6,312.45 USD", "6,300 USD", "0.082 y · 30 d", "14.60%", "4.30%", "1.30%"):
        assert f"`{display}`" in texts(lab), display
    # both widgets of each pair start on the seed value
    assert lab.slider(key="lab.S__slider").value == SEED.S
    assert lab.number_input(key="lab.T__input").value == SEED.T


def test_readout_groups_every_greek_in_desk_units(lab: AppTest) -> None:
    table = lab.table[0].value
    assert list(table["label"]) == [
        label for g in GREEK_GROUPS for label in (g.title, *(GREEK_UNITS[k].label for k in g.keys))
    ]
    units = dict(zip(table["label"], table["unit"], strict=True))
    for k in GREEK_ORDER:
        assert units[GREEK_UNITS[k].label] == markdown_safe(GREEK_UNITS[k].unit)


def test_raw_partials_show_the_unscaled_derivatives(lab: AppTest) -> None:
    (raw_panel,) = lab.status  # an expander with an icon is a "status" block in AppTest
    assert raw_panel.label == "Raw partials"
    table = raw_panel.table[0].value
    values = table[table["value"].notna()]
    a = analyze_option(SEED, "call")
    assert list(values["value"]) == [getattr(a.raw, k) for k in GREEK_ORDER]
    assert to_precision(a.raw.vega, 6) == "715.411"


def test_charts_plot_the_engine_curves(lab: AppTest) -> None:
    (greek_line,) = chart_lines(lab, 0)
    sweep = curves.greek_sweep(SEED, "call", "S", SNAP.spot)
    assert list(greek_line["x"]) == list(sweep["x"])
    assert list(greek_line["y"]) == list(sweep["delta"])
    now, expiry = chart_lines(lab, 1)
    payoff = curves.payoff_curve(SEED, "call", SNAP.spot)
    assert list(now["y"]) == list(payoff["now"])
    assert list(expiry["y"]) == list(payoff["expiry"])
    assert "**Delta** :gray[vs] :primary[spot]" in texts(lab)
    captions = [c.value for c in lab.caption]
    assert markdown_safe(greek_sweep_caption("delta", "S")) in captions
    assert markdown_safe(PAYOFF_CAPTION) in captions


def test_learn_panel_explains_the_selected_greek(lab: AppTest) -> None:
    assert f"##### {markdown_safe(GREEK_DOCS['delta'].title)}" in texts(lab)
    assert any(markdown_safe(GREEK_DOCS["delta"].desk) in t for t in texts(lab))
    assert any(f"gray-badge[{markdown_safe('per $1 spot')}]" in t for t in texts(lab))
    assert [e.label for e in lab.expander] == [markdown_safe(r.title) for r in KEY_RELATIONSHIPS]


# ------------------------------------------------------------------ controls


def test_put_flips_the_delta_sign(lab: AppTest) -> None:
    assert readout(lab)["Delta"] > 0
    lab.button_group(key="lab.type").set_value("put").run()
    assert readout(lab)["Delta"] < 0
    assert_shows(lab, SEED, "put")
    # the payoff is now the put's
    _, expiry = chart_lines(lab, 1)
    assert list(expiry["y"]) == list(curves.payoff_curve(SEED, "put", SNAP.spot)["expiry"])


def test_moving_spot_reprices_and_moves_both_widgets(lab: AppTest) -> None:
    lab.slider(key="lab.S__slider").set_value(6400.0).run()
    assert lab.number_input(key="lab.S__input").value == 6400.0
    assert "`6,400 USD`" in texts(lab)
    moved = dataclasses.replace(SEED, S=6400.0)
    assert_shows(lab, moved, "call")
    assert premium(lab)[0] != "119.61"
    (greek_line,) = chart_lines(lab, 0)
    assert list(greek_line["y"]) == list(curves.greek_sweep(moved, "call", "S", SNAP.spot)["delta"])


def test_typing_a_vol_reprices_and_moves_the_slider(lab: AppTest) -> None:
    lab.number_input(key="lab.sigma__input").set_value(0.25).run()
    assert lab.slider(key="lab.sigma__slider").value == 0.25
    assert "`25.00%`" in texts(lab)
    assert_shows(lab, dataclasses.replace(SEED, sigma=0.25), "call")


def test_typing_the_longest_tenor_reprices(lab: AppTest) -> None:
    # (an out-of-range entry never reaches the script: the browser field refuses it)
    lab.number_input(key="lab.T__input").set_value(2.0).run()
    assert lab.session_state["lab.T"] == 2.0
    assert lab.slider(key="lab.T__slider").value == 2.0
    assert "`2.000 y · 730 d`" in texts(lab)
    assert_shows(lab, dataclasses.replace(SEED, T=2.0), "call")


def test_reset_restores_the_snapshot_and_a_call(lab: AppTest) -> None:
    lab.slider(key="lab.S__slider").set_value(5000.0).run()
    lab.number_input(key="lab.sigma__input").set_value(0.4).run()
    lab.number_input(key="lab.q__input").set_value(0.03).run()
    lab.button_group(key="lab.type").set_value("put").run()
    assert current_inputs(lab) != SEED
    lab.button(key="lab.reset").click().run()
    assert current_inputs(lab) == SEED
    assert lab.session_state["lab.type"] == "call"
    assert lab.slider(key="lab.S__slider").value == SEED.S
    assert lab.number_input(key="lab.sigma__input").value == SEED.sigma
    assert premium(lab)[0] == "119.61"
    assert_shows(lab, SEED, "call")


def test_vol_from_surface_reads_the_skew_at_strike_and_tenor(lab: AppTest) -> None:
    surface = default_surface()
    lab.number_input(key="lab.K__input").set_value(5800.0).run()
    lab.button(key="lab.surface_vol").click().run()
    sigma = surface.get_vol(5800.0, SEED.T)
    assert lab.session_state["lab.sigma"] == sigma
    assert lab.slider(key="lab.sigma__slider").value == sigma
    assert sigma > SEED.sigma  # equity skew: a low strike carries more vol
    assert_shows(lab, dataclasses.replace(SEED, K=5800.0, sigma=sigma), "call")


def test_greek_selection_drives_the_chart_and_the_learn_card(lab: AppTest) -> None:
    lab.button_group(key="lab.greek").set_value("gamma").run()
    assert not lab.exception, lab.exception
    shown = texts(lab)
    assert "**Gamma** :gray[vs] :primary[spot]" in shown
    assert f"##### {markdown_safe(GREEK_DOCS['gamma'].title)}" in shown
    assert f"##### {markdown_safe(GREEK_DOCS['delta'].title)}" not in shown
    assert any(markdown_safe(GREEK_DOCS["gamma"].when_large) in t for t in shown)
    assert any(f"gray-badge[{markdown_safe(GREEK_UNITS['gamma'].unit)}]" in t for t in shown)
    assert markdown_safe(greek_sweep_caption("gamma", "S")) in [c.value for c in lab.caption]
    (line,) = chart_lines(lab, 0)
    assert list(line["y"]) == list(curves.greek_sweep(SEED, "call", "S", SNAP.spot)["gamma"])


def test_x_axis_switch_sweeps_time(lab: AppTest) -> None:
    lab.button_group(key="lab.greek").set_value("vega").run()
    lab.button_group(key="lab.x").set_value("T").run()
    assert "**Vega** :gray[vs] :primary[time to expiry (yrs)]" in texts(lab)
    assert markdown_safe(greek_sweep_caption("vega", "T")) in [c.value for c in lab.caption]
    (line,) = chart_lines(lab, 0)
    sweep = curves.greek_sweep(SEED, "call", "T", SNAP.spot)
    assert list(line["x"]) == list(sweep["x"])
    assert list(line["y"]) == list(sweep["vega"])
    # the acceptance check, as plotted: long-dated options carry more vega
    assert line["y"].is_monotonic_increasing


def test_shrinking_T_spikes_the_plotted_gamma(lab: AppTest) -> None:
    lab.button_group(key="lab.greek").set_value("gamma").run()
    (month,) = chart_lines(lab, 0)
    lab.number_input(key="lab.T__input").set_value(0.006).run()
    assert "`0.006 y · 2 d`" in texts(lab)
    (days,) = chart_lines(lab, 0)
    assert days["y"].max() > 3 * month["y"].max()
    assert readout(lab)["Gamma"] > 3 * analyze_option(SEED, "call").reported.gamma


def test_inputs_survive_a_page_switch(lab: AppTest) -> None:
    lab.slider(key="lab.S__slider").set_value(6000.0).run()
    lab.button_group(key="lab.greek").set_value("theta").run()
    lab.switch_page("app_pages/home.py").run()
    lab.switch_page(PAGE).run()
    assert not lab.exception, lab.exception
    assert lab.session_state["lab.S"] == 6000.0
    assert lab.slider(key="lab.S__slider").value == 6000.0
    assert "**Theta** :gray[vs] :primary[spot]" in texts(lab)
    assert_shows(lab, dataclasses.replace(SEED, S=6000.0), "call")
