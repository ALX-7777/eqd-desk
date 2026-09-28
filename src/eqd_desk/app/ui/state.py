"""Session state and shared market data for the pages.

Two kinds of state, two mechanisms:

- **Shared, read-only market data** (the seed snapshot, its vol surface, the replay
  history) is loaded once per PROCESS and shared by every session: the data layer caches it
  with ``functools.cache`` and the objects are frozen dataclasses, so the accessors below
  simply delegate (equivalent to ``st.cache_resource`` without copying on every rerun).
- **Per-user state** lives in ``st.session_state`` under PAGE-PREFIXED keys (``"lab.S"``,
  ``"sim.book"``). Each page initialises its own keys with :func:`ensure_state` at the top
  of its script, so it works however it is reached: via the navigation, a deep link, or on
  its own in an ``AppTest``. Initialisation is idempotent (``setdefault``): it never
  overwrites what the user has done.

Keys that are not widget keys survive page switches, so a page keeps its state when the user
navigates away and back (the React simulator stays mounted for the same reason).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Final, cast

import streamlit as st

from eqd_desk.data import (
    DEFAULT_UNDERLYING,
    UNDERLYINGS,
    History,
    MarketSnapshot,
    SnapshotVolSurface,
    UnderlyingConfig,
    default_surface,
    load_history,
    load_snapshot,
)

APP_READY_KEY: Final = "app.ready"
"""Set by :func:`init_app_state` once the shared data has been loaded in this session."""

# ------------------------------------------------------------------ shared market data


def snapshot() -> MarketSnapshot:
    """The validated seed market snapshot (spot, r, q, ATM vol, skew, term structure)."""
    return load_snapshot()


def surface() -> SnapshotVolSurface:
    """The seed implied-vol surface built from the snapshot (``get_vol(K, T)``)."""
    return default_surface()


def history() -> History:
    """The real daily ^GSPC / ^VIX series used by the simulator's historical replay."""
    return load_history()


def underlying(snap: MarketSnapshot | None = None) -> UnderlyingConfig:
    """The underlying preset of the snapshot (tickers, currency), falling back to the
    default (S&P 500) for an unknown key, like the React header."""
    key = (snap or snapshot()).underlying
    for k, cfg in UNDERLYINGS.items():
        if k == key:
            return cfg
    return UNDERLYINGS[DEFAULT_UNDERLYING]


def strike_step(spot: float | None = None) -> float:
    """Listed-strike grid of the index, in index points: 25 for an index above 2,000
    (SPX, SX5E), else 5 — the React exotics' and simulator's ``STRIKE_STEP``."""
    s = snapshot().spot if spot is None else spot
    return 25.0 if s >= 2000 else 5.0


def level_step(spot: float | None = None) -> float:
    """Slider increment for spot / strike inputs: 1 point above 2,000, 0.5 above 200, else
    0.1 — the greeks lab's ``stepFor(spot)``."""
    s = snapshot().spot if spot is None else spot
    if s >= 2000:
        return 1.0
    if s >= 200:
        return 0.5
    return 0.1


# ------------------------------------------------------------------ session state


def ensure_state(defaults: Mapping[str, object]) -> None:
    """Idempotently seed session-state keys (``setdefault``): existing values are kept.

    Call at the top of a page with that page's prefixed keys, e.g.
    ``ensure_state({"lab.type": "call", "lab.greek": "delta"})``. For values that are
    expensive to build, pass them lazily with :func:`ensure_lazy`.
    """
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def ensure_lazy[T](key: str, factory: Callable[[], T]) -> T:
    """Seed ``key`` with ``factory()`` only if it is missing (the factory is not called
    otherwise); return the stored value."""
    if key not in st.session_state:
        st.session_state[key] = factory()
    return cast("T", st.session_state[key])


def reset_state(values: Mapping[str, object]) -> None:
    """Overwrite keys (e.g. a "Reset" button's ``on_click``). Widget keys may only be
    assigned before their widget renders in a run, so call this from a callback."""
    for key, value in values.items():
        st.session_state[key] = value


def clear_state(prefix: str, *, keep: Iterable[str] = ()) -> None:
    """Delete every session key starting with ``prefix`` (``"lab."``) except ``keep``;
    the page's :func:`ensure_state` then re-seeds its defaults on the next run."""
    kept = set(keep)
    for key in [k for k in st.session_state if str(k).startswith(prefix)]:
        if key not in kept:
            del st.session_state[key]


def init_app_state() -> None:
    """App-wide, idempotent initialisation run by the entrypoint before every page: loads
    (and so caches) the shared market data once, then marks the session ready."""
    if st.session_state.get(APP_READY_KEY):
        return
    snapshot()
    surface()
    history()
    st.session_state[APP_READY_KEY] = True
