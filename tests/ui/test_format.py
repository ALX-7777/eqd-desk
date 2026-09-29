"""The formatters print exactly what the React app prints.

Every expected string below was produced by running the TypeScript ``format.ts`` functions
(and the JS built-ins they rely on) under Node 24 on the same inputs, so these are parity
tests, including JavaScript's rounding quirks (exact-binary ``toFixed``, shortest-repr
``toLocaleString``, ties-toward-+∞ ``Math.round``).
"""

from __future__ import annotations

import math

import pytest

from eqd_desk.app.ui import format as f

NAN, INF = math.nan, math.inf


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (0.0, "0"),
        (-0.0, "0"),
        (1.0, "1.0000"),
        (-1.0, "-1.0000"),
        (0.54994, "0.54994"),
        (0.549940123, "0.54994"),
        (7.15412345, "7.1541"),
        (-2.01213, "-2.0121"),
        (2.755, "2.7550"),
        (0.0014962, "0.0014962"),
        (-0.0023055, "-0.0023055"),
        (0.005299, "0.0052990"),
        (119.6123, "119.61"),
        (6312.45, "6312.4"),
        (12345.678, "12346"),
        (99999.5, "100000"),
        (999999.99, "1000000"),
        (1e7, "1.00e+7"),
        (12345678.0, "1.23e+7"),
        (0.0001, "0.00010000"),
        (0.00009999, "1.00e-4"),
        (-0.0000123, "-1.23e-5"),
        (1.005, "1.0050"),
        (2.5, "2.5000"),
        (0.125, "0.12500"),
        (-0.125, "-0.12500"),
        (1234567.891, "1234568"),
        (-17959.06, "-17959"),
        (0.1 + 0.2, "0.30000"),
        (1 / 3, "0.33333"),
        (2 / 3, "0.66667"),
        (99.999995, "100.000"),
        (9.99995, "10.0000"),
        (NAN, "—"),
        (INF, "—"),
        (-INF, "—"),
    ],
)
def test_fmt_num_matches_js(x: float, expected: str) -> None:
    assert f.fmt_num(x) == expected


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (1.0, "1.00"),
        (0.54994, "0.550"),
        (7.15412345, "7.15"),
        (-2.01213, "-2.01"),
        (0.0014962, "0.00150"),
        (-0.0023055, "-0.00231"),
        (119.6123, "120"),
        (6312.45, "6312"),
        (0.0001, "0.000100"),
        (1.005, "1.00"),
        (0.125, "0.125"),
        (99.999995, "100.0"),
        (9.99995, "10.00"),
    ],
)
def test_fmt_num_three_sig_figs(x: float, expected: str) -> None:
    assert f.fmt_num(x, 3) == expected


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (0.0, "0"),
        (-0.0, "0"),
        (1.0, "+1.0000"),
        (-1.0, "−1.0000"),
        (-2.01213, "−2.0121"),
        (6312.45, "+6312.4"),
        (-0.0000123, "−1.23e-5"),
        (12345678.0, "+1.23e+7"),
        (NAN, "—"),
    ],
)
def test_fmt_signed_uses_typographic_minus(x: float, expected: str) -> None:
    assert f.fmt_signed(x) == expected


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (0.0, "0.00"),
        (-0.0, "-0.00"),
        (1.0, "1.00"),
        (-1.0, "-1.00"),
        (0.54994, "0.55"),
        (2.755, "2.76"),  # shortest repr "2.755" rounds up (toFixed would give 2.75)
        (0.0014962, "0.00"),
        (-0.0023055, "-0.00"),
        (0.005299, "0.01"),
        (119.6123, "119.61"),
        (6312.45, "6,312.45"),
        (12345.678, "12,345.68"),
        (99999.5, "99,999.50"),
        (999999.99, "999,999.99"),
        (1e7, "10,000,000.00"),
        (1.005, "1.01"),
        (0.125, "0.13"),
        (-0.125, "-0.13"),
        (1234567.891, "1,234,567.89"),
        (-17959.06, "-17,959.06"),
        (99.999995, "100.00"),
        (INF, "—"),
    ],
)
def test_fmt_money_matches_intl(x: float, expected: str) -> None:
    assert f.fmt_money(x) == expected


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (0.54994, "1"),
        (2.755, "3"),
        (-0.0023055, "-0"),
        (2.5, "3"),
        (0.125, "0"),
        (-0.125, "-0"),
        (6312.45, "6,312"),
        (99999.5, "100,000"),
        (2 / 3, "1"),
        (-17959.06, "-17,959"),
    ],
)
def test_fmt_money_zero_dp(x: float, expected: str) -> None:
    assert f.fmt_money(x, 0) == expected


@pytest.mark.parametrize(
    ("x", "dp2", "dp1", "dp0"),
    [
        (0.146, "14.60%", "14.6%", "15%"),
        (0.043, "4.30%", "4.3%", "4%"),
        (0.013, "1.30%", "1.3%", "1%"),
        (0.0005, "0.05%", "0.1%", "0%"),
        (0.12345, "12.35%", "12.3%", "12%"),
        (-0.0213, "-2.13%", "-2.1%", "-2%"),
        (0.999999, "100.00%", "100.0%", "100%"),
        (0.00125, "0.13%", "0.1%", "0%"),
        (1.005, "100.50%", "100.5%", "100%"),
        (0.0555, "5.55%", "5.5%", "6%"),
    ],
)
def test_fmt_pct(x: float, dp2: str, dp1: str, dp0: str) -> None:
    assert (f.fmt_pct(x), f.fmt_pct(x, 1), f.fmt_pct(x, 0)) == (dp2, dp1, dp0)
    assert f.fmt_pct(NAN) == "—"


