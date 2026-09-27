"""EQD Desk: an equity-index derivatives trader training simulator.

The package is split into a pure pricing/risk engine (``eqd_desk.engine``), the seed
market data (``eqd_desk.data``), the in-app teaching content (``eqd_desk.content``) and
the Streamlit UI (``eqd_desk.app``). The engine has zero UI dependencies.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("eqd-desk")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0"

__all__ = ["__version__"]
