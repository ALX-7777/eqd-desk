"""Helpers for the golden-parity tests.

Golden files are produced by the TypeScript engine (``cd web && npm run golden``, see
``web/scripts/golden/``). Each holds ``{"generator": ..., "data": ...}``.
"""

from __future__ import annotations

import json
import math
from functools import cache
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).parent / "golden"

# Python and V8 use different libm implementations for exp/log, so values can differ in
# the last ulp or two; after a few chained operations that is ~1e-15 relative. These
# tolerances are ~4 orders of magnitude looser than that and ~7 tighter than any display.
RTOL = 1e-10
ATOL = 1e-12


@cache
def load_golden(name: str) -> Any:
    """Return the ``data`` payload of ``tests/parity/golden/<name>.json``."""
    with (GOLDEN_DIR / f"{name}.json").open(encoding="utf-8") as fh:
        return json.load(fh)["data"]


def assert_close(
    actual: float, expected: float, *, rtol: float = RTOL, atol: float = ATOL, label: str = ""
) -> None:
    """Assert |actual − expected| ≤ atol + rtol·|expected| (NaN/inf must match exactly)."""
    if not (math.isfinite(actual) and math.isfinite(expected)):
        assert actual == expected or (math.isnan(actual) and math.isnan(expected)), label
        return
    diff = abs(actual - expected)
    bound = atol + rtol * abs(expected)
    assert diff <= bound, (
        f"{label}: {actual!r} vs golden {expected!r} (|Δ|={diff:.3e} > {bound:.3e})"
    )
