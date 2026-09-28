"""The greeks lab's input panel as data (port of ``web/src/components/InputPanel.tsx``): one
:class:`InputSpec` per BSM input, with the React bounds, steps and header displays, plus the
page's session-state keys and the seed values.

Pure (no Streamlit calls), so the bounds and formats are unit-tested against the React
component; the page turns each spec into a paired slider + field
(:func:`~eqd_desk.app.ui.widgets.number_slider`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from eqd_desk.app.ui.format import fmt_level, fmt_pct, fmt_with_unit, fmt_years_days, js_round
from eqd_desk.app.ui.greeks_lab_curves import X_AXES
from eqd_desk.app.ui.state import level_step
from eqd_desk.content import GREEK_KEYS, GreekKey
from eqd_desk.content.greeks import XAxisKey
from eqd_desk.engine import BsmInputs, OptionType

InputField = Literal["S", "K", "T", "sigma", "r", "q"]
"""A :class:`~eqd_desk.engine.BsmInputs` field, i.e. one input of the panel."""

INPUT_FIELDS: Final[tuple[InputField, ...]] = ("S", "K", "T", "sigma", "r", "q")
"""The inputs in panel order."""

PREFIX: Final = "lab."
"""Prefix of every session-state key owned by the greeks lab."""

TYPE_KEY: Final = "lab.type"
"""Session key of the call/put toggle."""
GREEK_KEY: Final = "lab.greek"
"""Session key of the selected greek (drives the chart, the readout highlight and the card)."""
X_AXIS_KEY: Final = "lab.x"
"""Session key of the chart's x variable (spot / vol / time)."""

DEFAULT_TYPE: Final[OptionType] = "call"
DEFAULT_GREEK: Final[GreekKey] = "delta"
DEFAULT_X_AXIS: Final[XAxisKey] = "S"


def input_key(field: InputField) -> str:
    """Session key holding the value of one input (``"lab.S"``, ``"lab.sigma"``)."""
    return f"{PREFIX}{field}"


@dataclass(frozen=True, slots=True)
class InputSpec:
    """One paired slider + numeric field of the input panel."""

    field: InputField
    label: str
    """Sentence-case label ("Time to expiry")."""
    symbol: str
    """The variable's symbol, shown dim after the label ("T", "σ")."""
    min_value: float
    max_value: float
    step: float
    input_format: str
    """printf format of the numeric field."""
    display: Callable[[float], str]
    """The value with its unit, shown on the right of the header ("6,312.45 USD", "14.60%")."""

    @property
    def key(self) -> str:
        """Session key of the value."""
        return input_key(self.field)


def input_specs(spot: float, currency: str) -> tuple[InputSpec, ...]:
    """The six inputs with ``InputPanel.tsx``'s bounds.

    Spot and strike span ``round(0.6 × spot) … round(1.4 × spot)`` of the SNAPSHOT spot, in
    steps of 1 / 0.5 / 0.1 points by index level; T spans 0.003 … 2 years (steps of about a
    day); σ 2 % … 100 %; r −2 % … 10 %; q 0 … 6 %.
    """

    def level(v: float) -> str:
        return fmt_with_unit(fmt_level(v), currency)

    lo, hi = float(js_round(spot * 0.6)), float(js_round(spot * 1.4))
    step = level_step(spot)
    return (
        InputSpec("S", "Spot", "S", lo, hi, step, "%.2f", level),
        InputSpec("K", "Strike", "K", lo, hi, step, "%.2f", level),
        InputSpec("T", "Time to expiry", "T", 0.003, 2.0, 0.003, "%.4f", fmt_years_days),
        InputSpec("sigma", "Volatility", "σ", 0.02, 1.0, 0.0025, "%.4f", fmt_pct),
        InputSpec("r", "Rate", "r", -0.02, 0.1, 0.0005, "%.4f", fmt_pct),
        InputSpec("q", "Dividend yield", "q", 0.0, 0.06, 0.0005, "%.4f", fmt_pct),
    )


def seed_values(seed: BsmInputs) -> dict[str, float]:
    """Session values of the six inputs for a seed option (``"lab.S" → 6312.45`` …)."""
    return {input_key(f): float(getattr(seed, f)) for f in INPUT_FIELDS}


def inputs_from_values(values: Mapping[str, float]) -> BsmInputs:
    """Build the option from the session values (keys as in :func:`seed_values`)."""
    return BsmInputs(
        S=float(values[input_key("S")]),
        K=float(values[input_key("K")]),
        T=float(values[input_key("T")]),
        r=float(values[input_key("r")]),
        q=float(values[input_key("q")]),
        sigma=float(values[input_key("sigma")]),
    )


def valid_greek(value: object) -> GreekKey:
    """``value`` if it is a greek key, else the default (delta)."""
    for key in GREEK_KEYS:
        if value == key:
            return key
    return DEFAULT_GREEK


def valid_x_axis(value: object) -> XAxisKey:
    """``value`` if it is an x variable, else the default (spot)."""
    for key in X_AXES:
        if value == key:
            return key
    return DEFAULT_X_AXIS
