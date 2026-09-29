"""The exotics page in a running app (``AppTest``): each sub-tab renders its controls,
readout, captions and Learn card; the numbers shown are the engine's (and the React app's
at the defaults); moving a control reprices; the barrier's knock-in + knock-out rows add up
to the vanilla shown, switching its side mirrors H, and a dead barrier says why; the
autocallable's Monte-Carlo diagnostics are shown, and its chips offer no gamma; built
charts are cached."""

from __future__ import annotations

from dataclasses import replace

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup

from eqd_desk.app.ui import exotics_curves as ec
from eqd_desk.app.ui import exotics_views as ev
from eqd_desk.app.ui.exotics_display import (
    ASSET_CALL_HEADING,
    ASSET_PUT_HEADING,
    K_DIGITALS_LABEL,
    PARITY_HEADING,
    vanilla_term_label,
)
from eqd_desk.app.ui.format import fmt_money, fmt_num, fmt_pct
from eqd_desk.app.ui.state import surface
from eqd_desk.content import EXOTIC_DOCS, GREEK_DOCS, ExoticKind, markdown_safe
from eqd_desk.content.exotics import (
    AUTOCALL_GAMMA_NOTE,
    AUTOCALL_PATHS_CAPTION,
    BARRIER_BREACHED_NOTES,
    BARRIER_CHART_CAPTION,
    BARRIER_DIRECTION_HINT,
    BARRIER_KNOCK_HINT,
    BARRIER_STRIKE_BEYOND_NOTES,
    DIGITAL_ASSET_PRICE_CAPTIONS,
    DIGITAL_GREEK_CAPTION,
    DIGITAL_PAYOUT_HINT,
    DIGITAL_PRICE_CAPTION,
    EXOTIC_TAB_LABELS,
    VARSWAP_SKEW_HINT,
    VARSWAP_SKEW_SWITCH_HINT,
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

from .conftest import AppTestFactory, slider_wkey, wkey

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
        at.button_group(key=wkey(at, "exo.kind")).set_value(kind).run()
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


def chips(at: AppTest, prefix: str = "exo.bar.") -> ButtonGroup[str]:
    """The Learn panel's price & greek chips of the view with session-key ``prefix``."""
    return at.button_group(key=wkey(at, f"{prefix}metric"))


def chart_metric(at: AppTest, prefix: str = "exo.bar.") -> ButtonGroup[str]:
    """The chart's own metric selector of the view with session-key ``prefix``."""
    return at.button_group(key=wkey(at, f"{prefix}metric__chart"))


# ------------------------------------------------------------------ every sub-tab


@pytest.mark.parametrize("kind", list(EXOTIC_TAB_LABELS))
def test_every_sub_tab_renders_its_learn_card(app_test: AppTestFactory, kind: ExoticKind) -> None:
    at = open_exotics(app_test, kind)
    assert at.button_group(key=wkey(at, "exo.kind")).value == kind
    texts = markdown(at)
    doc = EXOTIC_DOCS[kind]
    assert f"##### {markdown_safe(doc.title)}" in texts
    for text in (doc.what, doc.behaviour, doc.risk):
        assert any(markdown_safe(text) in t for t in texts)
    assert ":gray-badge[exotic]" in texts
    # the priced exotics show the price & greeks chips; the variance swap shows none
    chip_key = wkey(at, f"{PREFIX[kind]}metric")
    assert (chip_key in [b.key for b in at.button_group]) == (kind != "varswap")


def test_sub_tabs_are_the_react_tabs_in_order(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    options = list(at.button_group(key=wkey(at, "exo.kind")).options)
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
    assert "###### **Gamma** :gray[vs] :primary[spot]" in markdown(at)
    assert markdown_safe(BARRIER_CHART_CAPTION) in captions(at)
    assert chart_metric(at).value == "gamma"
    assert chips(at).value == "gamma"


def test_moving_the_barrier_reprices(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    at.slider(key=slider_wkey(at, "exo.bar.H")).set_value(6000.0).run()
    assert not at.exception
    moved = replace(ec.barrier_seed(SNAP), H=6000.0)
    assert hero(at)[1] == fmt_money(barrier_price(moved))
    assert rows(at)["Delta"] == barrier_greeks(moved).delta
    assert any(m == "`6,000.00`" for m in markdown(at))


def pick_barrier(at: AppTest, kind: BarrierKind) -> None:
    """Pick a barrier kind through its two controls (direction, then knock)."""
    direction, knock = ec.barrier_sides(kind)
    at.button_group(key=wkey(at, "exo.bar.dir")).set_value(direction).run()
    at.button_group(key=wkey(at, "exo.bar.knock")).set_value(knock).run()
    assert not at.exception, at.exception


def notes(at: AppTest) -> list[str]:
    """The texts of the ``st.info`` notes on the page."""
    return [i.value for i in at.info]


def test_barrier_kind_is_a_direction_and_a_knock(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    direction = at.button_group(key=wkey(at, "exo.bar.dir"))
    knock = at.button_group(key=wkey(at, "exo.bar.knock"))
    assert (direction.value, knock.value) == ("down", "out")
    assert list(direction.options) == ["Down", "Up"]
    assert list(knock.options) == ["Out", "In"]
    assert direction.help == markdown_safe(BARRIER_DIRECTION_HINT)
    assert knock.help == markdown_safe(BARRIER_KNOCK_HINT)
    assert notes(at) == []  # the seed's barrier is live


@pytest.mark.parametrize("kind", ["down-in", "up-out", "up-in"])
def test_knock_in_plus_knock_out_equals_the_vanilla_shown(
    app_test: AppTestFactory, kind: BarrierKind
) -> None:
    at = open_exotics(app_test)
    pick_barrier(at, kind)
    # switching to "up" mirrored the seed's barrier above spot: the option is live
    H = 7025.0 if kind.startswith("up") else 5675.0
    assert at.session_state["exo.bar.H"] == H
    assert notes(at) == []
    i = replace(ec.barrier_seed(SNAP), kind=kind, H=H)
    _, value, detail = hero(at)
    assert value == fmt_money(barrier_price(i))
    assert barrier_price(i) > 0
    shown = rows(at)
    direction = kind.split("-")[0].capitalize()
    knock_out, knock_in = shown[f"{direction}-out"], shown[f"{direction}-in"]
    assert shown[ec.BARRIER_KIND_LABELS[kind]] == barrier_price(i)  # the hero's own row
    assert knock_out + knock_in == pytest.approx(shown["Sum"], rel=1e-12)
    vanilla = ec.barrier_parity(i).vanilla
    assert shown["Sum"] == pytest.approx(vanilla, rel=1e-9)
    assert detail == f"vanilla {fmt_money(vanilla)}"


def test_switching_side_mirrors_h_and_a_dead_barrier_says_why(app_test: AppTestFactory) -> None:
    """Regression: "Up-out" kept H = 5,675 below spot 6,312: already knocked out, a zero
    premium, flat greeks, and nothing said why."""
    at = open_exotics(app_test)
    at.button_group(key=wkey(at, "exo.bar.dir")).set_value("up").run()
    assert at.session_state["exo.bar.H"] == 7025.0  # mirrored above spot, on the grid
    assert at.slider(key=slider_wkey(at, "exo.bar.H")).value == 7025.0
    up_out = replace(ec.barrier_seed(SNAP), kind="up-out", H=7025.0)
    assert hero(at)[1] == fmt_money(barrier_price(up_out)) != "0.00"
    assert notes(at) == []

    # spot dragged through the barrier: the knock-out is dead, and the page says why
    at.slider(key=slider_wkey(at, "exo.bar.S")).set_value(7100.0).run()
    assert hero(at)[1] == "0.00"
    assert notes(at) == [markdown_safe(BARRIER_BREACHED_NOTES["up-out"])]
    at.button_group(key=wkey(at, "exo.bar.knock")).set_value("in").run()
    assert notes(at) == [markdown_safe(BARRIER_BREACHED_NOTES["up-in"])]
    breached_in = replace(up_out, S=7100.0, kind="up-in")
    assert hero(at)[1] == fmt_money(ec.barrier_parity(breached_in).vanilla)

    # back to "down": H = 7,025 is below spot 7,100, already a live down barrier: it stays
    at.button_group(key=wkey(at, "exo.bar.dir")).set_value("down").run()
    assert at.session_state["exo.bar.H"] == 7025.0
    assert notes(at) == []

    # an up-and-out call struck above its barrier can never pay
    at.slider(key=slider_wkey(at, "exo.bar.S")).set_value(6300.0).run()
    at.button_group(key=wkey(at, "exo.bar.dir")).set_value("up").run()
    at.button_group(key=wkey(at, "exo.bar.knock")).set_value("out").run()
    assert at.session_state["exo.bar.H"] == 7025.0
    at.slider(key=slider_wkey(at, "exo.bar.K")).set_value(7100.0).run()
    assert hero(at)[1] == "0.00"
    assert notes(at) == [markdown_safe(BARRIER_STRIKE_BEYOND_NOTES["out"])]


def test_put_toggle_surface_vol_and_reset(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    at.button_group(key=wkey(at, "exo.bar.type")).set_value("put").run()
    put = replace(ec.barrier_seed(SNAP), type="put")
    assert hero(at)[1] == fmt_money(barrier_price(put))

    at.slider(key=slider_wkey(at, "exo.bar.K")).set_value(5900.0).run()
    at.button(key="exo.bar.surface").click().run()
    vol = surface().get_vol(5900.0, 0.5)
    assert at.session_state["exo.bar.sigma"] == vol
    assert at.slider(key=slider_wkey(at, "exo.bar.sigma")).value == pytest.approx(vol)
    assert hero(at)[1] == fmt_money(barrier_price(replace(put, K=5900.0, sigma=vol)))

    pick_barrier(at, "up-in")
    at.button(key="exo.bar.reset").click().run()
    assert not at.exception
    assert at.button_group(key=wkey(at, "exo.bar.type")).value == "call"
    assert at.button_group(key=wkey(at, "exo.bar.dir")).value == "down"
    assert at.button_group(key=wkey(at, "exo.bar.knock")).value == "out"
    assert at.slider(key=slider_wkey(at, "exo.bar.H")).value == 5675.0
    assert at.slider(key=slider_wkey(at, "exo.bar.K")).value == 6300.0
    assert hero(at)[1] == "306.96"


def test_chips_and_chart_selector_share_the_metric(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    chips(at).set_value("theta").run()
    assert "###### **Theta** :gray[vs] :primary[spot]" in markdown(at)
    assert chart_metric(at).value is None  # not a chart metric
    assert f"##### {markdown_safe(GREEK_DOCS['theta'].title)}" in markdown(at)
    chart_metric(at).set_value("vega").run()
    assert chips(at).value == "vega"
    assert "###### **Vega** :gray[vs] :primary[spot]" in markdown(at)


def test_chart_selector_follows_the_chips_out_of_and_back_into_its_metrics(
    app_test: AppTestFactory,
) -> None:
    """A selector showing no selection (theta picked on the chips) must pick up the next
    chart metric the chips choose, not keep showing none."""
    at = open_exotics(app_test)
    chips(at).set_value("rho").run()
    assert chart_metric(at).value is None
    chips(at).set_value("delta").run()
    assert chart_metric(at).value == "delta"
    assert "###### **Delta** :gray[vs] :primary[spot]" in markdown(at)
    chips(at).set_value("vega").run()
    assert chart_metric(at).value == "vega"
    chart_metric(at).set_value("price").run()
    assert chips(at).value == "price"
    assert chart_metric(at).value == "price"


def test_inputs_survive_a_sub_tab_round_trip(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test)
    at.slider(key=slider_wkey(at, "exo.bar.T")).set_value(1.25).run()
    at.toggle(key=wkey(at, "exo.bar.vanilla")).set_value(False).run()
    chart_metric(at).set_value("vega").run()
    at.button_group(key=wkey(at, "exo.kind")).set_value("varswap").run()
    at.button_group(key=wkey(at, "exo.kind")).set_value("barrier").run()
    assert at.slider(key=slider_wkey(at, "exo.bar.T")).value == 1.25
    assert at.toggle(key=wkey(at, "exo.bar.vanilla")).value is False
    assert chart_metric(at).value == "vega"
    assert chips(at).value == "vega"
    moved = replace(ec.barrier_seed(SNAP), T=1.25)
    assert hero(at)[1] == fmt_money(barrier_price(moved))
    assert rows(at)["Vega"] == barrier_greeks(moved).vega


# ------------------------------------------------------------------ digital


def test_digital_defaults_and_replication(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "digital")
    seed = ec.digital_seed(SNAP)
    g = digital_greeks(seed)
    assert hero(at) == ("Digital premium (USD)", "53.14", "spread 53.14 · size 0.800×")
    shown = rows(at)
    for k in ec.PRICED_READOUT_KEYS:
        assert shown[GREEK_UNITS[k].label] == getattr(g, k)
    assert "###### **Value** :gray[vs] :primary[spot]" in markdown(at)
    assert markdown_safe(DIGITAL_PRICE_CAPTION) in captions(at)

    at.slider(key=slider_wkey(at, "exo.dig.width")).set_value(400.0).run()
    spread = call_spread_replication(seed, 400.0)
    assert hero(at)[2] == ec.digital_detail(spread, 100.0, 400.0)
    assert any(f"spread {fmt_money(spread)}" in c for c in captions(at))

    chart_metric(at, "exo.dig.").set_value("delta").run()
    assert "###### **Delta** :gray[vs] :primary[spot]" in markdown(at)
    assert markdown_safe(DIGITAL_GREEK_CAPTION) in captions(at)


@pytest.mark.parametrize("option", ["call", "put"])
def test_digital_asset_payout(app_test: AppTestFactory, option: OptionType) -> None:
    at = open_exotics(app_test, "digital")
    payout = at.button_group(key=wkey(at, "exo.dig.payout"))
    assert payout.value == "cash"
    assert list(payout.options) == ["Cash", "Asset"]  # short: they share one row
    assert payout.help == markdown_safe(DIGITAL_PAYOUT_HINT)  # the full names
    assert not at.slider(key=slider_wkey(at, "exo.dig.cash")).disabled
    if option == "put":
        at.button_group(key=wkey(at, "exo.dig.type")).set_value("put").run()
    at.button_group(key=wkey(at, "exo.dig.payout")).set_value("asset").run()
    assert not at.exception
    i = replace(ec.digital_seed(SNAP), type=option)
    price = asset_or_nothing_price(i)
    repl = ec.replication_price(i, 125.0, "asset")
    assert hero(at) == (
        "Digital premium (USD)",
        fmt_money(price),
        ec.digital_detail(repl, i.K, 125.0, label="replication"),
    )
    assert at.slider(key=slider_wkey(at, "exo.dig.cash")).disabled  # Q plays no part
    shown = rows(at)
    g = ec.payout_greeks(i, "asset")
    for k in ec.PRICED_READOUT_KEYS:
        assert shown[GREEK_UNITS[k].label] == getattr(g, k)
    d = ec.asset_decomposition(i)
    # each row is a signed term of the heading, so the rows read down to the Sum
    assert shown[K_DIGITALS_LABEL] == d.k_digitals
    assert shown[vanilla_term_label(option)] == d.sign * d.vanilla
    assert f"Vanilla {option}" not in shown
    assert shown[K_DIGITALS_LABEL] + shown[vanilla_term_label(option)] == pytest.approx(
        shown["Sum"], rel=1e-12
    )
    assert shown["Sum"] == pytest.approx(price, rel=1e-12)
    heading = ASSET_CALL_HEADING if option == "call" else ASSET_PUT_HEADING
    assert heading in list(at.table[0].value["label"])
    spreads = ec.digital_series_labels(option, "asset")[0]
    assert f"###### **{spreads}** :gray[vs] :primary[width Δ]" in markdown(at)
    recipe = ec.replication_recipe(i, 125.0, "asset")
    assert any(recipe in c and f"replication {fmt_money(repl)}" in c for c in captions(at))
    # the value chart's caption reads the asset-or-nothing against its own replication
    assert markdown_safe(DIGITAL_ASSET_PRICE_CAPTIONS[option]) in captions(at)
    assert markdown_safe(DIGITAL_PRICE_CAPTION) not in captions(at)

    at.button(key="exo.dig.reset").click().run()
    assert at.button_group(key=wkey(at, "exo.dig.payout")).value == "cash"
    assert hero(at)[1] == "53.14"
    assert markdown_safe(DIGITAL_PRICE_CAPTION) in captions(at)


def test_digital_near_expiry_reprices(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "digital")
    at.slider(key=slider_wkey(at, "exo.dig.T")).set_value(0.01).run()
    at.slider(key=slider_wkey(at, "exo.dig.cash")).set_value(250.0).run()
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


def test_autocall_chips_offer_no_gamma(app_test: AppTestFactory) -> None:
    """Regression: the Learn chips offered Gamma, which the note never reports (nothing to
    highlight, and a vanilla gamma card beside a short-put-like note)."""
    at = open_exotics(app_test, "autocall")
    chip_row = chips(at, "exo.ac.")
    assert list(chip_row.options) == ["Price", "Delta", "Vega", "Theta", "Rho"]
    assert chip_row.value == "delta"
    assert markdown_safe(AUTOCALL_GAMMA_NOTE) in captions(at)
    chip_row.set_value("vega").run()
    assert chips(at, "exo.ac.").value == "vega"
    assert f"##### {markdown_safe(GREEK_DOCS['vega'].title)}" in markdown(at)
    # the closed-form exotics keep every chip, and no gamma note
    at.button_group(key=wkey(at, "exo.kind")).set_value("barrier").run()
    assert "Gamma" in list(chips(at).options)
    assert markdown_safe(AUTOCALL_GAMMA_NOTE) not in captions(at)


def test_autocall_controls_reprice(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "autocall")
    at.toggle(key=wkey(at, "exo.ac.memory")).set_value(False).run()
    at.slider(key=slider_wkey(at, "exo.ac.n_obs")).set_value(4).run()
    at.slider(key=slider_wkey(at, "exo.ac.pb")).set_value(0.8).run()
    assert not at.exception
    i = replace(ec.autocall_seed(SNAP), memory=False, n_obs=4, protection_barrier=0.8)
    res = price_autocall(i, ec.AUTOCALL_PRICE_PATHS)
    assert hero(at)[1] == fmt_money(res.price)
    assert rows(at)["P(capital loss)"] == res.prob_capital_loss
    assert any(m == "`4`" for m in markdown(at))

    at.button(key="exo.ac.reset").click().run()
    assert not at.exception
    assert at.toggle(key=wkey(at, "exo.ac.memory")).value is True
    assert at.slider(key=slider_wkey(at, "exo.ac.n_obs")).value == ec.autocall_seed(SNAP).n_obs
    assert hero(at)[1] == "103.20"


# ------------------------------------------------------------------ variance swap


def test_varswap_defaults_and_skew(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "varswap")
    seed = ec.varswap_seed(SNAP)
    data = ec.varswap_data(seed, S=SNAP.spot, r=SNAP.r, q=SNAP.q)
    assert hero(at) == ("Fair volatility", "17.16%", "√(fair variance)")
    assert ":primary-badge[VIX-style]" in markdown(at)
    shown = rows(at)
    assert shown["Fair variance"] == data.fair_variance
    assert shown["ATM vol"] == data.atm_vol
    assert shown["Convexity premium"] == data.convexity_premium
    assert shown["Forward"] == data.forward
    assert markdown_safe(VARSWAP_SKEW_HINT) in captions(at)
    assert markdown_safe(VARSWAP_STRIP_CAPTION) in captions(at)

    at.slider(key=slider_wkey(at, "exo.vs.slope")).set_value(-0.9).run()
    steeper = ec.varswap_data(replace(seed, slope=-0.9), S=SNAP.spot, r=SNAP.r, q=SNAP.q)
    assert hero(at)[1] == fmt_pct(steeper.fair_vol)
    assert steeper.fair_vol > data.fair_vol  # steeper skew, richer variance
    assert rows(at)["Convexity premium"] == steeper.convexity_premium


def test_varswap_skew_switch(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "varswap")
    assert at.toggle(key=wkey(at, "exo.vs.skew")).value is True
    at.toggle(key=wkey(at, "exo.vs.skew")).set_value(False).run()
    assert not at.exception
    seed = ec.varswap_seed(SNAP)
    flat = ec.varswap_data(replace(seed, skew=False), S=SNAP.spot, r=SNAP.r, q=SNAP.q)
    assert hero(at)[1] == fmt_pct(flat.fair_vol)
    assert abs(rows(at)["Convexity premium"]) < 2e-4  # no skew, no convexity premium
    assert at.slider(key=slider_wkey(at, "exo.vs.slope")).disabled
    assert at.slider(key=slider_wkey(at, "exo.vs.curv")).disabled
    assert at.slider(key=slider_wkey(at, "exo.vs.slope")).value == seed.slope  # kept, not reset
    assert any(c.startswith("Skew off (flat smile)") for c in captions(at))

    at.toggle(key=wkey(at, "exo.vs.skew")).set_value(True).run()
    assert hero(at)[1] == "17.16%"
    assert not at.slider(key=slider_wkey(at, "exo.vs.slope")).disabled


def test_varswap_reset_restores_the_skew_switch(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "varswap")
    skew = at.toggle(key=wkey(at, "exo.vs.skew"))
    assert skew.help == markdown_safe(VARSWAP_SKEW_SWITCH_HINT)
    skew.set_value(False).run()
    at.slider(key=slider_wkey(at, "exo.vs.atm")).set_value(0.25).run()
    assert at.toggle(key=wkey(at, "exo.vs.skew")).value is False
    at.button(key="exo.vs.reset").click().run()
    assert not at.exception
    assert at.session_state["exo.vs.skew"] is True  # the canonical value, and the widget:
    assert at.toggle(key=wkey(at, "exo.vs.skew")).value is True
    assert not at.slider(key=slider_wkey(at, "exo.vs.slope")).disabled
    assert hero(at)[1] == "17.16%"


def test_varswap_strip_truncation(app_test: AppTestFactory) -> None:
    at = open_exotics(app_test, "varswap")
    at.slider(key=slider_wkey(at, "exo.vs.lo")).set_value(0.8).run()
    at.slider(key=slider_wkey(at, "exo.vs.hi")).set_value(1.25).run()
    c = replace(ec.varswap_seed(SNAP), lo_mult=0.8, hi_mult=1.25)
    data = ec.varswap_data(c, S=SNAP.spot, r=SNAP.r, q=SNAP.q)
    assert hero(at)[1] == fmt_pct(data.fair_vol)
    assert any(f"{fmt_num(c.slope, 3)}" in cap and "400 strikes" in cap for cap in captions(at))


# ------------------------------------------------------------------ chart cache


def test_chart_cache_reuses_a_chart_for_the_same_inputs() -> None:
    """The views wrap the pure builders in ``st.cache_resource``: the same inputs give the
    very same chart object, other inputs a new one."""
    i = ec.autocall_seed(SNAP)
    paths = ec.sample_paths(i)
    first = ev.cached_autocall_chart(paths, i)
    assert ev.cached_autocall_chart(paths.copy(), i) is first  # same content, same chart
    other = replace(i, protection_barrier=0.5)
    assert ev.cached_autocall_chart(paths, other) is not first
