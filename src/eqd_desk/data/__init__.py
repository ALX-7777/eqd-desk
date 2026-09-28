"""Seed market data: underlying presets, the validated snapshot, the implied-vol surface and
the historical replay series.

The committed JSON files (``snapshot.json``, ``history.json``) ship inside this package and
are read lazily (on first use, then cached), so importing is cheap and the app needs no
network access. All fetching lives in ``scripts/`` and stays out of the reactive loop::

    from eqd_desk.data import default_surface, load_snapshot, seed_inputs

    snap = load_snapshot()
    inputs = seed_inputs(snap)  # ATM-ish 30-day option
    default_surface().get_vol(0.95 * snap.spot, 0.25)  # 95% strike, 3 months
"""

from __future__ import annotations

from eqd_desk.data.config import (
    DEFAULT_UNDERLYING,
    UNDERLYING_KEYS,
    UNDERLYINGS,
    UnderlyingConfig,
    UnderlyingKey,
)
from eqd_desk.data.history import (
    History,
    HistoryMeta,
    HistoryPoint,
    load_history,
    parse_history,
    read_history_json,
)
from eqd_desk.data.snapshot import (
    SEED_T,
    MarketSnapshot,
    SkewParams,
    SnapshotTickers,
    TermPoint,
    load_snapshot,
    read_snapshot_json,
    seed_inputs,
    validate_snapshot,
)
from eqd_desk.data.vol_surface import (
    T_MIN,
    VOL_FLOOR,
    SnapshotVolSurface,
    VolSurface,
    build_surface,
    default_surface,
)

__all__ = [
    "DEFAULT_UNDERLYING",
    "SEED_T",
    "T_MIN",
    "UNDERLYINGS",
    "UNDERLYING_KEYS",
    "VOL_FLOOR",
    "History",
    "HistoryMeta",
    "HistoryPoint",
    "MarketSnapshot",
    "SkewParams",
    "SnapshotTickers",
    "SnapshotVolSurface",
    "TermPoint",
    "UnderlyingConfig",
    "UnderlyingKey",
    "VolSurface",
    "build_surface",
    "default_surface",
    "load_history",
    "load_snapshot",
    "parse_history",
    "read_history_json",
    "read_snapshot_json",
    "seed_inputs",
    "validate_snapshot",
]
