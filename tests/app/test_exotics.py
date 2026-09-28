"""The exotics page in a running app (``AppTest``): each sub-tab renders its controls,
readout, captions and Learn card; the numbers shown are the engine's (and the React app's
at the defaults); moving a control reprices; the barrier's knock-in + knock-out rows add up
to the vanilla shown; the autocallable's Monte-Carlo diagnostics are shown."""

from __future__ import annotations

from dataclasses import replace

import pytest
from streamlit.testing.v1 import AppTest

from eqd_desk.app.ui import exotics_curves as ec
from eqd_desk.app.ui.exotics_views import ASSET_CALL_HEADING, ASSET_PUT_HEADING, PARITY_HEADING
from eqd_desk.app.ui.format import fmt_money, fmt_num, fmt_pct
from eqd_desk.app.ui.state import surface
from eqd_desk.content import EXOTIC_DOCS, GREEK_DOCS, ExoticKind, markdown_safe
from eqd_desk.content.exotics import (
    AUTOCALL_PATHS_CAPTION,
    BARRIER_CHART_CAPTION,
    DIGITAL_GREEK_CAPTION,
    DIGITAL_PRICE_CAPTION,
    EXOTIC_TAB_LABELS,
    VARSWAP_SKEW_HINT,
    VARSWAP_STRIP_CAPTION,
)
from eqd_desk.data import load_snapshot
from eqd_desk.engine import GREEK_UNITS, OptionType
from eqd_desk.engine.exotics import (
    BarrierKind,
    asset_or_nothing_price,
    autocall_greeks,
    barrier_greeks,
    barrier_price,
    call_spread_replication,
    digital_greeks,
    price_autocall,
)

from .conftest import AppTestFactory

pytestmark = pytest.mark.app

SNAP = load_snapshot()

PREFIX: dict[ExoticKind, str] = {
    "barrier": "exo.bar.",
    "digital": "exo.dig.",
    "autocall": "exo.ac.",
    "varswap": "exo.vs.",
}
"""Session-key prefix of each sub-tab."""


def open_exotics(app_test: AppTestFactory, kind: ExoticKind = "barrier") -> AppTest:
    """The app on the exotics page, on sub-tab ``kind``."""
    at = app_test()
    at.run()
    at.switch_page("app_pages/exotics.py").run()
    assert not at.exception, at.exception
    if kind != "barrier":
        at.button_group(key="exo.kind").set_value(kind).run()
        assert not at.exception, at.exception
    return at


def hero(at: AppTest) -> tuple[str, str, str]:
    """(label, value, detail) of the view's hero number."""
    (metric,) = at.metric
    return metric.label, metric.value, metric.proto.delta_description


def rows(at: AppTest) -> dict[str, float]:
    """The readout table as label → numeric value (group headings dropped)."""
    table = at.table[0].value
    return {
        str(label): float(value)
        for label, value in zip(table["label"], table["value"], strict=True)
        if value == value  # NaN = a group heading
    }


def markdown(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown]


def captions(at: AppTest) -> list[str]:
    return [c.value for c in at.caption]


# ------------------------------------------------------------------ every sub-tab


@pytest.mark.parametrize("kind", list(EXOTIC_TAB_LABELS))
def test_every_sub_tab_renders_its_learn_card(app_test: AppTestFactory, kind: ExoticKind) -> None:
    at = open_exotics(app_test, kind)
    assert at.button_group(key="exo.kind").value == kind
    texts = markdown(at)
    doc = EXOTIC_DOCS[kind]
    assert f"##### {markdown_safe(doc.title)}" in texts
    for text in (doc.what, doc.behaviour, doc.risk):
        assert any(markdown_safe(text) in t for t in texts)
    assert ":gray-badge[exotic]" in texts
    # the priced exotics show the price & greeks chips; the variance swap shows none
    chips = f"{PREFIX[kind]}metric"
    assert (chips in [b.key for b in at.button_group]) == (kind != "varswap")


