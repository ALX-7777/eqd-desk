"""``eqd-desk`` console script: launch the Streamlit app from anywhere.

    eqd-desk                          # → http://localhost:8501
    eqd-desk --server.port 8080       # any `streamlit run` option is passed through
    uvx --from git+https://github.com/ALX-7777/eqd-desk eqd-desk   # no clone needed

The app, its pages and its theme (``app/.streamlit/config.toml``, a script-level config)
ship inside the package, so this works from any working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_SCRIPT = Path(__file__).resolve().parent / "app" / "streamlit_app.py"


def main(argv: list[str] | None = None) -> None:
    """Run ``streamlit run <packaged app> [argv...]``."""
    from streamlit.web import cli as stcli

    args = sys.argv[1:] if argv is None else argv
    sys.argv = ["streamlit", "run", str(APP_SCRIPT), *args]
    sys.exit(stcli.main())


if __name__ == "__main__":  # pragma: no cover
    main()
