"""Repository hygiene that no other test would notice until a commit or an image went wrong.

- Streamlit secrets are ignored by git and by the Docker build context wherever Streamlit
  would read them: the repo root AND next to the packaged entrypoint (Streamlit also reads
  the main script's own ``.streamlit/`` directory).
- The committed seed JSON ends with exactly one newline, so pre-commit's
  ``end-of-file-fixer`` never rewrites a freshly refreshed data file.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

SECRETS = (".streamlit/secrets.toml", "src/eqd_desk/app/.streamlit/secrets.toml")
DATA_DIRS = (ROOT / "src" / "eqd_desk" / "data", ROOT / "web" / "src" / "data")


def git_ignores(path: str) -> bool:
    """Would ``.gitignore`` ignore ``path`` (relative to the repo root; need not exist)?

    ``--no-index`` asks the rules alone, even for a path that is already tracked.
    """
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    cmd = [git, "check-ignore", "--quiet", "--no-index", path]
    result = subprocess.run(cmd, cwd=ROOT, check=False, timeout=60)
    assert result.returncode in (0, 1), result  # 0 = ignored, 1 = not ignored
    return result.returncode == 0


@pytest.mark.parametrize("path", SECRETS)
def test_streamlit_secrets_are_git_ignored(path: str) -> None:
    assert git_ignores(path)


def test_the_theme_next_to_the_secrets_is_not_ignored() -> None:
    assert not git_ignores("src/eqd_desk/app/.streamlit/config.toml")


def test_the_docker_context_re_excludes_secrets_after_allowlisting_src() -> None:
    dockerignore = ROOT / ".dockerignore"
    if not dockerignore.is_file():
        pytest.skip("no .dockerignore in this checkout")
    lines = [ln.strip() for ln in dockerignore.read_text("utf-8").splitlines()]
    # .dockerignore rules apply in order: the exclusion must come after `!src/`
    assert lines.index("**/.streamlit/secrets.toml") > lines.index("!src/")


def _data_files() -> list[Path]:
    return sorted(p for d in DATA_DIRS if d.is_dir() for p in d.glob("*.json"))


def test_there_is_seed_data_to_check() -> None:
    names = {p.name for p in _data_files()}
    assert {"snapshot.json", "history.json"} <= names


@pytest.mark.parametrize("path", _data_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_committed_json_ends_with_one_newline_and_uses_lf(path: Path) -> None:
    data = path.read_bytes()
    assert data.endswith(b"\n")
    assert not data.endswith(b"\n\n")
    assert b"\r\n" not in data
