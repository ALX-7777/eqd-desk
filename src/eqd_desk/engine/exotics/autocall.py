"""Phoenix autocallable: a path-dependent structured note, priced by Monte Carlo.

On each (evenly-spaced) observation date:

* conditional coupon: if S ≥ couponBarrier·S0, pay the period coupon (plus any missed
  coupons, if ``memory``); otherwise the coupon is missed (and remembered);
* early redemption: if S ≥ autocallBarrier·S0 (before maturity), the note redeems at par
  and stops.

At maturity, if not autocalled: par if S ≥ protectionBarrier·S0, else par·(S/S0). The
holder is long the downside below the barrier.

Barriers are ABSOLUTE levels set from the initial fixing S0; greeks bump the current spot
with those levels fixed (the correct risk view). Teaching point: the price is a
path-dependent blend of a yield instrument and a short down-and-in put; early-redemption
probability and "expected life" are as important as the price.

Two implementations consume the SAME seeded draws in the SAME order as the TypeScript
engine (one normal per observation, path after path, stopping at early redemption):

* :func:`price_autocall_loop`: the literal one-path-at-a-time loop. Easiest to read; slow.
* :func:`price_autocall`: the same computation vectorised with numpy (the default). It is
  tested to agree with the loop to rounding, including every autocall/loss count.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from eqd_desk.engine.exotics.mc import NormalStream, make_normal, mulberry32
from eqd_desk.engine.exotics.numeric_greeks import ExoticGreeks, numeric_greeks


@dataclass(frozen=True, slots=True)
class AutocallInputs:
    """A Phoenix autocallable note. Barriers are fractions of the initial fixing ``S0``."""

    S: float
    """Current spot."""
    S0: float
    """Initial fixing level (sets the absolute barriers, > 0). At inception S == S0."""
    sigma: float
    """Volatility (decimal, annualised)."""
    r: float
    """Continuously-compounded risk-free rate (decimal)."""
    q: float
    """Continuously-compounded dividend yield (decimal)."""
    maturity: float
    """Maturity in years (> 0)."""
    n_obs: int
    """Number of equally-spaced observation dates (>= 1); the last one is maturity."""
    coupon_rate: float
    """Per-period coupon as a fraction of notional (e.g. 0.02 = 2% per observation)."""
    autocall_barrier: float
    """Early-redemption barrier as a fraction of S0 (e.g. 1.0)."""
    coupon_barrier: float
    """Conditional-coupon barrier as a fraction of S0 (e.g. 0.7)."""
    protection_barrier: float
    """Capital-protection barrier at maturity as a fraction of S0 (e.g. 0.7)."""
    memory: bool
    """Whether missed coupons accumulate and pay later (snowball / memory)."""
    notional: float
    """Notional (par), e.g. 100."""


@dataclass(frozen=True, slots=True)
class AutocallResult:
    """Monte-Carlo price and diagnostics of an autocallable."""

    price: float
    """Present value (same units as the notional)."""
    stderr: float
    """Monte-Carlo standard error of the price."""
    prob_autocall: float
    """Probability of early redemption (autocalled before maturity)."""
    prob_capital_loss: float
    """Probability of capital loss at maturity."""
    expected_life: float
    """Expected time to redemption (years)."""


DEFAULT_PATHS = 20_000
"""Monte-Carlo paths for a price."""
DEFAULT_GREEK_PATHS = 40_000
"""Monte-Carlo paths for the bump greeks (more, because finite differences amplify noise)."""
DEFAULT_SEED = 0x9E3779B1
"""Default RNG seed (the golden-ratio constant), shared with the TypeScript engine."""


def _validate(i: AutocallInputs, paths: int) -> None:
    """Reject inputs the pricer cannot handle.

    The TypeScript checks none of these; here they are all explicit errors. What it does
    instead:

    - ``paths = 0``: 0/0, so every output is NaN.
    - ``n_obs = 0``: no observation dates, so nothing is paid and the price is 0. A
      negative ``n_obs`` throws (``new Array(-1)``).
    - ``maturity = 0``: zero-length periods, so the spot never moves and every path pays
      the same deterministic, meaningless amount. A negative maturity gives NaN
      (σ·√dt of a negative dt).
    - ``S0 <= 0``: every barrier sits at or below 0, so every path collects the first
      coupon and is called on the first date (redeems at maturity if ``n_obs = 1``).

    Raises:
        ValueError: on ``paths < 1``, ``n_obs < 1``, ``maturity <= 0`` or ``S0 <= 0``.
    """
    if paths < 1:
        raise ValueError(f"autocall: paths must be >= 1 (got {paths})")
    if i.n_obs < 1:
        raise ValueError(f"autocall: n_obs must be >= 1 (got {i.n_obs})")
    if not i.maturity > 0:
        raise ValueError(f"autocall: maturity must be > 0 (got {i.maturity})")
    if not i.S0 > 0:
        raise ValueError(f"autocall: initial fixing S0 must be > 0 (got {i.S0})")


def _result(
    total: float, total2: float, n_auto: int, n_loss: int, life_sum: float, paths: int
) -> AutocallResult:
    """Turn the path sums into the price and diagnostics.

    stderr = √(Var[pv] / paths), with Var[pv] = E[pv²] − E[pv]² (floored at 0 against
    rounding when every path pays the same).
    """
    price = total / paths
    variance = total2 / paths - price * price
    return AutocallResult(
        price=price,
        stderr=math.sqrt(max(variance, 0.0) / paths),
        prob_autocall=n_auto / paths,
        prob_capital_loss=n_loss / paths,
        expected_life=life_sum / paths,
    )


def price_autocall_loop(
    i: AutocallInputs, paths: int = DEFAULT_PATHS, seed: int = DEFAULT_SEED
) -> AutocallResult:
    """Price a Phoenix autocallable by Monte Carlo, one path at a time (seeded, so
    reproducible).

    This is the literal port of the TypeScript loop and the READABLE reference for
    :func:`price_autocall` (several times faster, same numbers). Each path
    steps the GBM once per observation date, S ← S·exp((r − q − σ²/2)·dt + σ·√dt·Z), and
    stops at early redemption, so the number of draws a path consumes depends on the path.

    Raises:
        ValueError: see :func:`_validate`.
    """
    _validate(i, paths)
    normal = make_normal(mulberry32(seed))
    n = i.n_obs
    dt = i.maturity / n
    drift = (i.r - i.q - 0.5 * i.sigma * i.sigma) * dt
    vol = i.sigma * math.sqrt(dt)
    AB = i.autocall_barrier * i.S0
    CB = i.coupon_barrier * i.S0
    PB = i.protection_barrier * i.S0
    N = i.notional

    # Pre-compute discount factors at each observation date.
    df = [math.exp(-i.r * k * dt) for k in range(1, n + 1)]

    total = 0.0
    total2 = 0.0
    n_auto = 0
    n_loss = 0
    life_sum = 0.0

    for _ in range(paths):
        s = i.S
        missed = 0
        pv = 0.0
        life = i.maturity

        for k in range(1, n + 1):
            s = s * math.exp(drift + vol * normal())
            d = df[k - 1]

            # conditional coupon (with optional memory)
            if s >= CB:
                periods = 1 + missed if i.memory else 1
                pv += N * i.coupon_rate * periods * d
                missed = 0
            else:
                missed += 1

            # early redemption (before maturity)
            if k < n and s >= AB:
                pv += N * d
                n_auto += 1
                life = k * dt
                break

            # maturity redemption
            if k == n:
                if s >= PB:
                    pv += N * d
                else:
                    pv += N * (s / i.S0) * d
                    n_loss += 1
                life = i.maturity

        total += pv
        total2 += pv * pv
        life_sum += life

    return _result(total, total2, n_auto, n_loss, life_sum, paths)


class _GrowthFactors:
    """Per-step GBM growth factors g = exp((r − q − σ²/2)·dt + σ√dt·Z) over a seeded
    :class:`~eqd_desk.engine.exotics.mc.NormalStream`, computed only as far as the paths
    actually reach (most autocallable paths stop after a few observations).

    ``values`` is a plain Python list, extended IN PLACE by :meth:`ensure`: indexing a list
    in a scalar loop is several times faster than indexing a numpy array.
    """

    __slots__ = ("_drift", "_stream", "_vol", "values")

    def __init__(self, stream: NormalStream, drift: float, vol: float) -> None:
        self._stream = stream
        self._drift = drift
        self._vol = vol
        self.values: list[float] = []

    def ensure(self, n: int) -> None:
        """Make ``values`` hold at least the first ``n`` growth factors."""
        have = len(self.values)
        if n <= have:
            return
        target = max(n, 2 * have, NormalStream.CHUNK)  # geometric growth: few numpy passes
        z = self._stream.first(target)[have:]
        self.values.extend(np.exp(self._drift + self._vol * z).tolist())


def _path_starts(growth: _GrowthFactors, S: float, AB: float, n_obs: int, paths: int) -> list[int]:
    """Index of each path's first draw in the shared stream of growth factors.

    A path consumes one draw per observation until it autocalls, so path p starts exactly
    where path p−1 stopped: a data-dependent chain that has to be walked in order. The walk
    only tracks the level against the autocall barrier (coupons and payoffs are done
    afterwards, vectorised), which keeps this scalar loop tight. Levels are multiplied in
    the same order as the path loop (S·g₁·g₂·…), so the walk sees exactly the levels the
    path sees and stops on exactly the same draw.
    """
    values = growth.values  # the same list object that growth.ensure() extends
    starts = [0] * paths
    ptr = 0
    for p in range(paths):
        if ptr + n_obs > len(values):
            growth.ensure(ptr + n_obs)  # enough draws for this path to reach maturity
        starts[p] = ptr
        s = S
        last_early = ptr + n_obs - 1  # draws on observation dates before maturity
        while ptr < last_early:
            s *= values[ptr]
            ptr += 1
            if s >= AB:
                break  # autocalled: the next path starts right after this draw
        else:
            ptr += 1  # survived every early observation: one more draw for maturity
    return starts


def _price_from_stream(i: AutocallInputs, paths: int, stream: NormalStream) -> AutocallResult:
    """Vectorised pricer over a seeded normal stream. See :func:`price_autocall`."""
    n = i.n_obs
    dt = i.maturity / n
    drift = (i.r - i.q - 0.5 * i.sigma * i.sigma) * dt
    vol = i.sigma * math.sqrt(dt)
    AB = i.autocall_barrier * i.S0
    CB = i.coupon_barrier * i.S0
    PB = i.protection_barrier * i.S0
    N = i.notional
    df = [math.exp(-i.r * k * dt) for k in range(1, n + 1)]

    growth = _GrowthFactors(stream, drift, vol)
    starts = np.asarray(_path_starts(growth, i.S, AB, n, paths), dtype=np.intp)
    # Row p = the n draws path p would use if it survived to maturity (trailing ones unused;
    # the walk made sure the stream reaches the last path's maturity draw).
    g = np.asarray(growth.values, dtype=np.float64)[starts[:, np.newaxis] + np.arange(n)]

    s = np.full(paths, i.S, dtype=np.float64)
    pv = np.zeros(paths, dtype=np.float64)
    missed = np.zeros(paths, dtype=np.float64)
    life = np.full(paths, i.maturity, dtype=np.float64)
    alive = np.ones(paths, dtype=np.bool_)
    n_auto = 0
    n_loss = 0

    for k in range(1, n + 1):
        s = s * g[:, k - 1]
        d = df[k - 1]

        # conditional coupon (with optional memory)
        pays = alive & (s >= CB)
        periods = 1.0 + missed[pays] if i.memory else 1.0
        pv[pays] += N * i.coupon_rate * periods * d
        missed[pays] = 0.0
        missed[alive & ~pays] += 1.0

        if k < n:
            # early redemption (before maturity)
            called = alive & (s >= AB)
            pv[called] += N * d
            life[called] = k * dt
            n_auto += int(np.count_nonzero(called))
            alive &= ~called
        else:
            # maturity redemption (life stays = maturity)
            protected = alive & (s >= PB)
            lost = alive & ~protected
            pv[protected] += N * d
            pv[lost] += N * (s[lost] / i.S0) * d
            n_loss += int(np.count_nonzero(lost))

    return _result(
        float(pv.sum()), float((pv * pv).sum()), n_auto, n_loss, float(life.sum()), paths
    )


def price_autocall(
    i: AutocallInputs, paths: int = DEFAULT_PATHS, seed: int = DEFAULT_SEED
) -> AutocallResult:
    """Price a Phoenix autocallable by Monte Carlo (seeded, so reproducible), vectorised.

    Same model, draws and payoff as :func:`price_autocall_loop` (read that one first):

    1. walk the paths through the seeded normal stream to find where each one starts
       (:func:`_path_starts`, a tight scalar loop), because early redemption makes the
       number of draws per path data-dependent. Draws are generated lazily, in numpy
       chunks, only as far as the paths reach;
    2. run the observation dates for all paths at once, with boolean masks for "still
       alive", "pays the coupon", "autocalls" and "loses capital".

    Path sums use numpy's pairwise summation, so results can differ from the loop (and
    from the TypeScript) in the last few ulps; every count is identical.

    Raises:
        ValueError: see :func:`_validate`.
    """
    _validate(i, paths)
    return _price_from_stream(i, paths, NormalStream(seed))


def autocall_greeks(
    i: AutocallInputs, paths: int = DEFAULT_GREEK_PATHS, seed: int = DEFAULT_SEED
) -> ExoticGreeks:
    """Autocallable greeks by bumping (S, σ, maturity, r), with common random numbers
    (fixed seed) so the finite differences are stable.

    MC greeks are approximate (gamma especially is noisy) but delta and vega read clearly.
    All nine bumped prices read one shared :class:`~eqd_desk.engine.exotics.mc.NormalStream`,
    which is exactly what re-seeding each price with ``seed`` would give, without drawing
    the normals nine times.

    Raises:
        ValueError: see :func:`_validate`.
    """
    _validate(i, paths)
    stream = NormalStream(seed)

    def px(S: float, sigma: float, T: float, r: float) -> float:
        bumped = replace(i, S=S, sigma=sigma, maturity=T, r=r)
        return _price_from_stream(bumped, paths, stream).price

    return numeric_greeks(px, i.S, i.sigma, i.maturity, i.r)
