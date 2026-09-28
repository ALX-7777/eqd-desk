"""Public surface for the Phase 3 exotics.

* :mod:`~eqd_desk.engine.exotics.barrier`: single-barrier options (closed form).
* :mod:`~eqd_desk.engine.exotics.digital`: cash-/asset-or-nothing digitals (closed form)
  and their call-spread replication.
* :mod:`~eqd_desk.engine.exotics.varswap`: variance-swap fair strike by static replication.
* :mod:`~eqd_desk.engine.exotics.autocall`: Phoenix autocallable (seeded Monte Carlo).
* :mod:`~eqd_desk.engine.exotics.mc`: seeded RNG re-exports and GBM path simulation.
* :mod:`~eqd_desk.engine.exotics.numeric_greeks`: the shared bump greeks, in desk units.

Example::

    from eqd_desk.engine.exotics import BarrierInputs, barrier_greeks

    g = barrier_greeks(
        BarrierInputs(
            S=91, K=100, T=1, r=0.05, q=0.01, sigma=0.2, type="call", H=90, kind="down-out"
        )
    )
    g.gamma  # large: the knock-out's hedge is hardest next to the barrier
"""

from __future__ import annotations

from eqd_desk.engine.exotics.autocall import (
    DEFAULT_GREEK_PATHS,
    DEFAULT_PATHS,
    DEFAULT_SEED,
    AutocallInputs,
    AutocallResult,
    autocall_greeks,
    price_autocall,
    price_autocall_loop,
)
from eqd_desk.engine.exotics.barrier import (
    BARRIER_KINDS,
    BarrierInputs,
    BarrierKind,
    barrier_greeks,
    barrier_price,
)
from eqd_desk.engine.exotics.digital import (
    DigitalInputs,
    asset_or_nothing_price,
    call_spread_replication,
    cash_or_nothing_price,
    digital_greeks,
)
from eqd_desk.engine.exotics.mc import (
    Mulberry32,
    NormalFn,
    NormalSampler,
    NormalStream,
    iter_normal_blocks,
    make_normal,
    mulberry32,
    normal_block,
    obs_paths_from_normals,
    simulate_obs_path,
    simulate_obs_paths,
    uniform_block,
)
from eqd_desk.engine.exotics.numeric_greeks import ExoticGreeks, PriceFn, numeric_greeks
from eqd_desk.engine.exotics.varswap import (
    StripPoint,
    VarSwapInputs,
    VarSwapResult,
    VolFn,
    price_variance_swap,
)

__all__ = [
    "BARRIER_KINDS",
    "DEFAULT_GREEK_PATHS",
    "DEFAULT_PATHS",
    "DEFAULT_SEED",
    "AutocallInputs",
    "AutocallResult",
    "BarrierInputs",
    "BarrierKind",
    "DigitalInputs",
    "ExoticGreeks",
    "Mulberry32",
    "NormalFn",
    "NormalSampler",
    "NormalStream",
    "PriceFn",
    "StripPoint",
    "VarSwapInputs",
    "VarSwapResult",
    "VolFn",
    "asset_or_nothing_price",
    "autocall_greeks",
    "barrier_greeks",
    "barrier_price",
    "call_spread_replication",
    "cash_or_nothing_price",
    "digital_greeks",
    "iter_normal_blocks",
    "make_normal",
    "mulberry32",
    "normal_block",
    "numeric_greeks",
    "obs_paths_from_normals",
    "price_autocall",
    "price_autocall_loop",
    "price_variance_swap",
    "simulate_obs_path",
    "simulate_obs_paths",
    "uniform_block",
]
