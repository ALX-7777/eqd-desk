"""Number formatting for the trading-terminal readouts (port of ``web/src/components/format.ts``).

Numbers are the product, so formatting is adaptive: enough significant figures to be useful,
exponential notation only for the very small/large, an em-dash for non-finite values.

Every function reproduces the React app's output string-for-string, including JavaScript's
rounding rules, so the Streamlit and React apps print identical numbers for identical inputs:

- ``Number.prototype.toFixed`` / ``toExponential`` round the EXACT binary value of the double,
  ties away from zero (``(1.005).toFixed(2) == "1.00"`` because 1.005 is stored as
  1.00499999…; ``(0.125).toFixed(2) == "0.13"``). Python's ``format(x, ".2f")`` rounds ties to
  even instead (``"0.12"``), hence :func:`to_fixed`.
- ``toLocaleString('en-US', …)`` (used for money) rounds the SHORTEST decimal representation
  of the double, ties away from zero (``(1.005).toLocaleString(…2dp) == "1.01"``), and prints
  negative zero as ``"-0.00"``; see :func:`to_locale`.
- ``Math.round`` rounds ties toward +∞ (``Math.round(-2.5) == -2``); see :func:`js_round`.

Minus signs follow the React app: plain formatters print the ASCII hyphen-minus (``-2.0121``,
as ``toFixed`` does); :func:`fmt_signed` prints the typographic minus (``−2.0121``).
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Context, Decimal
from typing import Final, Literal

EM_DASH: Final = "—"
"""What every formatter returns for NaN / ±∞ (a visible "no number")."""

MINUS: Final = "−"
"""Typographic minus (U+2212), used by the explicitly signed formatters."""

_CTX: Final = Context(prec=80)
"""Enough precision to quantize any finite double we format without an InvalidOperation."""

SignClass = Literal["pos", "neg", "zero"]
"""Sign bucket used to colour a number (see :func:`sign_class`)."""


# ------------------------------------------------------------------ JavaScript primitives


def _quantize(d: Decimal, dp: int) -> Decimal:
    """Round ``d`` to ``dp`` decimals, ties away from zero (JS's rule for both toFixed and Intl)."""
    return d.quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP, context=_CTX)


def to_fixed(x: float, dp: int) -> str:
    """JavaScript ``x.toFixed(dp)`` for a finite ``x`` (``0 <= dp <= 100``).

    Rounds the exact binary value half away from zero; negative zero prints as ``"0.00"``,
    while a small negative that rounds to zero keeps its sign (``(-0.001).toFixed(2)`` is
    ``"-0.00"``), exactly like JS.
    """
    if x == 0:
        return format(_quantize(Decimal(0), dp), "f")
    return format(_quantize(Decimal(x), dp), "f")


def to_exponential(x: float, dp: int) -> str:
    """JavaScript ``x.toExponential(dp)`` for a finite ``x``: ``1.23e+7``, ``-1.23e-5``.

    One leading digit, ``dp`` decimals of mantissa (exact binary value, ties away from zero),
    and an exponent with an explicit sign and no zero padding.
    """
    if x == 0:
        return f"{to_fixed(0.0, dp)}e+0"
    d = abs(Decimal(x))
    exp = d.adjusted()
    mantissa = _quantize(d.scaleb(-exp, context=_CTX), dp)
    if mantissa >= 10:  # 9.995 → 10.00: renormalise
        exp += 1
        mantissa = _quantize(d.scaleb(-exp, context=_CTX), dp)
    sign = "-" if x < 0 else ""
    exp_sign = "+" if exp >= 0 else "-"
    return f"{sign}{format(mantissa, 'f')}e{exp_sign}{abs(exp)}"


def to_precision(x: float, precision: int) -> str:
    """JavaScript ``x.toPrecision(precision)`` for a finite ``x`` (``precision >= 1``).

    Fixed notation with ``precision`` significant figures, unless the decimal exponent is
    below −6 or at least ``precision``, in which case exponential notation is used (the React
    readout prints the raw partials this way, e.g. ``"0.549940"``, ``"1.23457e+8"``).
    """
    if x == 0:
        return to_fixed(0.0, precision - 1)
    d = abs(Decimal(x))
    exp = d.adjusted()
    rounded = _quantize(d.scaleb(-exp, context=_CTX), precision - 1)
    if rounded >= 10:
        exp += 1
    if exp < -6 or exp >= precision:
        return to_exponential(x, precision - 1)
    return to_fixed(x, precision - 1 - exp)


