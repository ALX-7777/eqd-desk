"""Offline checks of the data-refresh scripts (``scripts/fetch_*.py``).

Nothing here touches the network: the fetchers are replaced by fakes, and yfinance is never
imported. Skipped where ``scripts/`` is absent (e.g. inside the Docker image).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from eqd_desk.data import UNDERLYINGS, parse_history, validate_snapshot

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str) -> ModuleType:
    path = SCRIPTS / f"{name}.py"
    if not path.is_file():
        pytest.skip(f"{path} not present")
    spec = importlib.util.spec_from_file_location(f"_eqd_script_{name}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fetch_snapshot() -> ModuleType:
    return _load("fetch_snapshot")


@pytest.fixture(scope="module")
def fetch_history() -> ModuleType:
    return _load("fetch_history")


FAKE_SNAPSHOT: dict[str, Any] = {
    "asof": "2026-01-02",
    "underlying": "spx",
    "name": "S&P 500",
    "currency": "USD",
    "spot": 6000.0,
    "r": 0.04,
    "q": 0.013,
    "realized_vol": None,
    "atm_vol_30d": 0.18,
    "skew": {"slope": -0.4, "curv": 0.6, "atm": 0.18},
    "term_structure": [],
    "source_notes": ["fake — offline test"],
    "tickers": {"index_ticker": "^GSPC", "vol_ticker": "^VIX", "options_proxy": "SPY"},
}


def test_script_presets_agree_with_the_package_config(fetch_snapshot: ModuleType) -> None:
    for key, cfg in UNDERLYINGS.items():
        preset = fetch_snapshot.CONFIGS[key]
        assert preset["name"] == cfg.name
        assert preset["index_ticker"] == cfg.index_ticker
        assert preset["vol_ticker"] == cfg.vol_index_ticker
        assert preset["options_proxy"] == cfg.options_proxy
        assert preset["currency"] == cfg.currency
        assert preset["default_div_yield"] == cfg.default_div_yield
    assert set(fetch_snapshot.CONFIGS) == set(UNDERLYINGS)


def test_default_paths_point_at_both_apps(
    fetch_snapshot: ModuleType, fetch_history: ModuleType
) -> None:
    root = SCRIPTS.parent
    for module, name in ((fetch_snapshot, "snapshot.json"), (fetch_history, "history.json")):
        assert root / "src" / "eqd_desk" / "data" / name == module.DEFAULT_OUT
        assert root / "web" / "src" / "data" / name == module.DEFAULT_MIRROR


def test_nearest_expiry_targets_30_days(fetch_snapshot: ModuleType) -> None:
    today = dt.date(2026, 1, 2)
    expiries = ["2026-01-02", "2026-01-09", "2026-01-30", "2026-02-06", "junk", "2026-03-20"]
    assert fetch_snapshot._nearest_expiry(expiries, today=today) == "2026-01-30"  # 28 days
    assert fetch_snapshot._nearest_expiry(expiries, 0, today=today) == "2026-01-02"
    assert fetch_snapshot._nearest_expiry(["junk"], today=today) is None


def test_snapshot_main_writes_output_and_mirror(
    fetch_snapshot: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch_snapshot, "build_snapshot", lambda underlying: FAKE_SNAPSHOT)
    out, mirror = tmp_path / "pkg" / "snapshot.json", tmp_path / "snapshot.json"
    fetch_snapshot.main(["--out", str(out), "--mirror", str(mirror)])
    assert out.read_bytes() == mirror.read_bytes()
    assert b"\r\n" not in out.read_bytes()  # LF line endings on every platform
    assert out.read_bytes().endswith(b"}\n")  # one final newline (pre-commit's end-of-file-fixer)
    assert json.loads(out.read_text("utf-8")) == FAKE_SNAPSHOT
    validate_snapshot(json.loads(out.read_text("utf-8")))  # the app accepts what it writes


def test_snapshot_mirror_can_be_disabled_and_is_skipped_without_its_directory(
    fetch_snapshot: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch_snapshot, "build_snapshot", lambda underlying: FAKE_SNAPSHOT)
    out = tmp_path / "snapshot.json"
    fetch_snapshot.main(["--out", str(out), "--mirror", ""])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["snapshot.json"]
    missing_dir_mirror = tmp_path / "no-web" / "snapshot.json"
    fetch_snapshot.main(["--out", str(out), "--mirror", str(missing_dir_mirror)])
    assert not missing_dir_mirror.parent.exists()


def test_history_main_writes_output_and_mirror(
    fetch_history: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = dt.date(2020, 1, 6)
    rows = [
        {"date": (start + dt.timedelta(days=i)).isoformat(), "spot": 3000.0 + i, "vix": 15.0}
        for i in range(fetch_history.MIN_POINTS)
    ]
    monkeypatch.setattr(fetch_history, "fetch_series", lambda years: rows)
    out, mirror = tmp_path / "history.json", tmp_path / "web" / "history.json"
    mirror.parent.mkdir()
    fetch_history.main(["--out", str(out), "--mirror", str(mirror)])
    assert out.read_bytes() == mirror.read_bytes()
    assert out.read_bytes().endswith(b"}\n")  # one final newline (pre-commit's end-of-file-fixer)
    h = parse_history(json.loads(out.read_text("utf-8")))
    assert h.meta.count == fetch_history.MIN_POINTS
    assert h.series[0].date == "2020-01-06"


def test_history_refuses_a_short_series(
    fetch_history: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch_history, "fetch_series", lambda years: [])
    out = tmp_path / "history.json"
    with pytest.raises(SystemExit, match="too few aligned days"):
        fetch_history.main(["--out", str(out), "--mirror", ""])
    assert not out.exists()


@pytest.mark.parametrize("name", ["fetch_snapshot", "fetch_history"])
def test_help_works_without_yfinance(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "yfinance", None)  # make `import yfinance` fail
    module = _load(name)
    with pytest.raises(SystemExit) as exit_info:
        module.main(["--help"])
    assert exit_info.value.code == 0
    assert "--mirror" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="yfinance is required"):
        module._yf()


@pytest.fixture
def redirected_defaults(
    fetch_snapshot: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Point the snapshot script's default --out / --mirror into ``tmp_path`` (never at the
    real repo copies) and stub the network fetch."""
    out = tmp_path / "src" / "eqd_desk" / "data" / "snapshot.json"
    mirror = tmp_path / "web" / "src" / "data" / "snapshot.json"
    mirror.parent.mkdir(parents=True)
    monkeypatch.setattr(fetch_snapshot, "DEFAULT_OUT", out)
    monkeypatch.setattr(fetch_snapshot, "DEFAULT_MIRROR", mirror)
    monkeypatch.setattr(fetch_snapshot, "build_snapshot", lambda underlying: FAKE_SNAPSHOT)
    return out, mirror


