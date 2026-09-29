"""The greeks lab's numbers that are not a single engine call: the greek sweeps behind the
main chart, the payoff grid, and the premium split (port of ``PlotsPanel.tsx`` and
``GreeksReadout.tsx``).

Pure functions (engine in, DataFrames and floats out), no Streamlit: the page caches them
with ``st.cache_data``. Every sweep uses the React resolution and the React arithmetic for
the grid (:func:`~eqd_desk.app.ui.charts.sweep_x`), so each point is the same engine call,
on the same inputs, as the React app's. The vol and time sweeps span their inputs' own
bounds, so the "current" marker is on the chart for any value the input accepts (React
sweeps vol over 0.02 … 0.80 only, and loses the marker when σ is set above 80 %):

======== ========================= ====================================================
x axis   range                     note
======== ========================= ====================================================
``S``    0.6 × spot … 1.4 × spot   ``spot`` = the SNAPSHOT spot, not the S slider, so
                                   the x range stays put while S is dragged
``sigma`` 0.02 … 1.00              implied vol as a decimal: the σ input's own bounds
``T``    0.003 … 2 years           the T slider's own bounds
======== ========================= ====================================================

Each sweep point is ``analyze_option(inputs with that one field replaced)``; every other
input is held at its current value.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

import pandas as pd

from eqd_desk.app.ui.bounds import SPOT_RANGE_FACTORS, T_BOUNDS, Bounds
from eqd_desk.app.ui.charts import SPOT_AXIS_FORMAT, level_text, sweep_x
from eqd_desk.app.ui.format import EM_DASH, to_fixed, to_precision
from eqd_desk.app.ui.readout import ReadoutRow, group_row
from eqd_desk.content import GREEK_KEYS
from eqd_desk.content.greeks import GREEK_GROUPS, XAxisKey
from eqd_desk.engine import GREEK_UNITS, BsmInputs, OptionAnalysis, OptionType, analyze_option

N_POINTS: Final = 100
"""Sweep resolution: ``N_POINTS + 1`` evaluations per curve (React ``PlotsPanel`` ``N``)."""

X_AXES: Final[tuple[XAxisKey, ...]] = ("S", "sigma", "T")
"""The variables a greek can be swept against, in the order of the x-axis control."""

X_AXIS_CHOICES: Final[Mapping[XAxisKey, str]] = MappingProxyType(
    {"S": "Spot", "sigma": "Vol", "T": "Time"}
)
"""Labels of the x-axis segmented control (``PlotsPanel.tsx`` buttons)."""

X_AXIS_LABELS: Final[Mapping[XAxisKey, str]] = MappingProxyType(
    {"S": "Spot", "sigma": "Implied vol", "T": "Time to expiry (yrs)"}
)
"""Axis title of each x variable (``PlotsPanel.tsx`` ``X_META[…].label``); lower-cased it
completes the chart title ("Delta vs spot")."""

X_AXIS_FORMATS: Final[Mapping[XAxisKey, str]] = MappingProxyType(
    {"S": SPOT_AXIS_FORMAT, "sigma": ".0%", "T": ".2f"}
)
"""d3-format of the x-axis ticks: whole index points (the shared spot format, ``",.0f"``),
whole vol percent, years to 2 dp (the React ``X_META[…].tick`` formats; spot gains a
thousands separator)."""

SIGMA_BOUNDS: Final = Bounds(0.02, 1.0, 0.0025)
"""Implied vol σ (decimal): 2 % … 100 %, in steps of a quarter vol point. The bounds of the
lab's σ input (:func:`~eqd_desk.app.ui.greeks_lab_inputs.input_specs`) AND of the sweep
against vol (:data:`SIGMA_RANGE`), one definition so the two cannot drift apart."""

SIGMA_RANGE: Final = (SIGMA_BOUNDS.lo, SIGMA_BOUNDS.hi)
"""Implied-vol sweep range (decimal): the σ input's bounds (:data:`SIGMA_BOUNDS`), so the
"current vol" marker is drawn for every σ the input accepts."""

T_RANGE: Final = (T_BOUNDS.lo, T_BOUNDS.hi)
"""Time-to-expiry sweep range (years): the T slider's bounds
(:data:`~eqd_desk.app.ui.bounds.T_BOUNDS`). The spot sweep (and the payoff chart) spans
:data:`~eqd_desk.app.ui.bounds.SPOT_RANGE_FACTORS` × the snapshot spot."""


def x_range(x_axis: XAxisKey, spot: float) -> tuple[float, float]:
    """``(lo, hi)`` of the sweep against ``x_axis`` (``spot`` is the snapshot spot)."""
    if x_axis == "S":
        return spot * SPOT_RANGE_FACTORS[0], spot * SPOT_RANGE_FACTORS[1]
    if x_axis == "sigma":
        return SIGMA_RANGE
    return T_RANGE


def x_tick(x_axis: XAxisKey, value: float) -> str:
    """The x value as the React tooltip prints it (``X_META[…].tick``): spot to whole points
    (``"6312"``), vol to whole percent (``"15%"``), time to 2 dp (``"0.08"``)."""
    if x_axis == "S":
        return level_text(value)
    if x_axis == "sigma":
        return f"{to_fixed(value * 100, 0)}%"
    return to_fixed(value, 2)


def current_x(inputs: BsmInputs, x_axis: XAxisKey) -> float:
    """The current value of the swept variable (where the "current" marker is drawn)."""
    value: float = getattr(inputs, x_axis)
    return value


def greek_sweep(
    inputs: BsmInputs,
    option_type: OptionType,
    x_axis: XAxisKey,
    spot: float,
    n: int = N_POINTS,
) -> pd.DataFrame:
    """Price and every greek, in REPORTED desk units, swept against ``x_axis``.

    Args:
        inputs: the current option (every field but ``x_axis`` is held fixed).
        option_type: ``"call"`` or ``"put"``.
        x_axis: the variable to sweep (``"S"``, ``"sigma"`` or ``"T"``).
        spot: the snapshot spot, which sets the spot range.
        n: number of intervals (``n + 1`` points).

    Returns:
        A frame with column ``x`` and one column per :data:`~eqd_desk.content.GREEK_KEYS`
        (``price``, ``delta``, …, ``color``), one row per point. Sweeping every greek at
        once means picking another greek needs no recomputation.
    """
    lo, hi = x_range(x_axis, spot)
    xs = sweep_x(lo, hi, n)
    rows = [
        analyze_option(dataclasses.replace(inputs, **{x_axis: x}), option_type).reported.as_dict()
        for x in xs
    ]
    frame = pd.DataFrame({"x": xs})
    for key in GREEK_KEYS:
        frame[key] = [row[key] for row in rows]
    return frame


def intrinsic_value(S: float, K: float, option_type: OptionType) -> float:
    """Value at expiry (intrinsic): ``max(S − K, 0)`` for a call, ``max(K − S, 0)`` for a put."""
    return max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)


def payoff_curve(
    inputs: BsmInputs,
    option_type: OptionType,
    spot: float,
    n: int = N_POINTS,
) -> pd.DataFrame:
    """The payoff chart's data over 0.6 × … 1.4 × the snapshot spot.

    Returns:
        A frame with ``spot`` (the x grid), ``expiry`` (intrinsic value at expiry, the solid
        curve) and ``now`` (today's premium at that spot, everything else unchanged, the thin
        curve). ``now − expiry`` is the time value.
    """
    lo, hi = x_range("S", spot)
    xs = sweep_x(lo, hi, n)
    return pd.DataFrame(
        {
            "spot": xs,
            "expiry": [intrinsic_value(x, inputs.K, option_type) for x in xs],
            "now": [
                analyze_option(dataclasses.replace(inputs, S=x), option_type).reported.price
                for x in xs
            ],
        }
    )


@dataclasses.dataclass(frozen=True, slots=True)
class PremiumSplit:
    """The premium and its two parts (the readout's hero line)."""

    premium: float
    """Option value now (currency units)."""
    intrinsic: float
    """What exercising now would pay: ``max(S − K, 0)`` (call) / ``max(K − S, 0)`` (put)."""
    time_value: float
    """``premium − intrinsic``: what optionality (vol × time) is worth. It can be negative
    for a deep in-the-money put (or a call on a high-dividend index): the forward, not
    spot, is what the option is really struck against."""


def premium_split(analysis: OptionAnalysis) -> PremiumSplit:
    """Premium, intrinsic and time value of an analysed option (``GreeksReadout.tsx``)."""
    i = analysis.inputs
    intrinsic = intrinsic_value(i.S, i.K, analysis.type)
    premium = analysis.reported.price
    return PremiumSplit(premium, intrinsic, premium - intrinsic)


def raw_scale_text(key: str) -> str:
    """How the desk number is obtained from the raw partial: ``"desk = raw ÷100"``, or
    ``"desk = raw"`` when no rescaling applies (from :data:`~eqd_desk.engine.GREEK_UNITS`)."""
    note = GREEK_UNITS[key].scale_note
    return "desk = raw" if note == "raw" else f"desk = raw {note}"


def raw_partial_rows(analysis: OptionAnalysis, *, selected: str | None = None) -> list[ReadoutRow]:
    """The raw partial derivatives (before desk scaling), grouped like the readout, each to 6
    significant figures (what the React readout shows on hover, ``raw ∂: <toPrecision(6)>``),
    with how the desk number derives from it."""
    raw = analysis.raw.as_dict()
    rows: list[ReadoutRow] = []
    for group in GREEK_GROUPS:
        rows.append(group_row(group.title))
        rows.extend(
            ReadoutRow(
                GREEK_UNITS[k].label,
                raw[k],
                text=to_precision(raw[k], 6) if math.isfinite(raw[k]) else EM_DASH,
                unit=raw_scale_text(k),
                selected=k == selected,
            )
            for k in group.keys
        )
    return rows


__all__ = [
    "N_POINTS",
    "SIGMA_BOUNDS",
    "SIGMA_RANGE",
    "T_RANGE",
    "X_AXES",
    "X_AXIS_CHOICES",
    "X_AXIS_FORMATS",
    "X_AXIS_LABELS",
    "PremiumSplit",
    "current_x",
    "greek_sweep",
    "intrinsic_value",
    "payoff_curve",
    "premium_split",
    "raw_partial_rows",
    "raw_scale_text",
    "x_range",
    "x_tick",
]
