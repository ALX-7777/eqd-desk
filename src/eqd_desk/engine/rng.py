"""Seeded random numbers shared by the Monte-Carlo exotics and the market simulator.

Everything random in the engine is driven by a SEEDED generator so prices and simulated
sessions are reproducible, and bump-greeks can reuse the same draws (common random
numbers). Without that, sampling noise swamps the finite differences.

The generator is ``mulberry32`` and the normal sampler is Marsaglia's polar method, both
ported BIT-EXACTLY from the TypeScript engine (``web/src/engine/exotics/mc.ts``). The same
seed therefore yields the same uniform stream in both implementations, which is what lets
``tests/parity`` compare Monte-Carlo prices and simulated paths against golden values
exported from the TS engine. (Normals can differ in the last ulp because ``log``/``exp``
come from different maths libraries, far below any tolerance that matters.)

Two forms are provided:

* :class:`Mulberry32` / :class:`NormalSampler`: scalar and stateful, for code that
  consumes draws one at a time (the step-by-step simulator, RFQ generation).
* :func:`uniform_block` / :func:`normal_block`: vectorised with numpy for Monte-Carlo.
  They return exactly the first ``n`` values of the corresponding scalar stream (see
  ``tests/engine/test_rng.py``).
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

_M32 = 0xFFFFFFFF
_GOLDEN_GAMMA = 0x6D2B79F5
_TWO_POW_32 = 4294967296.0


class Mulberry32:
    """mulberry32: a small, fast, well-distributed seeded PRNG returning floats in [0, 1).

    It is counter-based: the n-th call hashes ``seed + n·0x6D2B79F5 (mod 2³²)``. That is
    what makes the vectorised :func:`uniform_block` possible.
    """

    __slots__ = ("_a",)

    def __init__(self, seed: int) -> None:
        # JS: `seed >>> 0` (ToUint32). Python's & gives the same two's-complement wrap.
        self._a = seed & _M32

    def __call__(self) -> float:
        """Next uniform draw in [0, 1)."""
        a = (self._a + _GOLDEN_GAMMA) & _M32
        self._a = a
        # Math.imul keeps the low 32 bits of the product; bit patterns are identical
        # whether JS treats the operands as signed or we treat them as unsigned.
        t = ((a ^ (a >> 15)) * (a | 1)) & _M32
        t = ((t + (((t ^ (t >> 7)) * (t | 61)) & _M32)) & _M32) ^ t
        return ((t ^ (t >> 14)) & _M32) / _TWO_POW_32


class NormalSampler:
    """Standard-normal sampler (Marsaglia polar method) over a uniform RNG.

    Each accepted pair (u, v) yields two normals: ``u·m`` is returned now and ``v·m`` is
    kept as the spare for the next call, where m = √(−2·ln s / s) and s = u² + v².
    """

    __slots__ = ("_rng", "_spare")

    def __init__(self, rng: Mulberry32) -> None:
        self._rng = rng
        self._spare: float | None = None

    def __call__(self) -> float:
        """Next standard-normal draw."""
        if self._spare is not None:
            v = self._spare
            self._spare = None
            return v
        while True:
            u = 2.0 * self._rng() - 1.0
            v = 2.0 * self._rng() - 1.0
            s = u * u + v * v
            if 0.0 < s < 1.0:
                break
        mul = math.sqrt((-2.0 * math.log(s)) / s)
        self._spare = v * mul
        return u * mul


def uniform_block(seed: int, n: int, *, offset: int = 0) -> NDArray[np.float64]:
    """Uniform draws number ``offset+1 … offset+n`` of ``Mulberry32(seed)``, vectorised.

    ``uniform_block(seed, n)`` equals ``[rng() for _ in range(n)]`` for a fresh
    ``rng = Mulberry32(seed)``, bit for bit.
    """
    if n < 0 or offset < 0:
        raise ValueError(f"uniform_block: n and offset must be >= 0 (got n={n}, offset={offset})")
    counter = np.arange(offset + 1, offset + n + 1, dtype=np.uint64)
    m32 = np.uint64(_M32)
    # Products of two values < 2³² fit exactly in uint64; mask back to 32 bits.
    a = (np.uint64(seed & _M32) + counter * np.uint64(_GOLDEN_GAMMA)) & m32
    t = ((a ^ (a >> np.uint64(15))) * (a | np.uint64(1))) & m32
    t = ((t + (((t ^ (t >> np.uint64(7))) * (t | np.uint64(61))) & m32)) & m32) ^ t
    out = (t ^ (t >> np.uint64(14))) & m32
    uniforms: NDArray[np.float64] = out.astype(np.float64) / _TWO_POW_32
    return uniforms


def normal_block(seed: int, n: int) -> NDArray[np.float64]:
    """The first ``n`` draws of ``NormalSampler(Mulberry32(seed))``, vectorised.

    Assumes the sampler has the uniform stream to itself (true for every Monte-Carlo
    pricer). Accepted polar pairs are found in bulk and interleaved as (u·m, v·m), which
    is exactly the scalar sampler's return-then-spare order.
    """
    if n < 0:
        raise ValueError(f"normal_block: n must be >= 0 (got {n})")
    chunks: list[NDArray[np.float64]] = []
    have = 0
    offset = 0
    while have < n:
        pairs_needed = (n - have + 1) // 2
        # Acceptance rate is π/4 ≈ 0.785; oversample so one pass almost always suffices.
        n_pairs = int(pairs_needed / 0.78) + 16
        u01 = uniform_block(seed, 2 * n_pairs, offset=offset).reshape(n_pairs, 2)
        offset += 2 * n_pairs
        u = 2.0 * u01[:, 0] - 1.0
        v = 2.0 * u01[:, 1] - 1.0
        s = u * u + v * v
        ok = (s < 1.0) & (s != 0.0)
        u, v, s = u[ok], v[ok], s[ok]
        mul = np.sqrt((-2.0 * np.log(s)) / s)
        block = np.empty(2 * u.size, dtype=np.float64)
        block[0::2] = u * mul
        block[1::2] = v * mul
        chunks.append(block)
        have += block.size
    return np.concatenate(chunks)[:n] if chunks else np.empty(0, dtype=np.float64)