@pytest.mark.parametrize(
    ("x", "dp", "expected"),
    [
        (1.005, 2, "1.00"),
        (2.5, 0, "3"),
        (0.125, 2, "0.13"),
        (-0.125, 2, "-0.13"),
        (-2.5, 0, "-3"),
        (-0.001, 2, "-0.00"),
        (-0.0, 2, "0.00"),
        (1.45, 1, "1.4"),
        (8.345, 2, "8.35"),
        (0.0821917808219178, 3, "0.082"),
    ],
)
def test_to_fixed_is_javascript_to_fixed(x: float, dp: int, expected: str) -> None:
    assert f.to_fixed(x, dp) == expected


@pytest.mark.parametrize(
    ("x", "dp", "expected"),
    [
        (12345678.0, 2, "1.23e+7"),
        (0.0000123, 2, "1.23e-5"),
        (-0.0000123, 2, "-1.23e-5"),
        (9.995e-5, 2, "1.00e-4"),  # mantissa rounds up to 10 → renormalised
        (0.0, 2, "0.00e+0"),
        (1.5e21, 2, "1.50e+21"),
    ],
)
def test_to_exponential(x: float, dp: int, expected: str) -> None:
    assert f.to_exponential(x, dp) == expected


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (0.549940123, "0.549940"),
        (7.1541, "7.15410"),
        (-2.0121e-5, "-0.0000201210"),
        (123456789.0, "1.23457e+8"),
        (0.0, "0.00000"),
    ],
)
def test_to_precision(x: float, expected: str) -> None:
    assert f.to_precision(x, 6) == expected


@pytest.mark.parametrize(
    ("x", "bare", "two_dp"),
    [
        (6312.45, "6,312.45", "6,312.45"),
        (5000.0, "5,000", "5,000"),
        (1234.5678, "1,234.568", "1,234.57"),
        (0.1234, "0.123", "0.12"),
        (1e6, "1,000,000", "1,000,000"),
        (-1234.5, "-1,234.5", "-1,234.5"),
        (99.9996, "100", "100"),
    ],
)
def test_to_locale_and_fmt_level(x: float, bare: str, two_dp: str) -> None:
    assert f.to_locale(x) == bare
    assert f.fmt_level(x, 3) == bare
    assert f.fmt_level(x) == two_dp


def test_to_locale_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        f.to_locale(NAN)
    assert f.fmt_level(NAN) == "—"


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (0.5, 1),
        (1.5, 2),
        (2.5, 3),
        (-0.5, 0),
        (-1.5, -1),
        (-2.5, -2),
        (0.49999999999999994, 0),
        (29.9999, 30),
        (30.0000001, 30),
        (364.9999999, 365),
    ],
)
def test_js_round(x: float, expected: int) -> None:
    assert f.js_round(x) == expected


def test_sign_class() -> None:
    assert f.sign_class(0.1) == "pos"
    assert f.sign_class(-1e-12) == "neg"
    assert f.sign_class(0.0) == "zero"
    assert f.sign_class(-0.0) == "zero"
    assert f.sign_class(NAN) == "zero"
    assert f.sign_class(INF) == "zero"


def test_component_patterns() -> None:
    # InputPanel's T readout, the simulator's P&L / lean, and level / unit labels.
    assert f.fmt_years_days(30 / 365) == "0.082 y · 30 d"
    assert f.fmt_years_days(0.5) == "0.500 y · 183 d"
    assert f.fmt_days(60 / 365) == "60 d"
    assert f.fmt_signed_money(17959.06) == "+17,959.06"
    assert f.fmt_signed_money(-1234.0) == "-1,234.00"
    assert f.fmt_signed_money(0.0) == "+0.00"
    assert f.fmt_signed_pct(0.0025) == "+0.25%"
    assert f.fmt_signed_pct(-0.011) == "-1.10%"
    assert f.fmt_level(6300.0) == "6,300"
    assert f.fmt_with_unit("6,312.45", "USD") == "6,312.45 USD"
    assert f.fmt_with_unit("6,312.45", None) == "6,312.45"
    for fn in (f.fmt_signed_money, f.fmt_signed_pct, f.fmt_days, f.fmt_years_days):
        assert fn(NAN) == "—"


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        # JavaScript String(x), from Node 24
        (3, "3"),
        (2.5, "2.5"),
        (100.0, "100"),
        (-0.0, "0"),
        (0.1 + 0.2, "0.30000000000000004"),
        (1e-7, "1e-7"),
        (1.5e-7, "1.5e-7"),
        (1e21, "1e+21"),
        (1.5e21, "1.5e+21"),
        (0.00001, "0.00001"),
        (0.000001, "0.000001"),
        (NAN, "NaN"),
        (INF, "Infinity"),
        (-INF, "-Infinity"),
        (6312.45, "6312.45"),
        (-25.0, "-25"),
        (1e20, "100000000000000000000"),
        (5e-324, "5e-324"),
        (-0.000123, "-0.000123"),
    ],
)
def test_js_number_is_javascript_string(x: float, expected: str) -> None:
    assert f.js_number(x) == expected


def test_slider_thumb_formats() -> None:
    # Streamlit format strings: a preset for percentages, printf for levels and years
    assert f.THUMB_PERCENT == "percent"
    assert f.THUMB_LEVEL == "%,.2f"
    assert f.THUMB_YEARS == "%.3f y"
