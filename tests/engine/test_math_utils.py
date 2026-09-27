from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from eqd_desk.engine import SQRT_2PI, norm_cdf, norm_pdf


def test_norm_pdf_known_values() -> None:
    assert norm_pdf(0) == pytest.approx(1 / SQRT_2PI, abs=1e-15)
    assert norm_pdf(0) == pytest.approx(0.3989422804014327, abs=1e-15)
    assert norm_pdf(1) == pytest.approx(0.24197072451914337, abs=1e-15)
    assert norm_pdf(-1) == pytest.approx(0.24197072451914337, abs=1e-15)  # even function
    assert norm_pdf(2) == pytest.approx(0.05399096651318806, abs=1e-15)


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (0.0, 0.5),
        (1.0, 0.8413447460685429),
        (-1.0, 0.15865525393145707),
        (2.0, 0.9772498680518208),
        (-2.0, 0.022750131948179195),
        (1.96, 0.9750021048517795),
        (1.6448536269514722, 0.95),
        (3.0, 0.9986501019683699),
        (-3.0, 0.0013498980316300933),
    ],
)
def test_norm_cdf_known_values(x: float, expected: float) -> None:
    assert norm_cdf(x) == pytest.approx(expected, abs=1e-12)


def test_norm_cdf_matches_erfc_reference() -> None:
    # Independent reference: N(x) = erfc(−x/√2)/2, accurate to ~1 ulp in CPython.
    for x in np.linspace(-6, 6, 241):
        ref = 0.5 * math.erfc(-x / math.sqrt(2))
        assert norm_cdf(float(x)) == pytest.approx(ref, rel=1e-13, abs=1e-16)


@pytest.mark.parametrize("x", [0.1, 0.5, 1.0, 2.3, 4.7, 6.5])
def test_norm_cdf_symmetric(x: float) -> None:
    assert norm_cdf(x) + norm_cdf(-x) == pytest.approx(1.0, abs=1e-14)


def test_norm_cdf_monotone_and_bounded() -> None:
    xs = np.arange(-50, 50, 0.25)
    vals = [norm_cdf(float(x)) for x in xs]
    assert all(b >= a for a, b in itertools.pairwise(vals))
    assert all(0.0 <= v <= 1.0 for v in vals)


def test_norm_cdf_deep_tails_keep_relative_accuracy() -> None:
    ref5 = 2.8665157187919333e-7  # P(Z < −5)
    ref8 = 6.220960574271782e-16  # P(Z < −8)
    assert abs(norm_cdf(-5) / ref5 - 1) < 1e-9
    assert abs(norm_cdf(-8) / ref8 - 1) < 1e-7
    assert norm_cdf(-40) == 0.0  # underflow region
    assert norm_cdf(40) == 1.0
