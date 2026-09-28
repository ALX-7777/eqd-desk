"""The strategy-builder page, driven headless: the numbers shown equal the engine's (and the
React app's for the default butterfly), and every control edits the position with the
React semantics (presets rebuild, hand edits make it custom, Reset restores the seed)."""

from __future__ import annotations

import dataclasses

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Widget

from eqd_desk.app.ui import strategy_builder_state as sb
from eqd_desk.app.ui.format import MINUS, fmt_money, fmt_num
from eqd_desk.content import GREEK_DOCS, STRATEGY_DOCS, markdown_safe
from eqd_desk.content.strategies import CUSTOM_STRUCTURE_NOTE, EMPTY_LEGS_HINT
from eqd_desk.data import default_surface, load_snapshot
from eqd_desk.engine import GREEK_UNITS
from eqd_desk.engine.presets import PRESETS, PresetName, PresetParams, build_preset
from eqd_desk.engine.strategy import Leg, MarketParams, analyze_position

from .conftest import AppTestFactory

pytestmark = pytest.mark.app

PAGE = "app_pages/strategy_builder.py"
SNAP = load_snapshot()
SURFACE = default_surface()
SEED = MarketParams(S=SNAP.spot, r=SNAP.r, q=SNAP.q)


@pytest.fixture
def at(app_test: AppTestFactory) -> AppTest:
    """The app, on the strategy builder."""
    app = app_test()
    app.run()
    app.switch_page(PAGE).run()
    assert not app.exception, app.exception
    return app


def run(target: AppTest | Widget) -> AppTest:
    """Rerun the app after an interaction (``target`` is the AppTest or the widget just
    set/clicked) and check it did not raise."""
    at = target.run()
    assert not at.exception, at.exception
    return at


def engine_legs(
    name: PresetName, *, spot: float = SNAP.spot, days: int = 30, wing: float = 0.05
) -> tuple[Leg, ...]:
    return tuple(
        build_preset(
            name,
            PresetParams(
                S=spot, base_t=days / 365, width_pct=wing, strike_step=25, vol_for=SURFACE.get_vol
            ),
        )
    )


def legs(at: AppTest) -> tuple[Leg, ...]:
    value: tuple[Leg, ...] = at.session_state[sb.LEGS_KEY]
    return value


def premium(at: AppTest) -> str:
    return at.metric[0].value


def readout(at: AppTest) -> dict[str, float]:
    """Greek label → value of the net-position table (group headings dropped)."""
    frame = at.table[0].value
    labels = [str(x) for x in frame["label"]]
    values = [float(x) for x in frame["value"]]
    return {k: v for k, v in zip(labels, values, strict=True) if v == v}  # NaN = group heading


def assert_readout_is_engine(at: AppTest, position: tuple[Leg, ...], m: MarketParams) -> None:
    expected = analyze_position(position, m).reported.as_dict()
    shown = readout(at)
    for key, unit in GREEK_UNITS.items():
        if key == "price":
            continue
        assert shown[unit.label] == expected[key], key
    price = analyze_position(position, m).price
    assert premium(at) == premium_text(price)


def premium_text(price: float) -> str:
    """The hero as React prints it: a debit (≥ 0) as −x.xx in plain text, a credit as +x.xx
    in green."""
    if price >= 0:
        return f"{MINUS}{fmt_money(price)}"
    return f":green[+{fmt_money(-price)}]"


def markdowns(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown]


def preset_label(at: AppTest, name: str) -> str:
    return at.button(key=sb.preset_button_key(name)).label  # type: ignore[arg-type]


# ------------------------------------------------------------------ default state


def test_default_butterfly_matches_the_react_app(at: AppTest) -> None:
    # Numbers read off the React reference screenshot (2_strategy_builder.png).
    assert premium(at) == f"{MINUS}146.39"
    shown = readout(at)
    assert fmt_num(shown["Delta"]) == "-0.12596"
    assert fmt_num(shown["Vega"]) == "-7.9708"
    assert fmt_num(shown["Theta"]) == "1.8962"
    assert fmt_num(shown["Rho"]) == "-0.77382"
    assert fmt_num(shown["Gamma"]) == "-0.0017380"
    assert fmt_num(shown["Vanna"]) == "0.010788"
    assert fmt_num(shown["Volga"]) == "0.74278"
    assert fmt_num(shown["Charm"]) == "-0.00029946"
    assert legs(at) == engine_legs("butterfly")
    assert_readout_is_engine(at, engine_legs("butterfly"), SEED)
    assert at.metric[0].label == "Net premium (USD)"
    md = markdowns(at)
    assert ":primary-badge[DEBIT]" in md
    assert ":gray-badge[3 legs]" in md
    assert ":gray-badge[preset]" in md


