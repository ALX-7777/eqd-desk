"""Historical replay series: the committed real ^GSPC + ^VIX history and its parser."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from itertools import pairwise
from typing import Any

import pytest

from eqd_desk.data import History, HistoryPoint, load_history, parse_history, read_history_json
from eqd_desk.engine import sim
from eqd_desk.engine.sim import pick_window, window_steps

HISTORY = load_history()


def test_loads_the_committed_series() -> None:
    series, meta = HISTORY.series, HISTORY.meta
    assert meta.count == len(series) == 2010
    assert meta.count == read_history_json()["count"]
    assert meta.asof == "2026-06-25"
    assert "^GSPC" in meta.source
    assert "^VIX" in meta.source
    assert series[0] == HistoryPoint(date="2018-06-25", spot=2717.07, vix=17.33)
    assert series[-1] == HistoryPoint(date="2026-06-24", spot=7358.22, vix=18.63)


def test_series_is_sane_real_market_data() -> None:
    """Oldest first, one point per distinct trading day, positive spot, VIX in (1, 200)."""
    dates = [dt.date.fromisoformat(p.date) for p in HISTORY.series]
    assert all(a < b for a, b in pairwise(dates))
    assert all(d.weekday() < 5 for d in dates)  # trading days only
    assert all(p.spot > 0 for p in HISTORY.series)
    assert all(1.0 < p.vix < 200.0 for p in HISTORY.series)
    # the COVID crash is in there: VIX closed above 80 in March 2020
    assert max(p.vix for p in HISTORY.series) > 80


def test_loader_is_cached_and_the_result_immutable_and_hashable() -> None:
    assert load_history() is load_history()
    assert isinstance(HISTORY.series, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        HISTORY.series[0].spot = 1.0  # type: ignore[misc]
    assert hash(HISTORY) == hash(parse_history(read_history_json()))


def test_history_point_is_the_engine_type() -> None:
    """One type, as in TS (``data/history.ts`` imports ``HistoryPoint`` from the engine)."""
    assert HistoryPoint is sim.HistoryPoint
    assert type(HISTORY.series[0]) is sim.HistoryPoint


def test_series_feeds_the_replay_engine() -> None:
    """The SimulatorView call ``pickWindow(historySeries, …)``. Also a static check: mypy
    rejects this line if the data layer and the engine disagree on ``HistoryPoint``."""
    window = pick_window(load_history().series, 10, 0.5)
    assert window_steps(window) == 10
    assert window.points == HISTORY.series[window.start_index : window.start_index + 11]
    assert all(isinstance(p, sim.HistoryPoint) for p in window.points)


def test_missing_fields_default_to_empty() -> None:
    h = parse_history({})
    assert h == parse_history({"series": "not a list", "asof": None})
    assert h.series == ()
    assert (h.meta.asof, h.meta.source, h.meta.count) == ("", "", 0)


def test_count_is_the_parsed_length_not_the_file_field() -> None:
    raw: dict[str, Any] = {
        "asof": "2026-01-02",
        "source": "test",
        "count": 99,
        "series": [{"date": "2026-01-02", "spot": 5000, "vix": 15}],
    }
    h = parse_history(raw)
    assert h.meta.count == 1
    assert h == History(
        series=(HistoryPoint("2026-01-02", 5000.0, 15.0),),
        meta=h.meta,
    )
    assert isinstance(h.series[0].spot, float)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (None, "history: not an object"),
        ([1, 2], "history: not an object"),
        ({"series": [1]}, r"series\[0\] is not an object"),
        ({"series": [{"date": "d", "spot": "1", "vix": 15}]}, r"series\[0\]\.spot"),
        ({"series": [{"date": "d", "spot": 1, "vix": True}]}, r"series\[0\]\.vix"),
        ({"series": [{"date": "d", "spot": 1}]}, r"series\[0\]\.vix"),
        ({"series": [{"spot": 1, "vix": 15}]}, r"series\[0\]\.date"),
        ({"series": [{"date": 20260102, "spot": 1, "vix": 15}]}, r"series\[0\]\.date"),
        # an integer literal too big for a double: ValueError, not OverflowError
        ({"series": [{"date": "d", "spot": 10**400, "vix": 15}]}, r"series\[0\]\.spot.*inf"),
        ({"series": [{"date": "d", "spot": 1, "vix": -(10**400)}]}, r"series\[0\]\.vix"),
        ({"series": [{"date": "d", "spot": 1, "vix": float("nan")}]}, r"series\[0\]\.vix"),
    ],
)
def test_malformed_history_is_rejected(raw: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_history(raw)


def test_huge_integer_from_json_text_is_rejected_cleanly() -> None:
    text = '{"series": [{"date": "d", "spot": 1' + "0" * 400 + ', "vix": 15}]}'
    with pytest.raises(ValueError, match=r"series\[0\]\.spot"):
        parse_history(json.loads(text))
