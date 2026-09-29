"""Behaviour of the shared widgets and education renderers inside a running script
(``AppTest.from_function``): values shown equal the engine's, controls stay in sync."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from eqd_desk.app.ui.education import field_markdown
from eqd_desk.app.ui.widgets import slider_keys
from eqd_desk.content import (
    ATTRIBUTION_TERMS,
    EXOTIC_DOCS,
    GREEK_DOCS,
    KEY_RELATIONSHIPS,
    SIM_CONCEPTS,
    STRATEGY_DOCS,
    markdown_safe,
)
from eqd_desk.content.exotics import EXOTIC_DOC_FIELD_LABELS
from eqd_desk.content.greeks import GREEK_DOC_FIELD_LABELS, GREEK_GROUPS
from eqd_desk.content.strategies import CUSTOM_STRUCTURE_NOTE, STRATEGY_DOC_FIELD_LABELS
from eqd_desk.engine import GREEK_UNITS, BsmInputs, analyze_option

from .conftest import DEFAULT_TIMEOUT, field_wkey, slider_wkey, wkey

pytestmark = pytest.mark.app


def value_line(at: AppTest) -> str:
    """The ``value=…`` markdown the test scripts print."""
    return next(m.value for m in at.markdown if m.value.startswith("value="))


# ------------------------------------------------------------------ number_slider


def slider_script() -> None:
    import streamlit as st

    from eqd_desk.app.ui.widgets import number_slider, set_number

    st.button("Reset", on_click=set_number, args=("t.S", 42.0))
    if st.checkbox("Show", value=True):
        v = number_slider(
            "Spot",
            key="t.S",
            min_value=0.0,
            max_value=200.0,
            step=0.5,
            default=100.0,
            symbol="S",
            display=lambda x: f"{x:.2f} USD",
        )
        st.markdown(f"value={v}")
    n = number_slider(
        "Observations", key="t.n", min_value=1, max_value=24, step=1, default=6, integer=True
    )
    st.markdown(f"obs={n!r}")
    number_slider("Wing", key="t.w", min_value=0.0, max_value=1.0, step=0.01, compact=True)


def run_slider_app() -> AppTest:
    at = AppTest.from_function(slider_script, default_timeout=DEFAULT_TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    return at


def test_number_slider_starts_at_default_with_both_widgets() -> None:
    at = run_slider_app()
    assert at.slider(key=slider_wkey(at, "t.S")).value == 100.0
    assert at.number_input(key=field_wkey(at, "t.S")).value == 100.0
    assert value_line(at) == "value=100.0"
    assert at.session_state["t.S"] == 100.0
    assert any(m.value == "`100.00 USD`" for m in at.markdown)  # the header display
    # compact: slider only, no numeric field
    assert at.slider(key=slider_wkey(at, "t.w")).value == 0.0
    with pytest.raises(KeyError):
        at.number_input(key=field_wkey(at, "t.w"))


def test_number_slider_widgets_are_created_at_the_current_value() -> None:
    """Remount safety: each widget's proto default IS the current value (a widget the
    frontend remounts restarts there, not at min_value), and the widget keys are derived
    keys, never the canonical one."""
    at = run_slider_app()
    at.slider(key=slider_wkey(at, "t.S")).set_value(120.5).run()
    slider = at.slider(key=slider_wkey(at, "t.S"))
    field = at.number_input(key=field_wkey(at, "t.S"))
    assert list(slider.proto.default) == [120.5]
    assert field.proto.default == 120.5
    assert slider.key == slider_wkey(at, "t.S")
    assert field.key == field_wkey(at, "t.S")
    assert str(slider.key).startswith(slider_keys("t.S")[0])  # never the canonical "t.S"
    assert str(field.key).startswith(slider_keys("t.S")[1])


def test_moving_the_slider_updates_the_field_and_the_value() -> None:
    at = run_slider_app()
    slider_before = slider_wkey(at, "t.S")
    at.slider(key=slider_before).set_value(120.5).run()
    assert at.number_input(key=field_wkey(at, "t.S")).value == 120.5
    assert slider_wkey(at, "t.S") == slider_before  # the widget in use is not remounted
    assert value_line(at) == "value=120.5"
    assert any(m.value == "`120.50 USD`" for m in at.markdown)


def test_typing_in_the_field_moves_the_slider() -> None:
    at = run_slider_app()
    field_before = field_wkey(at, "t.S")
    at.number_input(key=field_before).set_value(63.5).run()
    assert at.slider(key=slider_wkey(at, "t.S")).value == 63.5
    assert field_wkey(at, "t.S") == field_before
    assert value_line(at) == "value=63.5"


def test_set_number_from_a_callback_moves_both_widgets() -> None:
    at = run_slider_app()
    at.slider(key=slider_wkey(at, "t.S")).set_value(150.0).run()
    at.button[0].click().run()
    assert at.slider(key=slider_wkey(at, "t.S")).value == 42.0
    assert at.number_input(key=field_wkey(at, "t.S")).value == 42.0
    assert value_line(at) == "value=42.0"


def test_value_survives_the_widgets_being_unmounted() -> None:
    at = run_slider_app()
    at.slider(key=slider_wkey(at, "t.S")).set_value(77.0).run()
    at.checkbox[0].uncheck().run()  # widgets gone (like a page switch)
    assert not any(m.value.startswith("value=") for m in at.markdown)
    at.checkbox[0].check().run()
    assert at.slider(key=slider_wkey(at, "t.S")).value == 77.0
    assert value_line(at) == "value=77.0"


def test_integer_slider_returns_whole_numbers() -> None:
    at = run_slider_app()
    assert any(m.value == "obs=6" for m in at.markdown)
    at.number_input(key=field_wkey(at, "t.n")).set_value(9).run()
    assert at.slider(key=slider_wkey(at, "t.n")).value == 9
    assert any(m.value == "obs=9" for m in at.markdown)


# ------------------------------------------------------------------ choices


def choice_script() -> None:
    import streamlit as st

    from eqd_desk.app.ui.widgets import choice, greek_picker, option_type_toggle, toggle

    def reset() -> None:  # plain writes of the canonical keys, like a page's Reset
        st.session_state["t.type"] = "call"
        st.session_state["t.greek"] = "theta"
        st.session_state["t.on"] = False

    st.button("Reset", on_click=reset)
    t = option_type_toggle(key="t.type")
    x = choice("X axis", {"S": "Spot", "sigma": "Vol", "T": "Time"}, key="t.x", default="S")
    g = greek_picker(key="t.greek")
    on = toggle("Overlay", key="t.on", default=True)
    st.markdown(f"value={t}|{x}|{g}|{on}")


def run_choice_app() -> AppTest:
    at = AppTest.from_function(choice_script, default_timeout=DEFAULT_TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    return at


def test_choice_widgets_return_values_not_labels() -> None:
    at = run_choice_app()
    assert value_line(at) == "value=call|S|delta|True"
    at.button_group(key=wkey(at, "t.type")).set_value("put").run()
    at.button_group(key=wkey(at, "t.x")).set_value("sigma").run()
    at.button_group(key=wkey(at, "t.greek")).set_value("gamma").run()
    at.toggle(key=wkey(at, "t.on")).set_value(False).run()
    assert value_line(at) == "value=put|sigma|gamma|False"
    assert at.session_state["t.greek"] == "gamma"  # the canonical key holds the value
    # the chips show the greeks' display labels, price first
    chips = at.button_group(key=wkey(at, "t.greek"))
    assert list(chips.options) == [u.label for u in GREEK_UNITS.values()]


def test_choice_widgets_are_created_at_the_current_selection() -> None:
    at = run_choice_app()
    at.button_group(key=wkey(at, "t.greek")).set_value("vega").run()
    chips = at.button_group(key=wkey(at, "t.greek"))
    assert [chips.options[i] for i in chips.proto.default] == ["Vega"]
    assert chips.key != "t.greek"
    assert at.toggle(key=wkey(at, "t.on")).proto.default is True


def test_a_plain_write_of_the_canonical_key_moves_the_widget() -> None:
    at = run_choice_app()
    at.button_group(key=wkey(at, "t.type")).set_value("put").run()
    at.button_group(key=wkey(at, "t.greek")).set_value("gamma").run()
    at.button[0].click().run()  # the callback writes the canonical keys only
    assert value_line(at) == "value=call|S|theta|False"
    assert at.button_group(key=wkey(at, "t.type")).value == "call"
    assert at.button_group(key=wkey(at, "t.greek")).value == "theta"
    assert at.toggle(key=wkey(at, "t.on")).value is False


def number_script() -> None:
    import streamlit as st

    from eqd_desk.app.ui.inputs import steady_number

    st.session_state.setdefault("t.K", 6300.0)
    st.session_state.setdefault("t.size", 10)
    st.button("Reset", on_click=lambda: st.session_state.update({"t.K": 6000.0}))
    k = steady_number(
        "Strike",
        key="t.K",
        min_value=0.01,
        step=5.0,
        format="%g",
        width=136,
        label_visibility="collapsed",
    )
    n = steady_number("Size", key="t.size", min_value=1, max_value=50, step=1)
    st.markdown(f"value={k!r}|{n!r}")


def test_steady_number_float_and_int_fields() -> None:
    at = AppTest.from_function(number_script, default_timeout=DEFAULT_TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    assert value_line(at) == "value=6300.0|10"
    strike = at.number_input(key=wkey(at, "t.K"))
    assert strike.proto.default == 6300.0  # created at the current value
    assert strike.proto.format == "%g"
    strike.set_value(6325.0).run()
    at.number_input(key=wkey(at, "t.size")).set_value(12).run()
    assert value_line(at) == "value=6325.0|12"
    at.button[0].click().run()  # a plain write of the canonical key remounts the field
    assert at.number_input(key=wkey(at, "t.K")).value == 6000.0
    assert value_line(at) == "value=6000.0|12"


# ------------------------------------------------------------------ readouts


def readout_script() -> None:
    import streamlit as st

    from eqd_desk.app.ui.format import fmt_money
    from eqd_desk.app.ui.widgets import greek_readout, hero_number, section_header
    from eqd_desk.engine import BsmInputs, analyze_option

    a = analyze_option(BsmInputs(S=100, K=100, T=1, r=0.05, q=0.01, sigma=0.2), "call")
    slot = section_header("Price & greeks", badge="CALL")
    with slot:
        st.button("Inside the slot")
    hero_number("Premium (USD)", fmt_money(a.reported.price), detail="time value only")
    hero_number("P&L (USD)", "+17,959.06", tone="pos")
    greek_readout(a.reported, selected="vega")


def test_greek_readout_shows_the_engine_values() -> None:
    at = AppTest.from_function(readout_script, default_timeout=DEFAULT_TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    a = analyze_option(BsmInputs(S=100, K=100, T=1, r=0.05, q=0.01, sigma=0.2), "call")
    table = at.table[0].value
    groups = [g.title for g in GREEK_GROUPS]
    greeks = table[~table["label"].isin(groups)]
    keys = [k for g in GREEK_GROUPS for k in g.keys]
    assert list(greeks["label"]) == [GREEK_UNITS[k].label for k in keys]
    assert list(greeks["value"]) == [getattr(a.reported, k) for k in keys]
    assert list(table[table["label"].isin(groups)]["label"]) == groups

    premium, pnl = at.metric
    assert premium.label == "Premium (USD)"
    assert premium.value == f"{a.reported.price:,.2f}"
    assert premium.proto.delta_description == "time value only"
    assert pnl.value == ":green[+17,959.06]"
    assert any(m.value == "###### **Price & greeks**" for m in at.markdown)
    assert any("CALL" in m.value and "badge" in m.value for m in at.markdown)
    assert at.button[0].label == "Inside the slot"


# ------------------------------------------------------------------ education


def education_script() -> None:
    from eqd_desk.app.ui.education import (
        attribution_terms,
        exotic_doc_card,
        exotic_greek_card,
        greek_doc_card,
        key_relationships,
        learn_header,
        sim_concepts,
        strategy_doc_card,
    )

    learn_header(badge="per $1 spot")
    greek_doc_card("delta")
    key_relationships()
    strategy_doc_card("risk-reversal", title="Risk reversal")
    strategy_doc_card(None, title="Custom structure")
    exotic_doc_card("barrier")
    exotic_greek_card("gamma")
    sim_concepts()
    attribution_terms()


def test_education_renders_content_verbatim_and_escaped() -> None:
    at = AppTest.from_function(education_script, default_timeout=DEFAULT_TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    texts = [m.value for m in at.markdown]

    delta = GREEK_DOCS["delta"]
    assert any(t == f"##### {markdown_safe(delta.title)}" for t in texts)
    for g_field, g_label in GREEK_DOC_FIELD_LABELS.items():
        assert field_markdown(g_label, getattr(delta, g_field)) in texts
    # "$1" must reach st.markdown escaped, or Streamlit would typeset LaTeX
    assert any("\\$1 move in spot" in t for t in texts)
    assert not any("$" in t.replace("\\$", "") for t in texts)

    rr = STRATEGY_DOCS["risk-reversal"]
    for s_field, s_label in STRATEGY_DOC_FIELD_LABELS.items():
        assert field_markdown(s_label, getattr(rr, s_field)) in texts
    assert any(markdown_safe(CUSTOM_STRUCTURE_NOTE) in t for t in texts)
    assert "##### Custom structure" not in texts  # the custom note is untitled (React)

    barrier = EXOTIC_DOCS["barrier"]
    for e_field, e_label in EXOTIC_DOC_FIELD_LABELS.items():
        assert field_markdown(e_label, getattr(barrier, e_field)) in texts
    gamma = GREEK_DOCS["gamma"]
    assert field_markdown("Measures", gamma.measures) in texts
    assert field_markdown("On the desk", gamma.desk) not in texts  # short card

    expanders = [e.label for e in at.expander]
    assert expanders == [markdown_safe(r.title) for r in KEY_RELATIONSHIPS] + [
        markdown_safe(c.title) for c in SIM_CONCEPTS
    ]
    for term in ATTRIBUTION_TERMS:
        assert field_markdown(term.label, term.note) in texts


# ------------------------------------------------------------------ panel actions & help


def actions_script() -> None:
    import streamlit as st

    from eqd_desk.app.ui.widgets import (
        choice,
        number_slider,
        reset_button,
        surface_vol_button,
        toggle,
    )

    st.session_state.setdefault("t.K", 5000.0)
    st.session_state.setdefault("t.T", 0.25)
    number_slider("Vol", key="t.sigma", min_value=0.01, max_value=1.0, step=0.0025, default=0.2)
    kind = choice("Kind", {"a": "A", "b": "B"}, key="t.kind", default="a")
    on = toggle("Flag", key="t.flag", default=False, help="costs $1 per $1 spot")
    with st.container(horizontal=True):
        surface_vol_button("t.")
        reset_button({"t.sigma": 0.2, "t.kind": "a", "t.flag": False}, key="t.reset")
    st.markdown(f"value={st.session_state['t.sigma']}|{kind}|{on}")


def run_actions_app() -> AppTest:
    at = AppTest.from_function(actions_script, default_timeout=DEFAULT_TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    return at


def test_surface_vol_button_snaps_sigma_to_the_seed_surface() -> None:
    from eqd_desk.data import default_surface

    at = run_actions_app()
    at.button(key="t.surface").click().run()
    expected = default_surface().get_vol(5000.0, 0.25)
    assert at.session_state["t.sigma"] == pytest.approx(expected)
    assert at.slider(key=slider_wkey(at, "t.sigma")).value == pytest.approx(expected)


def test_reset_button_restores_sliders_choices_and_toggles() -> None:
    at = run_actions_app()
    at.slider(key=slider_wkey(at, "t.sigma")).set_value(0.5).run()
    at.button_group(key=wkey(at, "t.kind")).set_value("b").run()
    at.toggle(key=wkey(at, "t.flag")).set_value(True).run()
    assert value_line(at) == "value=0.5|b|True"
    at.button(key="t.reset").click().run()
    assert value_line(at) == "value=0.2|a|False"
    # every widget shows the restored value (they were remounted with it)
    assert at.slider(key=slider_wkey(at, "t.sigma")).value == 0.2
    assert at.number_input(key=field_wkey(at, "t.sigma")).value == 0.2
    assert at.button_group(key=wkey(at, "t.kind")).value == "a"
    assert at.toggle(key=wkey(at, "t.flag")).value is False


def test_widget_help_is_escaped_exactly_once() -> None:
    at = run_actions_app()
    # plain text in: "$" escaped once (no LaTeX between the two dollar signs), not twice
    assert at.toggle(key=wkey(at, "t.flag")).help == r"costs \$1 per \$1 spot"
