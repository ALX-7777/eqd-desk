"""Historical replay data loader.

Wraps the committed ``history.json`` (real daily ^GSPC + ^VIX from
``scripts/fetch_history.py``) as a typed series the simulator can replay. Data only: kept
out of the reactive loop.

:class:`HistoryPoint` is the ENGINE's type (``eqd_desk.engine.sim.replay``), re-exported
here, exactly as the TS ``data/history.ts`` imports it from ``../engine``: the data layer
depends on the engine, never the reverse, so :func:`load_history`'s series can be passed
straight to :func:`eqd_desk.engine.sim.pick_window` and type-checks.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any, Final

from eqd_desk.engine.sim.replay import HistoryPoint

__all__ = [
    "HISTORY_RESOURCE",
    "History",
    "HistoryMeta",
    "HistoryPoint",
    "load_history",
    "parse_history",
    "read_history_json",
]

HISTORY_RESOURCE: Final = "history.json"
"""File name of the committed replay series inside the ``eqd_desk.data`` package."""


@dataclass(frozen=True, slots=True)
class HistoryMeta:
    """Provenance of the replay series."""

    asof: str
    """ISO date the file was generated."""
    source: str
    """Human-readable data source."""
    count: int
    """Number of points in the series (counted, not trusted from the file)."""


@dataclass(frozen=True, slots=True)
class History:
    """The replay series plus its metadata. Frozen (the series is a tuple), so hashable."""

    series: tuple[HistoryPoint, ...]
    """Daily points, oldest first."""
    meta: HistoryMeta
    """Where the series came from."""


def _num(v: object, path: str) -> float:
    """Return ``v`` as a float if it is a finite number (booleans rejected), else raise.

    An integer too large for a double (``json`` keeps integers exact) counts as infinite,
    as ``JSON.parse`` would read it, and is rejected with ValueError, not OverflowError.
    """
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise ValueError(f'history: expected finite number at "{path}", got {v!r}')
    try:
        x = float(v)
    except OverflowError:
        x = math.inf
    if not math.isfinite(x):
        raise ValueError(f'history: expected finite number at "{path}", got {x!r}')
    return x


def _point(p: object, i: int) -> HistoryPoint:
    """Narrow one ``{"date", "spot", "vix"}`` entry of the series to a :class:`HistoryPoint`."""
    if not isinstance(p, Mapping):
        raise ValueError(f"history: series[{i}] is not an object")
    date = p.get("date")
    if not isinstance(date, str):
        raise ValueError(f'history: expected a date string at "series[{i}].date", got {date!r}')
    return HistoryPoint(
        date=date,
        spot=_num(p.get("spot"), f"series[{i}].spot"),
        vix=_num(p.get("vix"), f"series[{i}].vix"),
    )


def parse_history(raw: object) -> History:
    """Narrow parsed ``history.json`` to a typed :class:`History`.

    A missing or non-list ``series`` gives an empty series; missing ``asof`` / ``source``
    give empty strings; ``meta.count`` is the length of the parsed series.

    Raises:
        ValueError: if ``raw`` is not a JSON object, or a point is not an object with a
            string ``date`` and finite numeric ``spot`` and ``vix``.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("history: not an object")
    series_raw = raw.get("series")
    items = series_raw if isinstance(series_raw, list | tuple) else []
    series = tuple(_point(p, i) for i, p in enumerate(items))
    asof, source = raw.get("asof"), raw.get("source")
    return History(
        series=series,
        meta=HistoryMeta(
            asof="" if asof is None else str(asof),
            source="" if source is None else str(source),
            count=len(series),
        ),
    )


def read_history_json() -> Any:
    """Parse the committed ``history.json`` shipped inside the package (unvalidated)."""
    text = resources.files("eqd_desk.data").joinpath(HISTORY_RESOURCE).read_text("utf-8")
    return json.loads(text)


@cache
def load_history() -> History:
    """The committed replay series, parsed once on first call and cached (immutable)."""
    return parse_history(read_history_json())