def test_default_run_writes_both_committed_copies(
    fetch_snapshot: ModuleType, redirected_defaults: tuple[Path, Path]
) -> None:
    out, mirror = redirected_defaults
    fetch_snapshot.main([])
    assert out.read_bytes() == mirror.read_bytes()


def test_a_custom_out_does_not_refresh_the_react_copy_alone(
    fetch_snapshot: ModuleType,
    redirected_defaults: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The pre-Python refresh command (``--out src/data/snapshot.json``) used to mirror into
    web/ while leaving the package copy stale; a custom --out now writes only itself."""
    _, mirror = redirected_defaults
    legacy_out = tmp_path / "src" / "data" / "snapshot.json"
    fetch_snapshot.main(["--underlying", "spx", "--out", str(legacy_out)])
    assert json.loads(legacy_out.read_text("utf-8")) == FAKE_SNAPSHOT
    assert not mirror.exists()
    assert "not mirrored" in capsys.readouterr().out
    # ... unless a mirror is asked for explicitly
    fetch_snapshot.main(["--out", str(legacy_out), "--mirror", str(mirror)])
    assert mirror.read_bytes() == legacy_out.read_bytes()


@pytest.mark.parametrize("name", ["fetch_snapshot", "fetch_history"])
def test_resolve_mirror(name: str, tmp_path: Path) -> None:
    module = _load(name)
    default_out, default_mirror = module.DEFAULT_OUT, module.DEFAULT_MIRROR
    assert module.resolve_mirror(default_out, None) == default_mirror
    assert module.resolve_mirror(tmp_path / "x.json", None) is None
    assert module.resolve_mirror(default_out, "") is None
    assert module.resolve_mirror(tmp_path / "x.json", str(tmp_path / "m.json")) == (
        tmp_path / "m.json"
    )
