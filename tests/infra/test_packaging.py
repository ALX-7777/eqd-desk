"""What ships: build the sdist and the wheel from a copy of the source tree and inspect them.

The source-tree tests import ``eqd_desk`` from ``src/``, so they cannot see a packaging
mistake: package data left out of the wheel, or a local file that should never ship
(Streamlit secrets next to the packaged entrypoint) put into it. Skipped without ``uv``.
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
from email.parser import HeaderParser
from pathlib import Path

import pytest

from eqd_desk.app.ui.nav import PAGES

ROOT = Path(__file__).resolve().parents[2]

SECRETS = ("src/eqd_desk/app/.streamlit/secrets.toml", "src/eqd_desk/.streamlit/secrets.toml")
"""Where a developer could plausibly drop a Streamlit secrets file inside the package."""


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """``uv build`` of a copy of the project, with dummy secrets planted in the package."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    if not (ROOT / "pyproject.toml").is_file():
        pytest.skip("not a source checkout")
    project = tmp_path_factory.mktemp("project")
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, project / name)
    shutil.copytree(
        ROOT / "src",
        project / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.py[cod]", "secrets.toml"),
    )
    for rel in SECRETS:
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_text('api_key = "do-not-ship"\n', encoding="utf-8")
    out = project / "dist"
    subprocess.run(
        [uv, "build", "--sdist", "--wheel", "--out-dir", str(out), "--quiet"],
        cwd=project,
        check=True,
        timeout=300,
    )
    return out


def _only(dist: Path, pattern: str) -> Path:
    (path,) = dist.glob(pattern)
    return path


@pytest.fixture(scope="module")
def wheel_names(dist: Path) -> list[str]:
    with zipfile.ZipFile(_only(dist, "*.whl")) as whl:
        return whl.namelist()


@pytest.fixture(scope="module")
def sdist_names(dist: Path) -> list[str]:
    with tarfile.open(_only(dist, "*.tar.gz")) as sdist:
        return sdist.getnames()


def test_the_wheel_ships_the_app_its_pages_theme_and_data(wheel_names: list[str]) -> None:
    expected = {
        "eqd_desk/cli.py",
        "eqd_desk/py.typed",
        "eqd_desk/app/streamlit_app.py",
        "eqd_desk/app/.streamlit/config.toml",
        "eqd_desk/data/snapshot.json",
        "eqd_desk/data/history.json",
        *(f"eqd_desk/app/{spec.file}" for spec in PAGES),
    }
    assert expected <= set(wheel_names)


def test_no_streamlit_secrets_in_the_wheel_or_the_sdist(
    wheel_names: list[str], sdist_names: list[str]
) -> None:
    assert [n for n in wheel_names if n.endswith("secrets.toml")] == []
    assert [n for n in sdist_names if n.endswith("secrets.toml")] == []
    # ... while the theme next to them still ships in both
    assert "eqd_desk/app/.streamlit/config.toml" in wheel_names
    assert any(n.endswith("src/eqd_desk/app/.streamlit/config.toml") for n in sdist_names)


def test_the_wheel_metadata_links_back_to_the_repository(dist: Path) -> None:
    with zipfile.ZipFile(_only(dist, "*.whl")) as whl:
        (meta_name,) = [n for n in whl.namelist() if n.endswith(".dist-info/METADATA")]
        meta = HeaderParser().parsestr(whl.read(meta_name).decode("utf-8"))
    urls = dict(u.split(", ", 1) for u in meta.get_all("Project-URL", []))
    assert urls["Repository"] == "https://github.com/ALX-7777/eqd-desk"
    assert {"Homepage", "Issues", "Documentation"} <= set(urls)
    assert meta["Name"] == "eqd-desk"
    # the README is the long description: it must describe THIS product
    description = meta.get_payload()
    assert isinstance(description, str)
    assert description.lstrip().startswith("# EQD Desk")
