"""Simulated market for the trading simulator.

A GBM spot path with the ATM vol moving AGAINST spot (the leverage effect) plus mild
mean-reversion and proportional (lognormal-style) vol-of-vol noise. The book is priced off
this single ATM vol (a flat surface that shifts, optionally tilted by a quadratic skew),
which keeps the P&L attribution clean while still letting spot and vol co-move so vanna
bites.

The step is written behind a small interface (:class:`MarketProcess`) so a Heston-style
spot+vol process can drop in later without touching the rest of the simulator.

Example::

    from eqd_desk.engine.sim import MarketSimulator, MarketState

    sim = MarketSimulator(MarketState(t=0, spot=6312.45, atm_vol=0.146, r=0.043, q=0.013))
    res = sim.next()  # one trading day (dt = 1/252)
    res.state.spot, res.d_vol
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from eqd_desk.engine.rng import Mulberry32, NormalSampler

NormalFn = Callable[[], float]
"""A zero-argument standard-normal sampler, e.g. ``NormalSampler(Mulberry32(seed))``."""

VOL_FLOOR: Final = 0.05
"""Lowest ATM vol (decimal) the simulated market (and the skew surface) can reach."""

VOL_CAP: Final = 1.2
"""Highest ATM vol (decimal) the simulated market (and the skew surface) can reach."""


@dataclass(frozen=True, slots=True)
class MarketState:
    """The market at one instant of the simulation clock.

    Frozen: every step returns a NEW state, so a history of states is safe to keep.
    """

    t: float
    """Elapsed time in years (the clock)."""
    spot: float
    """Index level (price units)."""
    atm_vol: float
    """ATM implied vol (at the forward, decimal); the level the whole surface hangs off."""
    r: float
    """Continuously-compounded risk-free rate (decimal)."""
    q: float
    """Continuously-compounded dividend yield (decimal)."""
    skew_slope: float | None = None
    """Skew slope in log-moneyness (≤ 0 for equity skew). ``None`` ⇒ flat surface."""
    skew_curv: float | None = None
    """Smile curvature in log-moneyness. ``None`` ⇒ flat surface."""


def vol_for_strike(market: MarketState, K: float, T: float) -> float:
    """Implied vol for strike ``K`` and expiry ``T`` (years) under the current market.

    A quadratic skew in log-moneyness around the forward, anchored to the ATM level::

        F = S·e^((r − q)·max(T, 1e-6))
        k = ln(K / F)
        σ(K) = clamp(atmVol + slope·k + curv·k², VOL_FLOOR, VOL_CAP)

    The ATM level moves with spot (leverage), and the whole surface shifts with it, so a
    strike's vol responds both to the ATM move and to its moneyness changing. Flat (just
    the clamped ATM vol) when the skew params are absent or both zero, which keeps the
    simpler tests untouched.
    """
    slope = market.skew_slope if market.skew_slope is not None else 0.0
    curv = market.skew_curv if market.skew_curv is not None else 0.0
    if slope == 0 and curv == 0:
        return min(VOL_CAP, max(VOL_FLOOR, market.atm_vol))
    F = market.spot * math.exp((market.r - market.q) * max(T, 1e-6))
    k = math.log(K / F)
    return min(VOL_CAP, max(VOL_FLOOR, market.atm_vol + slope * k + curv * k * k))


@dataclass(frozen=True, slots=True)
class SimParams:
    """Parameters of the simulated spot + ATM-vol process."""

    drift: float
    """Real-world spot drift (annualised; default 0: no directional edge)."""
    leverage: float
    """Leverage: dVol ≈ −leverage·(dS/S). ~1 ⇒ a −1% move lifts vol ~1 point."""
    vol_mean_rev: float
    """Mean-reversion speed (per year) of vol back to ``base_vol``."""
    base_vol: float
    """Long-run vol level (decimal)."""
    vol_of_vol: float
    """Vol-of-vol: annualised volatility of the idiosyncratic vol noise, PROPORTIONAL to the
    vol level (0.6 ⇒ the ATM vol's own noise is 60%/yr of itself: ≈0.55 vol pt/day at 14.6%)."""
    dt: float
    """Step size in years (1/252 ≈ one trading day)."""


@dataclass(frozen=True, slots=True)
class StepResult:
    """The outcome of one market step."""

    state: MarketState
    """The market after the step."""
    dS: float
    """Change in spot over the step (price units)."""
    d_vol: float
    """Change in ATM vol over the step (decimal)."""
    spot_return: float
    """Spot return over the step (dS/S)."""


DEFAULT_SIM_PARAMS: Final = SimParams(
    drift=0.0,
    leverage=1.0,
    vol_mean_rev=3.0,
    base_vol=0.15,
    vol_of_vol=0.6,
    dt=1 / 252,
)
"""Default process: no drift, leverage 1, vol mean-reverting to 15% with 60% vol-of-vol,
one trading day per step. At a 14.6% ATM vol that is ≈0.9 vol pt/day of leverage-driven move
plus ≈0.55 pt/day of noise: a daily vol change of ≈1.1 pt with a spot/vol correlation of about
−0.85 (real ^GSPC/^VIX 2018–26: median |ΔVIX| 0.75 pt, correlation −0.79)."""


class MarketProcess(Protocol):
    """A pluggable one-step market process. GBM + leverage is the default."""

    def step(self, state: MarketState, params: SimParams, normal: NormalFn) -> StepResult:
        """Advance ``state`` by one step of ``params.dt``, drawing normals from ``normal``."""
        ...


class GbmLeverageProcess:
    """GBM spot with leverage-linked vol.

    Consumes exactly TWO normals per step, in this order: z1 drives spot, z2 drives the
    idiosyncratic vol noise::

        ret     = (μ − σ²/2)·dt + σ·√dt·z1          σ = the current ATM vol
        S'      = S·e^ret
        R       = S'/S − 1                          the step's spot return
        σ'      = σ − leverage·R + κ·(σ̄ − σ)·dt + ν·σ·√dt·z2
        σ'      = clamp(σ', VOL_FLOOR, VOL_CAP)

    The noise term is PROPORTIONAL to σ (an Euler step of dσ = … + ν·σ·dW), so ν is a true
    "vol of vol": a calm 12% market jitters less, in vol points, than a stressed 40% one, and
    the leverage term (−leverage·R) dominates the daily vol change, so spot and vol visibly
    move against each other.

    Stateless: the shared instance :data:`gbm_leverage_process` is all you need.
    """

    __slots__ = ()

    def step(self, state: MarketState, params: SimParams, normal: NormalFn) -> StepResult:
        """One GBM + leverage step (see the class docstring)."""
        z1 = normal()
        z2 = normal()
        sigma = state.atm_vol
        ret = (params.drift - 0.5 * sigma * sigma) * params.dt + sigma * math.sqrt(params.dt) * z1
        new_spot = state.spot * math.exp(ret)
        spot_return = new_spot / state.spot - 1

        new_vol = (
            state.atm_vol
            - params.leverage * spot_return
            + params.vol_mean_rev * (params.base_vol - state.atm_vol) * params.dt
            + params.vol_of_vol * state.atm_vol * math.sqrt(params.dt) * z2
        )
        new_vol = min(VOL_CAP, max(VOL_FLOOR, new_vol))

        return StepResult(
            state=MarketState(
                t=state.t + params.dt,
                spot=new_spot,
                atm_vol=new_vol,
                r=state.r,
                q=state.q,
                skew_slope=state.skew_slope,
                skew_curv=state.skew_curv,
            ),
            dS=new_spot - state.spot,
            d_vol=new_vol - state.atm_vol,
            spot_return=spot_return,
        )


gbm_leverage_process: Final = GbmLeverageProcess()
"""The default :class:`MarketProcess` (TS: ``gbmLeverageProcess``)."""


class MarketSimulator:
    """A small driver that owns a seeded RNG so a whole session is reproducible.

    Call :meth:`next` to advance one step. The only mutable piece of the simulator: it
    holds the current :attr:`state` and the normal stream (``NormalSampler(Mulberry32(seed))``,
    the same stream as the TS ``makeNormal(mulberry32(seed))``).
    """

    state: MarketState
    """The current market (replaced, never mutated, on each step)."""

    __slots__ = ("_normal", "_params", "_process", "state")

    def __init__(
        self,
        initial: MarketState,
        params: SimParams = DEFAULT_SIM_PARAMS,
        seed: int = 0x5EED,
        process: MarketProcess = gbm_leverage_process,
    ) -> None:
        self.state = initial
        self._params = params
        self._process = process
        self._normal: NormalFn = NormalSampler(Mulberry32(seed))

    def next(self) -> StepResult:
        """Advance one step and return it (the new state is also kept in :attr:`state`)."""
        res = self._process.step(self.state, self._params, self._normal)
        self.state = res.state
        return res


def realised_vol(spots: Sequence[float], dt: float) -> float | None:
    """Annualised realised vol of a spot path, from its log returns.

    With n = len(spots) − 1 log returns lrᵢ = ln(Sᵢ / Sᵢ₋₁)::

        σ_realised = √( max(mean(lr²) − mean(lr)², 0) / dt )

    (the population variance of the returns, annualised by the step ``dt`` in years).
    Returns ``None`` if the path is too short (fewer than 3 points).
    """
    if len(spots) < 3:
        return None
    total = 0.0
    total_sq = 0.0
    n = 0
    for i in range(1, len(spots)):
        lr = math.log(spots[i] / spots[i - 1])
        total += lr
        total_sq += lr * lr
        n += 1
    mean = total / n
    variance = total_sq / n - mean * mean
    return math.sqrt(max(variance, 0.0) / dt)


__all__ = [
    "DEFAULT_SIM_PARAMS",
    "VOL_CAP",
    "VOL_FLOOR",
    "GbmLeverageProcess",
    "MarketProcess",
    "MarketSimulator",
    "MarketState",
    "NormalFn",
    "SimParams",
    "StepResult",
    "gbm_leverage_process",
    "realised_vol",
    "vol_for_strike",
]
