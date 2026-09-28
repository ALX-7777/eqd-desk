"""Monte-Carlo primitives for the path-dependent exotics.

Everything is driven by a SEEDED RNG so prices are reproducible and bump-greeks can reuse
the same draws (common random numbers). Without that, sampling noise swamps the finite
differences.

The generators themselves live in :mod:`eqd_desk.engine.rng` (shared with the market
simulator) and are re-exported here, so the exotics read like the TypeScript engine::

    normal = make_normal(mulberry32(seed))  # TS: makeNormal(mulberry32(seed))
    z = normal()

Scalar (one draw at a time, exactly the TS loop) and vectorised (numpy, whole blocks of
the SAME stream) forms are both available; see :func:`simulate_obs_path` and
:func:`simulate_obs_paths`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator

import numpy as np
from numpy.typing import NDArray

from eqd_desk.engine.rng import Mulberry32, NormalSampler, normal_block, uniform_block

NormalFn = Callable[[], float]
"""A zero-argument standard-normal sampler, e.g. ``make_normal(mulberry32(seed))``."""


def mulberry32(seed: int) -> Mulberry32:
    """TS-named factory for the seeded uniform PRNG: ``mulberry32(seed)()`` ∈ [0, 1).

    Identical to ``Mulberry32(seed)``; kept so ported code reads like the TypeScript.
    """
    return Mulberry32(seed)


def make_normal(rng: Mulberry32) -> NormalSampler:
    """TS-named factory for the standard-normal sampler (Marsaglia polar method) over a
    uniform RNG. Identical to ``NormalSampler(rng)``."""
    return NormalSampler(rng)


def iter_normal_blocks(seed: int, block_size: int) -> Iterator[NDArray[np.float64]]:
    """Yield the ``NormalSampler(Mulberry32(seed))`` stream in consecutive blocks of
    ``block_size`` draws, forever.

    Concatenating the first m blocks gives exactly ``normal_block(seed, m·block_size)``,
    but only ~one block is held in memory at a time. Use it for Monte Carlo too large to
    draw in one go (e.g. 60 000 paths × 200 steps), while still consuming the very same
    draws as the scalar TypeScript loop.

    How: uniforms are addressable by position (see :func:`~eqd_desk.engine.rng.uniform_block`),
    so we walk the uniform stream in chunks of whole (u, v) pairs, keep the accepted polar
    pairs in order and interleave them as (u·m, v·m), which is the scalar sampler's
    return-then-spare order.
    """
    if block_size < 1:
        raise ValueError(f"iter_normal_blocks: block_size must be >= 1 (got {block_size})")
    # Acceptance rate of the polar method is π/4 ≈ 0.785: draw ~one block's worth per refill.
    n_pairs = int(block_size / 2 / 0.78) + 16
    offset = 0
    pending: NDArray[np.float64] = np.empty(0, dtype=np.float64)
    while True:
        while pending.size < block_size:
            u01 = uniform_block(seed, 2 * n_pairs, offset=offset).reshape(n_pairs, 2)
            offset += 2 * n_pairs
            u = 2.0 * u01[:, 0] - 1.0
            v = 2.0 * u01[:, 1] - 1.0
            s = u * u + v * v
            ok = (s < 1.0) & (s != 0.0)
            u, v, s = u[ok], v[ok], s[ok]
            mul = np.sqrt((-2.0 * np.log(s)) / s)
            fresh = np.empty(2 * u.size, dtype=np.float64)
            fresh[0::2] = u * mul
            fresh[1::2] = v * mul
            pending = np.concatenate((pending, fresh))
        yield pending[:block_size].copy()
        pending = pending[block_size:]


class NormalStream:
    """The seeded standard-normal stream ``NormalSampler(Mulberry32(seed))`` as a lazily
    grown array.

    ``stream.first(n)`` returns draws 0 … n−1, generating only the ones not drawn yet (in
    cache-sized chunks, via :func:`iter_normal_blocks`). Use it when the number of draws a
    simulation needs is data-dependent, e.g. an autocallable whose paths stop at early
    redemption: you pay only for what the paths actually reach, not for an upper bound.

    Draws are kept, so every later call returns the very same numbers. That is how bumped
    repricings share one set of draws (common random numbers).
    """

    CHUNK = 16_384
    """Draws generated per refill: large enough to amortise numpy overhead, small enough to
    stay in cache (≈2× faster than drawing hundreds of thousands in one block)."""

    __slots__ = ("_blocks", "_buf", "_n")

    def __init__(self, seed: int) -> None:
        self._blocks = iter_normal_blocks(seed, self.CHUNK)
        self._buf: NDArray[np.float64] = np.empty(0, dtype=np.float64)
        self._n = 0

    def __len__(self) -> int:
        """Number of draws generated so far."""
        return self._n

    def first(self, n: int) -> NDArray[np.float64]:
        """Draws 0 … n−1 of the stream (a read-only view)."""
        if n < 0:
            raise ValueError(f"NormalStream.first: n must be >= 0 (got {n})")
        # Draws always come in whole blocks, so the count and the capacity stay multiples of
        # CHUNK and every block fits exactly.
        need = -(-n // self.CHUNK) * self.CHUNK
        if need > self._buf.size:
            # Grow geometrically so repeated small extensions stay linear overall.
            grown = np.empty(max(need, 2 * self._buf.size), dtype=np.float64)
            grown[: self._n] = self._buf[: self._n]
            self._buf = grown
        while self._n < need:
            self._buf[self._n : self._n + self.CHUNK] = next(self._blocks)
            self._n += self.CHUNK
        view = self._buf[:n]
        view.flags.writeable = False
        return view


def simulate_obs_path(
    S0: float,
    r: float,
    q: float,
    sigma: float,
    dt: float,
    n_steps: int,
    normal: NormalFn,
) -> list[float]:
    """Simulate the underlying at ``n_steps`` equally-spaced dates of length ``dt`` under
    risk-neutral GBM::

        S_{t+dt} = S_t · exp((r − q − σ²/2)·dt + σ·√dt·Z)

    Returns the level at each step, EXCLUDING the start ``S0`` (the exact distribution at
    those dates, fine for discretely observed payoffs). Draws ``n_steps`` normals from
    ``normal``, in step order.

    Units: ``r``, ``q`` continuously compounded; ``sigma`` annualised decimal vol; ``dt``
    in years.
    """
    drift = (r - q - 0.5 * sigma * sigma) * dt
    vol = sigma * math.sqrt(dt)
    s = S0
    out: list[float] = []
    for _ in range(n_steps):
        s = s * math.exp(drift + vol * normal())
        out.append(s)
    return out


def obs_paths_from_normals(
    S0: float, r: float, q: float, sigma: float, dt: float, z: NDArray[np.float64]
) -> NDArray[np.float64]:
    """GBM levels driven by a given matrix of standard normals ``z`` (one row per path, one
    column per step): the vectorised core of :func:`simulate_obs_path`.

    Row p, column k is S0·g₁·…·g_{k+1} with g = exp((r − q − σ²/2)·dt + σ√dt·z). The level
    is built by a running product along each row, multiplied in the same left-to-right
    order as the scalar loop (not by exponentiating a cumulative sum of log-returns), so
    the arithmetic matches the step-by-step recursion. Returns an array shaped like ``z``.
    """
    if z.ndim != 2:
        raise ValueError(f"obs_paths_from_normals: z must be 2-D (paths × steps), got {z.shape}")
    drift = (r - q - 0.5 * sigma * sigma) * dt
    vol = sigma * math.sqrt(dt)
    n_paths, n_steps = z.shape
    levels = np.empty((n_paths, n_steps + 1), dtype=np.float64)
    levels[:, 0] = S0
    levels[:, 1:] = np.exp(drift + vol * z)
    np.multiply.accumulate(levels, axis=1, out=levels)
    return levels[:, 1:]


def simulate_obs_paths(
    S0: float,
    r: float,
    q: float,
    sigma: float,
    dt: float,
    n_steps: int,
    n_paths: int,
    seed: int,
) -> NDArray[np.float64]:
    """Vectorised :func:`simulate_obs_path`: ``n_paths`` GBM paths from one seeded stream.

    Returns an array of shape ``(n_paths, n_steps)`` equal (to the last ulp of ``exp``) to
    calling :func:`simulate_obs_path` ``n_paths`` times in a row with ONE shared
    ``make_normal(mulberry32(seed))``: path p uses draws ``p·n_steps … (p+1)·n_steps − 1``.
    For more draws than fit in memory, feed :func:`iter_normal_blocks` chunks to
    :func:`obs_paths_from_normals` instead.
    """
    if n_steps < 0 or n_paths < 0:
        raise ValueError(
            f"simulate_obs_paths: n_steps and n_paths must be >= 0 (got {n_steps}, {n_paths})"
        )
    z = normal_block(seed, n_paths * n_steps).reshape(n_paths, n_steps)
    return obs_paths_from_normals(S0, r, q, sigma, dt, z)


__all__ = [
    "Mulberry32",
    "NormalFn",
    "NormalSampler",
    "NormalStream",
    "iter_normal_blocks",
    "make_normal",
    "mulberry32",
    "normal_block",
    "obs_paths_from_normals",
    "simulate_obs_path",
    "simulate_obs_paths",
    "uniform_block",
]