def _group_thousands(digits: str) -> str:
    """Insert en-US thousands separators into an unsigned integer digit string."""
    return f"{int(digits):,}"


def to_locale(x: float, min_dp: int = 0, max_dp: int = 3) -> str:
    """JavaScript ``x.toLocaleString('en-US', {minimumFractionDigits, maximumFractionDigits})``.

    Groups thousands with commas and rounds the shortest round-trip decimal of ``x`` (what
    ``repr`` prints) half away from zero, keeping between ``min_dp`` and ``max_dp`` decimals.
    The defaults (0, 3) are those of a bare ``x.toLocaleString('en-US')``. Negative values,
    including negative zero, keep a hyphen-minus (``"-0.00"``), as ICU prints them.
    """
    if not math.isfinite(x):
        raise ValueError(f"to_locale: non-finite value {x!r}")
    negative = math.copysign(1.0, x) < 0
    q = _quantize(abs(Decimal(repr(x))), max_dp)
    text = format(q, "f")
    whole, _, frac = text.partition(".")
    frac = frac.rstrip("0")
    frac = frac.ljust(min_dp, "0")
    body = _group_thousands(whole) + (f".{frac}" if frac else "")
    return f"-{body}" if negative else body


def js_round(x: float) -> int:
    """JavaScript ``Math.round``: nearest integer, ties toward +∞ (``2.5 → 3``, ``−2.5 → −2``).

    Written as floor + compare (not ``floor(x + 0.5)``) so that 0.49999999999999994 rounds to
    0, as it does in JS.
    """
    f = math.floor(x)
    return f + 1 if x - f >= 0.5 else f