def test_default_legs_table_shows_the_react_fields(at: AppTest) -> None:
    rows = [
        (
            at.number_input(key=sb.leg_widget_key(f"butterfly-{i}", "quantity")).value,
            at.number_input(key=sb.leg_widget_key(f"butterfly-{i}", "K")).value,
            at.number_input(key=sb.leg_widget_key(f"butterfly-{i}", "days")).value,
            at.number_input(key=sb.leg_widget_key(f"butterfly-{i}", "vol")).value,
        )
        for i in range(3)
    ]
    assert rows == [(1, 5975.0, 30, 16.72), (2, 6300.0, 30, 14.0), (1, 6625.0, 30, 11.73)]
    sides = [at.button(key=sb.leg_widget_key(f"butterfly-{i}", "side")).label for i in range(3)]
    assert sides == [":green[**L**]", ":red[**S**]", ":green[**L**]"]
    assert at.button(key=sb.leg_widget_key("butterfly-0", "type")).label == ":primary[**C**]"


def test_preset_grid_highlights_only_the_active_preset(at: AppTest) -> None:
    labels = {p.name: preset_label(at, p.name) for p in PRESETS}
    assert labels["butterfly"] == ":primary[**Butterfly**]"
    assert all(labels[p.name] == p.label for p in PRESETS if p.name != "butterfly")


def test_break_evens_and_learn_panel(at: AppTest) -> None:
    md = markdowns(at)
    assert ":small[:gray[Break-even at expiry]] `6,121.39` · `6,478.61`" in md
    doc = STRATEGY_DOCS["butterfly"]
    assert any(markdown_safe(doc.view) in m for m in md)
    assert any(markdown_safe(doc.risk) in m for m in md)
    assert ":gray-badge[Butterfly]" in md
    captions = [c.value for c in at.caption]
    assert markdown_safe(GREEK_DOCS["delta"].measures) in captions


# ------------------------------------------------------------------ presets


def test_switching_preset_rebuilds_legs_and_premium(at: AppTest) -> None:
    run(at.button(key=sb.preset_button_key("straddle")).click())
    straddle = engine_legs("straddle")
    assert legs(at) == straddle
    assert [(leg.type, leg.K) for leg in straddle] == [("call", 6300.0), ("put", 6300.0)]
    assert_readout_is_engine(at, straddle, SEED)
    assert preset_label(at, "straddle") == ":primary[**Straddle**]"
    assert preset_label(at, "butterfly") == "Butterfly"
    md = markdowns(at)
    assert ":gray-badge[2 legs]" in md
    assert ":gray-badge[Straddle]" in md
    assert any(markdown_safe(STRATEGY_DOCS["straddle"].view) in m for m in md)
    # the old legs' widgets are gone, the new ones show the new strikes
    with pytest.raises(KeyError):
        at.number_input(key=sb.leg_widget_key("butterfly-0", "K"))
    assert at.number_input(key=sb.leg_widget_key("straddle-1", "K")).value == 6300.0


def test_a_credit_structure_shows_a_plus_and_the_credit_badge(at: AppTest) -> None:
    run(at.button(key=sb.preset_button_key("iron-condor")).click())
    condor = engine_legs("iron-condor")
    price = analyze_position(condor, SEED).price
    assert price < 0
    assert premium(at) == f":green[+{fmt_money(-price)}]"
    assert ":gray-badge[CREDIT]" in markdowns(at)
    assert_readout_is_engine(at, condor, SEED)


