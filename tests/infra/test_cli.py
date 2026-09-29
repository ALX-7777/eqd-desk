"""``eqd-desk`` launches ``streamlit run`` on the PACKAGED app, passing extra args through."""

from __future__ import annotations

import sys

import pytest

from eqd_desk import cli


def capture_streamlit(monkeypatch: pytest.MonkeyPatch, code: int = 0) -> list[list[str]]:
    """Replace ``streamlit.web.cli.main`` by a stub recording ``sys.argv`` at call time."""
    calls: list[list[str]] = []

    def fake_main() -> int:
        calls.append(list(sys.argv))
        return code

    monkeypatch.setattr("streamlit.web.cli.main", fake_main)
    monkeypatch.setattr(sys, "argv", ["eqd-desk"])  # restored after the test
    return calls


def test_runs_the_packaged_entrypoint_with_extra_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = capture_streamlit(monkeypatch)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--server.port", "9999", "--server.headless", "true"])
    assert exit_info.value.code == 0
    assert calls == [
        [
            "streamlit",
            "run",
            str(cli.APP_SCRIPT),
            "--server.port",
            "9999",
            "--server.headless",
            "true",
        ]
    ]


def test_defaults_to_the_process_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = capture_streamlit(monkeypatch, code=3)
    monkeypatch.setattr(sys, "argv", ["eqd-desk", "--server.port", "8080"])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 3  # streamlit's exit code is propagated
    assert calls == [["streamlit", "run", str(cli.APP_SCRIPT), "--server.port", "8080"]]


def test_packaged_app_files_exist() -> None:
    assert cli.APP_SCRIPT.is_file()
    assert cli.APP_SCRIPT.name == "streamlit_app.py"
    assert cli.APP_SCRIPT.parent.name == "app"
    # the theme is a script-level config next to the entrypoint, so it ships with the wheel
    assert (cli.APP_SCRIPT.parent / ".streamlit" / "config.toml").is_file()
    assert (cli.APP_SCRIPT.parent / "app_pages" / "home.py").is_file()
