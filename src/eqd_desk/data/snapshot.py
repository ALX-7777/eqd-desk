"""Typed loader + light runtime validation for the seed snapshot.

The app builds its initial market state from this; all data fetching lives in
``scripts/fetch_snapshot.py`` and stays OUT of the reactive loop. The committed seed
``snapshot.json`` ships inside the package (read with :mod:`importlib.resources`), so the
app runs from an installed wheel or a Docker image with no network access.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any, Final

from eqd_desk.engine.types import BsmInputs

SNAPSHOT_RESOURCE: Final = "snapshot.json"
"""File name of the committed seed snapshot inside the ``eqd_desk.data`` package."""

SEED_T: Final = 30 / 365
"""Tenor of the seeded Greeks-Lab option: 30 calendar days, as a year fraction."""


@dataclass(frozen=True, slots=True)
class SkewParams:
    """Quadratic skew in log-moneyness: iv(k) ≈ atm + slope·k + curv·k², k = ln(K/S).

    All three are decimals of vol (0.146 = 14.6 vol points); ``slope`` and ``curv`` are per
    unit of log-moneyness and per unit of log-moneyness squared respectively.
    """

    atm: float
    """ATM level (decimal vol)."""
    slope: float
    """First-order coefficient: negative for an equity skew (low strikes trade richer)."""
    curv: float
    """Second-order coefficient: positive for a smile (both wings lifted)."""


@dataclass(frozen=True, slots=True)
class TermPoint:
    """One ATM point of the term structure."""

    t: float
    """Tenor in years."""
    atm_iv: float
    """ATM implied vol at that tenor (decimal)."""


@dataclass(frozen=True, slots=True)
class SnapshotTickers:
    """The data sources the snapshot was built from."""

    index_ticker: str
    """Real index ticker (spot + realized vol), e.g. ``^GSPC``."""
    vol_ticker: str
    """Vol-gauge ticker (ATM level), e.g. ``^VIX``."""
    options_proxy: str
    """Listed ETF whose option chain gave the skew shape, e.g. ``SPY``."""


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """The seed market snapshot (mirror of ``fetch_snapshot.py``'s JSON shape).

    Units: ``spot`` in index points of ``currency``; ``r``, ``q`` continuously compounded
    decimals; every vol a decimal (0.146 = 14.6 vol points), annualised.

    Frozen (sequences are tuples), so a snapshot is hashable and safe to cache; build a
    variant with ``dataclasses.replace(snap, spot=5000)``.
    """

    asof: str
    """ISO date of the last index close used (``YYYY-MM-DD``)."""
    underlying: str
    """Underlying key (``"spx"`` / ``"sx5e"``)."""
    name: str
    """Display name of the index."""
    currency: str
    """Premium currency."""
    spot: float
    """Index level (> 0)."""
    r: float
    """Continuously-compounded short rate (decimal)."""
    q: float
    """Continuously-compounded dividend yield (decimal)."""
    realized_vol: float | None
    """Trailing 1y close-to-close realized vol (decimal), or ``None`` if unavailable."""
    atm_vol_30d: float
    """30-day ATM implied vol anchor from the vol index (decimal, > 0)."""
    skew: SkewParams
    """Smile shape in log-moneyness."""
    term_structure: tuple[TermPoint, ...]
    """ATM implied vol by tenor (may be empty)."""
    source_notes: tuple[str, ...]
    """Human-readable provenance / fallback notes."""
    tickers: SnapshotTickers
    """Where the data came from."""

    def as_dict(self) -> dict[str, Any]:
        """The snapshot as a plain JSON-shaped dict (lists, not tuples): the inverse of
        :func:`validate_snapshot`."""
        return {
            "asof": self.asof,
            "underlying": self.underlying,
            "name": self.name,
            "currency": self.currency,
            "spot": self.spot,
            "r": self.r,
            "q": self.q,
            "realized_vol": self.realized_vol,
            "atm_vol_30d": self.atm_vol_30d,
            "skew": {"atm": self.skew.atm, "slope": self.skew.slope, "curv": self.skew.curv},
            "term_structure": [{"t": p.t, "atm_iv": p.atm_iv} for p in self.term_structure],
            "source_notes": list(self.source_notes),
            "tickers": {
                "index_ticker": self.tickers.index_ticker,
                "vol_ticker": self.tickers.vol_ticker,
                "options_proxy": self.tickers.options_proxy,
            },
        }


class _Missing:
    """Marker for an absent key (JavaScript's ``undefined``), distinct from JSON ``null``."""

    def __repr__(self) -> str:
        return "undefined"


_MISSING: Final = _Missing()


# --- JavaScript value semantics ---------------------------------------------------------
# The TS validator renders offending values with JSON.stringify and coerces strings with
# String(). Python's json.dumps / str() differ on many JSON-shaped values (True vs true,
# 5.0 vs 5, 1e-07 vs 1e-7, NaN vs null, "€" vs "€"...), so these helpers reproduce the
# JavaScript rules and the Python error messages / coerced strings stay byte-identical.


def _to_js_number(v: int | float) -> float:
    """The IEEE-754 double a JavaScript engine holds for this JSON number.

    ``JSON.parse`` turns every number into a double, and an integer literal too large for one
    (beyond ~1.8e308) becomes ±Infinity. Python's :mod:`json` keeps integers exact (arbitrary
    precision), and ``float()`` of such an int raises :class:`OverflowError`; map that to
    ±inf instead, so the value is simply rejected as non-finite.
    """
    try:
        return float(v)
    except OverflowError:
        return math.inf if v > 0 else -math.inf


def _js_number_string(x: float) -> str:
    """JavaScript ``String(x)`` for a double (ECMAScript ``Number::toString``, radix 10).

    Both languages print the SHORTEST digit string that round-trips (``repr`` gives it);
    only the layout differs. With ``x = 0.d₁…d_k × 10ⁿ`` (k significant digits):
      - k ≤ n ≤ 21   → the digits then n − k zeros       (``5.0`` → ``5``, 1e20 → 21 digits);
      - 0 < n ≤ 21   → a decimal point after n digits    (``123.456``);
      - −6 < n ≤ 0   → ``0.``, −n zeros, then the digits  (``1e-06`` → ``0.000001``);
      - otherwise    → exponent form, sign always shown  (``1e-07`` → ``1e-7``, ``1e+21``).
    ``-0`` prints as ``0``; NaN / ±inf as ``NaN`` / ``Infinity`` / ``-Infinity``.
    """
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    mantissa, _, exp = repr(abs(x)).partition("e")  # e.g. "1.5", "e", "-07"
    int_part, _, frac_part = mantissa.partition(".")
    all_digits = int_part + frac_part
    stripped = all_digits.lstrip("0")
    n = len(int_part) + (int(exp) if exp else 0) - (len(all_digits) - len(stripped))
    digits = stripped.rstrip("0")
    k = len(digits)
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = f"{digits[:n]}.{digits[n:]}"
    elif -6 < n <= 0:
        body = "0." + "0" * -n + digits
    else:
        e = f"{n - 1:+d}"  # "+21" / "-7"
        body = f"{digits}e{e}" if k == 1 else f"{digits[0]}.{digits[1:]}e{e}"
    return sign + body


def _js_string(v: object) -> str:
    """JavaScript ``String(v)`` for a JSON-shaped value.

    ``null`` → ``"null"``, booleans → ``"true"``/``"false"``, numbers per
    :func:`_js_number_string`, arrays → their items joined with ``","`` (``null`` items
    empty, like ``Array.prototype.join``), objects → ``"[object Object]"``.
    """
    if v is None:
        return "null"
    if isinstance(v, _Missing):
        return "undefined"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return _js_number_string(_to_js_number(v))
    if isinstance(v, str):
        return v
    if isinstance(v, list | tuple):
        return ",".join("" if x is None or isinstance(x, _Missing) else _js_string(x) for x in v)
    if isinstance(v, Mapping):
        return "[object Object]"
    return str(v)  # not JSON-shaped: no JavaScript counterpart


_JSON_ESCAPES: Final = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _json_quote(s: str) -> str:
    """A string literal as ``JSON.stringify`` writes it.

    Only ``"``, ``\\``, control characters (< U+0020) and lone surrogates are escaped;
    everything else (é, €, emoji) is kept as-is (unlike ``json.dumps``'s default
    ``ensure_ascii``, which would write ``"\\u20ac"`` for ``"€"``).
    """
    out: list[str] = []
    for ch in s:
        code = ord(ch)
        if ch in _JSON_ESCAPES:
            out.append(_JSON_ESCAPES[ch])
        elif code < 0x20 or 0xD800 <= code <= 0xDFFF:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _is_array_index(key: str) -> bool:
    """Is ``key`` a canonical array index ("0", "7", "42" — not "01", max 2³² − 2)?

    JavaScript objects list such keys FIRST, in ascending numeric order, then the other
    keys in insertion order; ``JSON.stringify`` follows that property order.
    """
    canonical = key == "0" or (key.isascii() and key.isdigit() and not key.startswith("0"))
    return canonical and int(key) <= 2**32 - 2


def _json_stringify(v: object) -> str:
    """Render an offending value for an error message exactly like ``JSON.stringify(v)``.

    Compact; non-finite numbers → ``null``; numbers formatted as JavaScript prints them;
    object keys in JavaScript property order; a missing key (``undefined``) → ``undefined``
    (``JSON.stringify(undefined)`` is ``undefined``, which the template literal prints).
    """
    if isinstance(v, _Missing):
        return "undefined"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        x = _to_js_number(v)
        return _js_number_string(x) if math.isfinite(x) else "null"
    if isinstance(v, str):
        return _json_quote(v)
    if isinstance(v, list | tuple):
        return "[" + ",".join(_json_stringify(x) for x in v) + "]"
    if isinstance(v, Mapping):
        items = [(_js_string(key), x) for key, x in v.items()]
        ordered = sorted(
            (kv for kv in items if _is_array_index(kv[0])), key=lambda kv: int(kv[0])
        ) + [kv for kv in items if not _is_array_index(kv[0])]
        return (
            "{" + ",".join(f"{_json_quote(key)}:{_json_stringify(x)}" for key, x in ordered) + "}"
        )
    return repr(v)  # not JSON-shaped: no JavaScript counterpart


def _num(v: object, path: str) -> float:
    """Return ``v`` as a float if it is a finite number, else raise.

    Booleans are rejected even though Python treats them as ints: in the JSON they would
    be ``true``/``false``, never a number. An integer too large for a double counts as
    ±Infinity (what ``JSON.parse`` gives in TS), so it is rejected with ``got null``.

    Raises:
        ValueError: if ``v`` is missing, not a number, NaN or infinite. The message renders
            ``v`` with ``JSON.stringify`` semantics, so it matches the TS text exactly.
    """
    x = None if isinstance(v, bool) or not isinstance(v, int | float) else _to_js_number(v)
    if x is None or not math.isfinite(x):
        raise ValueError(f'snapshot: expected finite number at "{path}", got {_json_stringify(v)}')
    return x


def _str(v: object) -> str:
    """``String(v ?? '')``: a missing / ``null`` field becomes the empty string; anything
    else is coerced with JavaScript ``String()`` (``true`` → ``"true"``, ``1.0`` → ``"1"``)."""
    if v is None or isinstance(v, _Missing):
        return ""
    return _js_string(v)


def _mapping(v: object) -> Mapping[str, object]:
    """Treat anything that is not a JSON object as an empty one (``v ?? {}``)."""
    return v if isinstance(v, Mapping) else {}


def validate_snapshot(raw: object) -> MarketSnapshot:
    """Validate parsed snapshot JSON and narrow it to :class:`MarketSnapshot`.

    What is enforced (anything else is passed through as-is):
      - ``spot`` and ``atm_vol_30d`` are finite numbers and strictly positive;
      - ``r``, ``q``, ``skew.slope``, ``skew.curv`` are finite numbers;
      - ``realized_vol`` is a finite number or ``null``;
      - ``skew.atm`` defaults to ``atm_vol_30d`` when absent;
      - every ``term_structure`` point has finite ``t`` and ``atm_iv``;
      - missing strings / lists default to ``""`` / empty; other string fields and the
        ``source_notes`` items are coerced with JavaScript ``String()`` semantics.

    Numbers are narrowed the way ``JSON.parse`` sees them (every number a double, an
    integer too large for one = Infinity), and error messages render the offending value
    as ``JSON.stringify`` does, so both match the TypeScript validator byte for byte.

    Raises:
        ValueError: if ``raw`` is not a JSON object or a required number is invalid.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("snapshot: not an object")
    s: Mapping[str, object] = raw
    skew = _mapping(s.get("skew"))
    spot = _num(s.get("spot", _MISSING), "spot")
    if spot <= 0:
        raise ValueError("snapshot: spot must be > 0")
    atm = _num(s.get("atm_vol_30d", _MISSING), "atm_vol_30d")
    if atm <= 0:
        raise ValueError("snapshot: atm_vol_30d must be > 0")
    term_raw = s.get("term_structure")
    term = term_raw if isinstance(term_raw, list | tuple) else []
    notes_raw = s.get("source_notes")
    notes = notes_raw if isinstance(notes_raw, list | tuple) else []
    realized_raw = s.get("realized_vol")
    skew_atm = skew.get("atm")
    tickers = _mapping(s.get("tickers"))
    return MarketSnapshot(
        asof=_str(s.get("asof")),
        underlying=_str(s.get("underlying")),
        name=_str(s.get("name")),
        currency=_str(s.get("currency")),
        spot=spot,
        r=_num(s.get("r", _MISSING), "r"),
        q=_num(s.get("q", _MISSING), "q"),
        realized_vol=None if realized_raw is None else _num(realized_raw, "realized_vol"),
        atm_vol_30d=atm,
        skew=SkewParams(
            atm=_num(atm if skew_atm is None else skew_atm, "skew.atm"),
            slope=_num(skew.get("slope", _MISSING), "skew.slope"),
            curv=_num(skew.get("curv", _MISSING), "skew.curv"),
        ),
        term_structure=tuple(
            TermPoint(
                t=_num(_mapping(p).get("t", _MISSING), f"term_structure[{i}].t"),
                atm_iv=_num(_mapping(p).get("atm_iv", _MISSING), f"term_structure[{i}].atm_iv"),
            )
            for i, p in enumerate(term)
        ),
        source_notes=tuple(_js_string(n) for n in notes),  # s.source_notes.map(String)
        tickers=SnapshotTickers(
            index_ticker=_str(tickers.get("index_ticker")),
            vol_ticker=_str(tickers.get("vol_ticker")),
            options_proxy=_str(tickers.get("options_proxy")),
        ),
    )


def read_snapshot_json() -> Any:
    """Parse the committed ``snapshot.json`` shipped inside the package (unvalidated).

    Returns a fresh object on every call, so callers may mutate it (e.g. to build a
    malformed variant in a test).
    """
    text = resources.files("eqd_desk.data").joinpath(SNAPSHOT_RESOURCE).read_text("utf-8")
    return json.loads(text)


@cache
def load_snapshot() -> MarketSnapshot:
    """The validated seed snapshot, ready to use across the app.

    Read and validated once on first call, then cached (the result is immutable).
    """
    return validate_snapshot(read_snapshot_json())


def _js_round(x: float) -> int:
    """JavaScript ``Math.round``: nearest integer, ties toward +∞ (2.5 → 3, −2.5 → −2).

    Python's built-in ``round`` rounds ties to even (2.5 → 2), which would snap the seed
    strike to a different level than the TypeScript app.
    """
    f = math.floor(x)
    return f + 1 if x - f >= 0.5 else f


def seed_inputs(s: MarketSnapshot | None = None, strike_step: float = 25) -> BsmInputs:
    """Seed a default Greeks-Lab option from a snapshot.

    An ATM-ish 30-day option: spot from the snapshot, strike rounded to the nearest
    multiple of ``strike_step`` index points (a round listed level), T = 30/365 years,
    and vol / r / q taken from the snapshot (``sigma`` = the 30-day ATM vol).

    Args:
        s: the snapshot to seed from; defaults to the committed seed (:func:`load_snapshot`).
        strike_step: strike grid spacing in index points (> 0).

    Raises:
        ValueError: if ``strike_step`` is not a finite positive number.
    """
    step = _to_js_number(strike_step)  # an int too large for a double is +inf, not a crash
    if not 0 < step < math.inf:
        raise ValueError(f"seed_inputs: strike_step must be > 0 (got {strike_step})")
    snap = load_snapshot() if s is None else s
    return BsmInputs(
        S=snap.spot,
        K=float(_js_round(snap.spot / step) * step),
        T=SEED_T,
        r=snap.r,
        q=snap.q,
        sigma=snap.atm_vol_30d,
    )