def test_tenor_and_wing_apply_on_the_next_preset_pick(at: AppTest) -> None:
    run(at.number_input(key=sb.TENOR_KEY).set_value(60))
    run(at.number_input(key=sb.WING_KEY).set_value(10))
    assert legs(at) == engine_legs("butterfly")  # React: nothing rebuilds until a pick
    run(at.slider(key=f"{sb.S_KEY}__slider").set_value(6000.0))
    run(at.button(key=sb.preset_button_key("call-vertical")).click())
    spread = engine_legs("call-vertical", spot=6000.0, days=60, wing=0.10)
    assert legs(at) == spread
    assert [leg.K for leg in spread] == [6000.0, 6600.0]
    assert all(leg.T == 60 / 365 for leg in spread)
    assert_readout_is_engine(at, spread, dataclasses.replace(SEED, S=6000.0))


# ------------------------------------------------------------------ editing legs


def test_editing_a_leg_updates_greeks_and_turns_custom(at: AppTest) -> None:
    run(at.number_input(key=sb.leg_widget_key("butterfly-1", "K")).set_value(6325.0))
    base = engine_legs("butterfly")
    edited = (base[0], dataclasses.replace(base[1], K=6325.0), base[2])
    assert legs(at) == edited  # only the strike changed: the vols keep full precision
    assert_readout_is_engine(at, edited, SEED)
    md = markdowns(at)
    assert ":gray-badge[custom]" in md
    assert ":gray-badge[Custom structure]" in md
    assert any(markdown_safe(CUSTOM_STRUCTURE_NOTE) in m for m in md)
    assert all(preset_label(at, p.name) == p.label for p in PRESETS)


def test_each_field_converts_units_like_the_react_table(at: AppTest) -> None:
    run(at.number_input(key=sb.leg_widget_key("butterfly-0", "vol")).set_value(20.0))
    run(at.number_input(key=sb.leg_widget_key("butterfly-0", "days")).set_value(45))
    run(at.number_input(key=sb.leg_widget_key("butterfly-0", "quantity")).set_value(3))
    leg = legs(at)[0]
    assert (leg.sigma, leg.T, leg.quantity) == (0.2, 45 / 365, 3)
    assert at.number_input(key=sb.leg_widget_key("butterfly-0", "vol")).value == 20.0
    assert_readout_is_engine(at, legs(at), SEED)


def test_side_and_type_toggles(at: AppTest) -> None:
    run(at.button(key=sb.leg_widget_key("butterfly-1", "side")).click())
    run(at.button(key=sb.leg_widget_key("butterfly-2", "type")).click())
    body, wing = legs(at)[1], legs(at)[2]
    assert (body.side, wing.type) == ("long", "put")
    assert at.button(key=sb.leg_widget_key("butterfly-1", "side")).label == ":green[**L**]"
    assert at.button(key=sb.leg_widget_key("butterfly-2", "type")).label == ":orange[**P**]"
    assert_readout_is_engine(at, legs(at), SEED)


def test_clicking_the_active_preset_rebuilds_it(at: AppTest) -> None:
    run(at.number_input(key=sb.leg_widget_key("butterfly-1", "K")).set_value(6400.0))
    assert legs(at) != engine_legs("butterfly")
    run(at.button(key=sb.preset_button_key("butterfly")).click())
    assert legs(at) == engine_legs("butterfly")
    assert at.number_input(key=sb.leg_widget_key("butterfly-1", "K")).value == 6300.0
    assert premium(at) == f"{MINUS}146.39"


# ------------------------------------------------------------------ add / remove


def test_add_leg_appends_a_long_atm_call_from_the_surface(at: AppTest) -> None:
    run(at.button(key=sb.ADD_LEG_KEY).click())
    added = legs(at)[-1]
    assert added == Leg(
        id="custom-0",
        type="call",
        side="long",
        quantity=1,
        K=6300.0,
        T=30 / 365,
        sigma=SURFACE.get_vol(6300.0, 30 / 365),
    )
    assert len(legs(at)) == 4
    assert ":gray-badge[4 legs]" in markdowns(at)
    assert_readout_is_engine(at, legs(at), SEED)
    run(at.button(key=sb.ADD_LEG_KEY).click())
    assert legs(at)[-1].id == "custom-1"