def test_sub_tabs_are_the_react_tabs_in_order(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    options = list(at.button_group(key="exo.kind").options)
    labels = list(EXOTIC_TAB_LABELS.values())
    assert len(options) == len(labels)
    assert all(label in option for option, label in zip(options, labels, strict=True))


# ------------------------------------------------------------------ barrier


def test_barrier_defaults_match_the_engine_and_react(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    seed = ec.barrier_seed(SNAP)
    g = barrier_greeks(seed)
    parity = ec.barrier_parity(seed)
    assert hero(at) == ("Barrier premium (USD)", "306.96", "vanilla 312.24")
    assert ":primary-badge[98% of vanilla]" in markdown(at)
    shown = rows(at)
    for k in ec.PRICED_READOUT_KEYS:
        assert shown[GREEK_UNITS[k].label] == getattr(g, k)
    assert shown["Down-out"] == parity.knock_out == g.price
    assert shown["Down-in"] == parity.knock_in
    assert shown["Sum"] == pytest.approx(parity.vanilla, rel=1e-12)
    assert PARITY_HEADING in list(at.table[0].value["label"])
    assert "**Gamma** :gray[vs] :primary[spot]" in markdown(at)
    assert markdown_safe(BARRIER_CHART_CAPTION) in captions(at)
    assert at.button_group(key="exo.bar.metric__chart").value == "gamma"
    assert at.button_group(key="exo.bar.metric").value == "gamma"


def test_moving_the_barrier_reprices(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    at.slider(key="exo.bar.H__slider").set_value(6000.0).run()
    assert not at.exception
    moved = replace(ec.barrier_seed(SNAP), H=6000.0)
    assert hero(at)[1] == fmt_money(barrier_price(moved))
    assert rows(at)["Delta"] == barrier_greeks(moved).delta
    assert any(m == "`6,000.00`" for m in markdown(at))


@pytest.mark.parametrize("kind", ["down-in", "up-out", "up-in"])
def test_knock_in_plus_knock_out_equals_the_vanilla_shown(
    app_test: AppTestFactory, kind: BarrierKind
) -> None:
    at = open_exotics(app_test)
    at.button_group(key="exo.bar.kind").set_value(kind).run()
    if kind.startswith("up"):
        at.slider(key="exo.bar.H__slider").set_value(7000.0).run()
    assert not at.exception
    i = replace(ec.barrier_seed(SNAP), kind=kind, H=7000.0 if kind.startswith("up") else 5675.0)
    _, value, detail = hero(at)
    assert value == fmt_money(barrier_price(i))
    shown = rows(at)
    direction = kind.split("-")[0].capitalize()
    knock_out, knock_in = shown[f"{direction}-out"], shown[f"{direction}-in"]
    assert shown[ec.BARRIER_KIND_LABELS[kind]] == barrier_price(i)  # the hero's own row
    assert knock_out + knock_in == pytest.approx(shown["Sum"], rel=1e-12)
    vanilla = ec.barrier_parity(i).vanilla
    assert shown["Sum"] == pytest.approx(vanilla, rel=1e-9)
    assert detail == f"vanilla {fmt_money(vanilla)}"


def test_put_toggle_surface_vol_and_reset(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    at.button_group(key="exo.bar.type").set_value("put").run()
    put = replace(ec.barrier_seed(SNAP), type="put")
    assert hero(at)[1] == fmt_money(barrier_price(put))

    at.slider(key="exo.bar.K__slider").set_value(5900.0).run()
    at.button(key="exo.bar.surface").click().run()
    vol = surface().get_vol(5900.0, 0.5)
    assert at.session_state["exo.bar.sigma"] == vol
    assert at.slider(key="exo.bar.sigma__slider").value == pytest.approx(vol)
    assert hero(at)[1] == fmt_money(barrier_price(replace(put, K=5900.0, sigma=vol)))

    at.button(key="exo.bar.reset").click().run()
    assert not at.exception
    assert at.button_group(key="exo.bar.type").value == "call"
    assert at.slider(key="exo.bar.K__slider").value == 6300.0
    assert hero(at)[1] == "306.96"


def test_chips_and_chart_selector_share_the_metric(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    at.button_group(key="exo.bar.metric").set_value("theta").run()
    assert "**Theta** :gray[vs] :primary[spot]" in markdown(at)
    assert at.button_group(key="exo.bar.metric__chart").value is None  # not a chart metric
    assert f"##### {markdown_safe(GREEK_DOCS['theta'].title)}" in markdown(at)
    at.button_group(key="exo.bar.metric__chart").set_value("vega").run()
    assert at.button_group(key="exo.bar.metric").value == "vega"
    assert "**Vega** :gray[vs] :primary[spot]" in markdown(at)


def test_inputs_survive_a_sub_tab_round_trip(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    at.slider(key="exo.bar.T__slider").set_value(1.25).run()
    at.button_group(key="exo.kind").set_value("varswap").run()
    at.button_group(key="exo.kind").set_value("barrier").run()
    assert at.slider(key="exo.bar.T__slider").value == 1.25
    assert hero(at)[1] == fmt_money(barrier_price(replace(ec.barrier_seed(SNAP), T=1.25)))


# ------------------------------------------------------------------ digital


def test_digital_defaults_and_replication(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "digital")
    seed = ec.digital_seed(SNAP)
    g = digital_greeks(seed)
    assert hero(at) == ("Digital premium (USD)", "53.14", "spread 53.14 · size 0.800×")
    shown = rows(at)
    for k in ec.PRICED_READOUT_KEYS:
        assert shown[GREEK_UNITS[k].label] == getattr(g, k)
    assert "**Value** :gray[vs] :primary[spot]" in markdown(at)
    assert markdown_safe(DIGITAL_PRICE_CAPTION) in captions(at)

    at.slider(key="exo.dig.width__slider").set_value(400.0).run()
    spread = call_spread_replication(seed, 400.0)
    assert hero(at)[2] == ec.digital_detail(spread, 100.0, 400.0)
    assert any(f"spread {fmt_money(spread)}" in c for c in captions(at))

    at.button_group(key="exo.dig.metric__chart").set_value("delta").run()
    assert "**Delta** :gray[vs] :primary[spot]" in markdown(at)
    assert markdown_safe(DIGITAL_GREEK_CAPTION) in captions(at)


@pytest.mark.parametrize("option", ["call", "put"])
def test_digital_asset_payout(app_test: AppTestFactory, option: OptionType) -> None:
    at = open_exotics(app_test, "digital")
    assert at.button_group(key="exo.dig.payout").value == "cash"
    assert not at.slider(key="exo.dig.cash__slider").disabled
    if option == "put":
        at.button_group(key="exo.dig.type").set_value("put").run()
    at.button_group(key="exo.dig.payout").set_value("asset").run()
    assert not at.exception
    i = replace(ec.digital_seed(SNAP), type=option)
    price = asset_or_nothing_price(i)
    repl = ec.replication_price(i, 125.0, "asset")
    assert hero(at) == (
        "Digital premium (USD)",
        fmt_money(price),
        ec.digital_detail(repl, i.K, 125.0, label="replication"),
    )
    assert at.slider(key="exo.dig.cash__slider").disabled  # Q plays no part
    shown = rows(at)
    g = ec.payout_greeks(i, "asset")
    for k in ec.PRICED_READOUT_KEYS:
        assert shown[GREEK_UNITS[k].label] == getattr(g, k)
    d = ec.asset_decomposition(i)
    assert shown["K × cash digital"] == d.k_digitals
    assert shown[f"Vanilla {option}"] == d.sign * d.vanilla
    assert shown["Sum"] == pytest.approx(price, rel=1e-12)
    heading = ASSET_CALL_HEADING if option == "call" else ASSET_PUT_HEADING
    assert heading in list(at.table[0].value["label"])
    spreads = ec.digital_series_labels(option, "asset")[0]
    assert f"**{spreads}** :gray[vs] :primary[width Δ]" in markdown(at)
    recipe = ec.replication_recipe(i, 125.0, "asset")
    assert any(recipe in c and f"replication {fmt_money(repl)}" in c for c in captions(at))

    at.button(key="exo.dig.reset").click().run()
    assert at.button_group(key="exo.dig.payout").value == "cash"
    assert hero(at)[1] == "53.14"


def test_digital_near_expiry_reprices(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "digital")
    at.slider(key="exo.dig.T__slider").set_value(0.01).run()
    at.slider(key="exo.dig.cash__slider").set_value(250.0).run()
    i = replace(ec.digital_seed(SNAP), T=0.01, cash=250.0)
    assert hero(at)[1] == fmt_money(digital_greeks(i).price)
    assert rows(at)["Gamma"] == digital_greeks(i).gamma


# ------------------------------------------------------------------ autocallable


def test_autocall_value_and_diagnostics(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "autocall")
    seed = ec.autocall_seed(SNAP)
    res = price_autocall(seed, ec.AUTOCALL_PRICE_PATHS)
    g = autocall_greeks(seed, ec.AUTOCALL_GREEK_PATHS)
    assert hero(at) == ("Note value (par 100)", "103.20", "103.2% of par")
    assert ":gray-badge[MC ±0.060]" in markdown(at)
    assert ":gray-badge[8 GBM paths]" in markdown(at)
    table = at.table[0].value
    labels = list(table["label"])
    assert labels[:5] == [
        "Diagnostics",
        "P(autocall)",
        "P(capital loss)",
        "Expected life",
        "Greeks (MC)",
    ]
    shown = rows(at)
    assert shown["P(autocall)"] == res.prob_autocall
    assert shown["P(capital loss)"] == res.prob_capital_loss
    assert shown["Expected life"] == res.expected_life
    for k in ec.AUTOCALL_READOUT_KEYS:
        assert shown[GREEK_UNITS[k].label] == getattr(g, k)
    assert "Gamma" not in shown  # MC gamma is too noisy to print (React shows none)
    assert markdown_safe(AUTOCALL_PATHS_CAPTION) in captions(at)
    assert fmt_pct(res.prob_autocall, 1) == "80.8%"


def test_autocall_controls_reprice(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "autocall")
    at.toggle(key="exo.ac.memory").set_value(False).run()
    at.slider(key="exo.ac.n_obs__slider").set_value(4).run()
    at.slider(key="exo.ac.pb__slider").set_value(0.8).run()
    assert not at.exception
    i = replace(ec.autocall_seed(SNAP), memory=False, n_obs=4, protection_barrier=0.8)
    res = price_autocall(i, ec.AUTOCALL_PRICE_PATHS)
    assert hero(at)[1] == fmt_money(res.price)
    assert rows(at)["P(capital loss)"] == res.prob_capital_loss
    assert any(m == "`4`" for m in markdown(at))


# ------------------------------------------------------------------ variance swap


def test_varswap_defaults_and_skew(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "varswap")
    seed = ec.varswap_seed(SNAP)
    data = ec.varswap_data(seed, S=SNAP.spot, r=SNAP.r, q=SNAP.q)
    assert hero(at) == ("Fair volatility", "17.24%", "√(fair variance)")
    assert ":primary-badge[VIX-style]" in markdown(at)
    shown = rows(at)
    assert shown["Fair variance"] == data.fair_variance
    assert shown["ATM vol"] == data.atm_vol
    assert shown["Convexity premium"] == data.convexity_premium
    assert shown["Forward"] == data.forward
    assert markdown_safe(VARSWAP_SKEW_HINT) in captions(at)
    assert markdown_safe(VARSWAP_STRIP_CAPTION) in captions(at)

    at.slider(key="exo.vs.slope__slider").set_value(-0.9).run()
    steeper = ec.varswap_data(replace(seed, slope=-0.9), S=SNAP.spot, r=SNAP.r, q=SNAP.q)
    assert hero(at)[1] == fmt_pct(steeper.fair_vol)
    assert steeper.fair_vol > data.fair_vol  # steeper skew, richer variance
    assert rows(at)["Convexity premium"] == steeper.convexity_premium


def test_varswap_skew_switch(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "varswap")
    assert at.toggle(key="exo.vs.skew").value is True
    at.toggle(key="exo.vs.skew").set_value(False).run()
    assert not at.exception
    seed = ec.varswap_seed(SNAP)
    flat = ec.varswap_data(replace(seed, skew=False), S=SNAP.spot, r=SNAP.r, q=SNAP.q)
    assert hero(at)[1] == fmt_pct(flat.fair_vol)
    assert abs(rows(at)["Convexity premium"]) < 2e-4  # no skew, no convexity premium
    assert at.slider(key="exo.vs.slope__slider").disabled
    assert at.slider(key="exo.vs.curv__slider").disabled
    assert at.slider(key="exo.vs.slope__slider").value == seed.slope  # kept, not reset
    assert any(c.startswith("Skew off (flat smile)") for c in captions(at))

    at.toggle(key="exo.vs.skew").set_value(True).run()
    assert hero(at)[1] == "17.24%"
    assert not at.slider(key="exo.vs.slope__slider").disabled


def test_varswap_strip_truncation(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "varswap")
    at.slider(key="exo.vs.lo__slider").set_value(0.8).run()
    at.slider(key="exo.vs.hi__slider").set_value(1.25).run()
    c = replace(ec.varswap_seed(SNAP), lo_mult=0.8, hi_mult=1.25)
    data = ec.varswap_data(c, S=SNAP.spot, r=SNAP.r, q=SNAP.q)
    assert hero(at)[1] == fmt_pct(data.fair_vol)
    assert any(f"{fmt_num(c.slope, 3)}" in cap and "400 strikes" in cap for cap in captions(at))
