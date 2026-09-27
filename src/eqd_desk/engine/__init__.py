"""Pure pricing/risk engine: no UI, no I/O, no global state.

The vanilla core is re-exported here; the larger sub-modules are imported explicitly::

    from eqd_desk.engine import BsmInputs, analyze_option
    from eqd_desk.engine.strategy import analyze_position
    from eqd_desk.engine.exotics import barrier_price
    from eqd_desk.engine.sim import MarketSimulator

    a = analyze_option(BsmInputs(S=100, K=100, T=1, r=0.05, q=0, sigma=0.2), "call")
    a.reported.vega  # per 1 vol point
"""

from __future__ import annotations

from eqd_desk.engine.bsm import (
    SIGMA_FLOOR,
    T_FLOOR,
    BsmCore,
    bsm_core,
    call_price,
    forward,
    price,
    put_price,
    validate_inputs,
)
from eqd_desk.engine.greeks import (
    charm,
    color,
    delta,
    gamma,
    raw_greeks,
    rho,
    speed,
    theta,
    vanna,
    vega,
    volga,
)
from eqd_desk.engine.math_utils import SQRT_2PI, norm_cdf, norm_pdf
from eqd_desk.engine.reporting import GREEK_UNITS, GreekUnit, to_reported
from eqd_desk.engine.types import (
    GREEK_NAMES,
    OPTION_TYPES,
    BsmInputs,
    Greeks,
    OptionAnalysis,
    OptionType,
    RawGreeks,
    ReportedGreeks,
)


def analyze_option(inputs: BsmInputs, option_type: OptionType) -> OptionAnalysis:
    """One-call analysis: price + all greeks in both raw and reported units.

    Computes the BSM core once internally.
    """
    raw = raw_greeks(inputs, option_type)
    return OptionAnalysis(inputs=inputs, type=option_type, raw=raw, reported=to_reported(raw))


__all__ = [
    "GREEK_NAMES",
    "GREEK_UNITS",
    "OPTION_TYPES",
    "SIGMA_FLOOR",
    "SQRT_2PI",
    "T_FLOOR",
    "BsmCore",
    "BsmInputs",
    "GreekUnit",
    "Greeks",
    "OptionAnalysis",
    "OptionType",
    "RawGreeks",
    "ReportedGreeks",
    "analyze_option",
    "bsm_core",
    "call_price",
    "charm",
    "color",
    "delta",
    "forward",
    "gamma",
    "norm_cdf",
    "norm_pdf",
    "price",
    "put_price",
    "raw_greeks",
    "rho",
    "speed",
    "theta",
    "to_reported",
    "validate_inputs",
    "vanna",
    "vega",
    "volga",
]
