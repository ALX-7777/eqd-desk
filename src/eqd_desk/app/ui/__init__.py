"""The Streamlit UI layer: the building blocks shared by every page, then one small family of
modules per page.

Shared (pure unless marked *Streamlit*):

- :mod:`~eqd_desk.app.ui.theme` — the terminal palette (mirrors ``.streamlit/config.toml``).
- :mod:`~eqd_desk.app.ui.format` — number formatting, string-identical to the React app, and
  the slider-thumb formats.
- :mod:`~eqd_desk.app.ui.units` — the greeks' desk units in the snapshot currency, and the
  axis titles built from them.
- :mod:`~eqd_desk.app.ui.bounds` — input ranges and grids shared by the pages (r, q, T, the
  spot range, slider steps, the listed-strike grid).
- :mod:`~eqd_desk.app.ui.charts` — Altair builders with one consistent look.
- :mod:`~eqd_desk.app.ui.readout` — the label · value · unit readout table as data and
  styles.
- :mod:`~eqd_desk.app.ui.nav` — the product name and the page registry (titles, icons, URLs,
  browser-tab titles).
- :mod:`~eqd_desk.app.ui.inputs` — *Streamlit*: the remount-safe contract every input
  follows (canonical Session State keys, generation-suffixed widget keys).
- :mod:`~eqd_desk.app.ui.widgets` — *Streamlit*: header, section titles, paired sliders,
  choices, readouts, the "σ ← surface" and Reset actions.
- :mod:`~eqd_desk.app.ui.education` — *Streamlit*: the "Learn" panels, rendered from
  :mod:`eqd_desk.content`.
- :mod:`~eqd_desk.app.ui.state` — *Streamlit*: session-state helpers and the shared market
  data.

Per page (the page script lives in ``app_pages/``): ``greeks_lab_*`` (inputs, curves,
charts), ``strategy_builder_*`` and ``strategy_curves`` (legs, state, curves, charts),
``exotics_*`` (curves, charts, display; views), and the simulator's ``sim_session`` (the
desk state machine) with ``simulator_*`` (clock, controls, display, charts, panels). Their
pure halves (curves, charts, display text, the session) are unit-tested without Streamlit
(``tests/ui/test_purity.py`` keeps them free of it).
"""