def js_number(x: float) -> str:
    """JavaScript ``String(x)`` (what a template literal prints for a number): integers
    without a decimal point (``3``, ``100``), other values with the shortest digits that
    round-trip (``2.5``, ``0.1``), fixed notation from 1e-6 up to 1e21 and exponential
    beyond (``1e-7``, ``1.5e+21``); ``-0`` prints ``0``, non-finite values ``NaN`` /
    ``Infinity`` / ``-Infinity``."""
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    if 1e-6 <= abs(x) < 1e21:
        text = format(Decimal(repr(x)), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    mantissa, _, exponent = repr(x).partition("e")
    return f"{mantissa.removesuffix('.0')}e{int(exponent):+d}"


# ------------------------------------------------------------------ format.ts


def fmt_num(x: float, sig: int = 5) -> str:
    """Adaptive numeric format targeting about ``sig`` significant figures (``fmtNum``).

    ``0 → "0"``; ``|x| >= 1e7`` or ``< 1e-4`` → two-decimal exponential (``"1.23e+7"``);
    otherwise fixed with ``sig − (integer digits)`` decimals, clamped to 0…8
    (``0.54994``, ``7.1541``, ``6312.4``, ``-0.0023055``). Non-finite → em-dash.
    """
    if not math.isfinite(x):
        return EM_DASH
    if x == 0:
        return "0"
    a = abs(x)
    if a >= 1e7 or a < 1e-4:
        return to_exponential(x, 2)
    int_digits = math.floor(math.log10(a)) + 1
    dp = min(8, max(0, sig - int_digits))
    return to_fixed(x, dp)


def fmt_signed(x: float, sig: int = 5) -> str:
    """Like :func:`fmt_num` but always with an explicit ``+`` / ``−`` sign (``fmtSigned``).

    Uses the typographic minus (U+2212); zero has no sign.
    """
    if not math.isfinite(x):
        return EM_DASH
    s = fmt_num(abs(x), sig)
    if x > 0:
        return f"+{s}"
    if x < 0:
        return f"{MINUS}{s}"
    return s


def fmt_money(x: float, dp: int = 2) -> str:
    """Currency-style format with thousands separators and exactly ``dp`` decimals
    (``fmtMoney``): ``6312.45 → "6,312.45"``, ``-17959.06 → "-17,959.06"``."""
    if not math.isfinite(x):
        return EM_DASH
    return to_locale(x, dp, dp)


def fmt_pct(x: float, dp: int = 2) -> str:
    """Percent of a decimal (``fmtPct``): ``0.146 → "14.60%"``, ``0.146, dp=1 → "14.6%"``."""
    if not math.isfinite(x):
        return EM_DASH
    return f"{to_fixed(x * 100, dp)}%"


def sign_class(x: float) -> SignClass:
    """Sign bucket for colouring (``signClass``): ``"pos"`` / ``"neg"``, or ``"zero"`` for 0
    and non-finite values."""
    if not math.isfinite(x) or x == 0:
        return "zero"
    return "pos" if x > 0 else "neg"


# ------------------------------------------------------------------ patterns from the components


def fmt_level(x: float, max_dp: int = 2) -> str:
    """An index / price level with grouping and at most ``max_dp`` decimals, trailing zeros
    dropped (``x.toLocaleString('en-US', {maximumFractionDigits: 2})``): ``6312.45 →
    "6,312.45"``, ``6300 → "6,300"``. The header's spot uses ``max_dp=3`` (a bare
    ``toLocaleString``)."""
    if not math.isfinite(x):
        return EM_DASH
    return to_locale(x, 0, max_dp)


def fmt_signed_money(x: float, dp: int = 2) -> str:
    """P&L style: ``+`` for ``x >= 0``, then :func:`fmt_money` (which carries the ``-``):
    ``"+17,959.06"``, ``"-1,234.00"`` (``${pnl >= 0 ? '+' : ''}${fmtMoney(pnl)}``)."""
    if not math.isfinite(x):
        return EM_DASH
    return f"{'+' if x >= 0 else ''}{fmt_money(x, dp)}"


def fmt_signed_pct(x: float, dp: int = 2) -> str:
    """``+`` for ``x >= 0``, then :func:`fmt_pct`: ``"+0.25%"``, ``"-1.10%"`` (the simulator's
    lean and the variance swap's convexity premium)."""
    if not math.isfinite(x):
        return EM_DASH
    return f"{'+' if x >= 0 else ''}{fmt_pct(x, dp)}"


def fmt_days(t_years: float) -> str:
    """A year fraction as whole calendar days: ``30/365 → "30 d"`` (``Math.round(T * 365)``)."""
    if not math.isfinite(t_years):
        return EM_DASH
    return f"{js_round(t_years * 365)} d"


def fmt_years_days(t_years: float, dp: int = 3) -> str:
    """Time to expiry as ``"0.082 y · 30 d"`` (the greeks lab's T readout)."""
    if not math.isfinite(t_years):
        return EM_DASH
    return f"{to_fixed(t_years, dp)} y · {fmt_days(t_years)}"


def fmt_with_unit(text: str, unit: str | None) -> str:
    """Append a unit after a thin separator (``"6,312.45 USD"``); no unit → text unchanged."""
    return f"{text} {unit}" if unit else text


# ------------------------------------------------------------------ slider thumbs
# Streamlit ``format`` strings for a slider's thumb label (a printf string or a preset), so a
# thumb reads in the units of the value printed above it.

THUMB_PERCENT: Final = "percent"
"""A decimal shown as a percentage (0.146 → ``14.6%``): vols, rates, yields, barriers and
coupons, like the header's ``14.60%``."""

THUMB_LEVEL: Final = "%,.2f"
"""An index level or an amount, grouped (``6,312.45``), like the header's ``6,312.45 USD``."""

THUMB_YEARS: Final = "%.3f y"
"""A time to expiry in years (``0.082 y``), like the header's ``0.082 y · 30 d``."""


__all__ = [
    "EM_DASH",
    "MINUS",
    "THUMB_LEVEL",
    "THUMB_PERCENT",
    "THUMB_YEARS",
    "SignClass",
    "fmt_days",
    "fmt_level",
    "fmt_money",
    "fmt_num",
    "fmt_pct",
    "fmt_signed",
    "fmt_signed_money",
    "fmt_signed_pct",
    "fmt_with_unit",
    "fmt_years_days",
    "js_number",
    "js_round",
    "sign_class",
    "to_exponential",
    "to_fixed",
    "to_locale",
    "to_precision",
]
