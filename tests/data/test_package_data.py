"""The seed JSON ships inside the package, and stays in sync with the React app's copy."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest

from eqd_desk.data.history import HISTORY_RESOURCE
from eqd_desk.data.snapshot import SNAPSHOT_RESOURCE

DATA_FILES = (SNAPSHOT_RESOURCE, HISTORY_RESOURCE)
PACKAGE_DATA = resources.files("eqd_desk.data")
WEB_DATA = Path(__file__).resolve().parents[2] / "web" / "src" / "data"


@pytest.mark.parametrize("name", DATA_FILES)
def test_json_is_package_data(name: str) -> None:
    resource = PACKAGE_DATA.joinpath(name)
    assert resource.is_file()
    assert isinstance(json.loads(resource.read_text("utf-8")), dict)


@pytest.mark.parametrize("name", DATA_FILES)
def test_json_is_byte_identical_to_the_react_app_copy(name: str) -> None:
    """``scripts/fetch_*.py`` write both copies; a hand edit of only one would drift.

    Skipped where ``web/`` is absent (e.g. inside the Docker image).
    """
    web_copy = WEB_DATA / name
    if not web_copy.is_file():
        pytest.skip(f"{web_copy} not present (no web/ app in this checkout)")
    assert PACKAGE_DATA.joinpath(name).read_bytes() == web_copy.read_bytes()