def test_remove_legs_down_to_an_empty_position(at: AppTest) -> None:
    run(at.button(key=sb.leg_widget_key("butterfly-0", "remove")).click())
    assert [leg.id for leg in legs(at)] == ["butterfly-1", "butterfly-2"]
    assert_readout_is_engine(at, legs(at), SEED)
    assert ":gray-badge[2 legs]" in markdowns(at)
    for leg_id in ("butterfly-1", "butterfly-2"):
        run(at.button(key=sb.leg_widget_key(leg_id, "remove")).click())
    assert legs(at) == ()
    assert markdown_safe(EMPTY_LEGS_HINT) in [c.value for c in at.caption]
    assert premium(at) == f"{MINUS}0.00"  # React: a zero premium counts as a debit
    assert all(v == 0 for v in readout(at).values())
    # every chart axis still works with no legs
    for axis in ("vol", "time", "S"):
        run(at.button_group(key=sb.X_KEY).set_value(axis))


# ------------------------------------------------------------------ market, selection, reset


def test_market_sliders_revalue_the_position(at: AppTest) -> None:
    run(at.slider(key=f"{sb.S_KEY}__slider").set_value(6400.0))
    run(at.slider(key=f"{sb.R_KEY}__slider").set_value(0.05))
    run(at.slider(key=f"{sb.Q_KEY}__slider").set_value(0.02))
    m = MarketParams(S=6400.0, r=0.05, q=0.02)
    assert legs(at) == engine_legs("butterfly")  # moving the market never rebuilds legs
    assert_readout_is_engine(at, legs(at), m)
    assert "`6,400 USD`" in markdowns(at)
    assert "`5.00%`" in markdowns(at)


def test_greek_and_axis_pickers_drive_the_profile(at: AppTest) -> None:
    run(at.button_group(key=sb.GREEK_KEY).set_value("gamma"))
    md = markdowns(at)
    assert ":gray[:material/timeline:] **Net Gamma** :gray[vs] :primary[spot]" in md
    assert markdown_safe(GREEK_DOCS["gamma"].measures) in [c.value for c in at.caption]
    assert any(m.startswith("##### Gamma") for m in md)  # the greek card follows
    run(at.button_group(key=sb.X_KEY).set_value("vol"))
    assert ":gray[:material/timeline:] **Net Gamma** :gray[vs] :primary[vol shift]" in (
        markdowns(at)
    )
    run(at.button_group(key=sb.X_KEY).set_value("time"))
    assert ":gray[:material/timeline:] **Net Gamma** :gray[vs] :primary[time elapsed]" in (
        markdowns(at)
    )


def test_reset_restores_the_seed_market_and_butterfly(at: AppTest) -> None:
    run(at.button_group(key=sb.GREEK_KEY).set_value("vega"))
    run(at.slider(key=f"{sb.S_KEY}__slider").set_value(5800.0))
    run(at.number_input(key=sb.TENOR_KEY).set_value(90))
    run(at.number_input(key=sb.WING_KEY).set_value(8))
    run(at.button(key=sb.preset_button_key("iron-condor")).click())
    run(at.button(key=sb.ADD_LEG_KEY).click())
    run(at.button(key=sb.RESET_KEY).click())
    assert at.session_state[sb.S_KEY] == SNAP.spot
    assert at.slider(key=f"{sb.S_KEY}__slider").value == SNAP.spot
    assert at.number_input(key=sb.TENOR_KEY).value == 30
    assert at.number_input(key=sb.WING_KEY).value == 5
    assert legs(at) == engine_legs("butterfly")
    assert premium(at) == f"{MINUS}146.39"
    assert preset_label(at, "butterfly") == ":primary[**Butterfly**]"
    assert at.button_group(key=sb.GREEK_KEY).value == "vega"  # React keeps the selection


def test_position_survives_a_page_switch(at: AppTest) -> None:
    run(at.button(key=sb.preset_button_key("calendar")).click())
    run(at.number_input(key=sb.leg_widget_key("calendar-1", "vol")).set_value(18.0))
    edited = legs(at)
    at.switch_page("app_pages/home.py")
    run(at)
    at.switch_page(PAGE)
    run(at)
    assert legs(at) == edited
    assert at.number_input(key=sb.leg_widget_key("calendar-1", "vol")).value == 18.0
    assert_readout_is_engine(at, edited, SEED)
