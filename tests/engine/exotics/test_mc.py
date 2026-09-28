"""Monte-Carlo primitives: the TS-named RNG factories, streamed normal blocks and GBM
observation paths (scalar and vectorised forms of the same draws)."""

from __future__ import annotations

import math
from itertools import islice

import numpy as np
import pytest

from eqd_desk.engine.exotics import (
    Mulberry32,
    NormalSampler,
    iter_normal_blocks,
    make_normal,
    mulberry32,
    normal_block,
    obs_paths_from_normals,
    simulate_obs_path,
    simulate_obs_paths,
)


def test_factories_are_the_shared_rng() -> None:
    assert isinstance(mulberry32(7), Mulberry32)
    assert isinstance(make_normal(mulberry32(7)), NormalSampler)
    a, b = mulberry32(7), Mulberry32(7)
    assert [a() for _ in range(10)] == [b() for _ in range(10)]


@pytest.mark.parametrize("block_size", [1, 3, 64, 1000])
def test_iter_normal_blocks_is_the_normal_stream(block_size: int) -> None:
    n_blocks = 5000 // block_size + 1
    streamed = np.concatenate(list(islice(iter_normal_blocks(42, block_size), n_blocks)))
    assert all(len(b) == block_size for b in islice(iter_normal_blocks(42, block_size), 3))
    np.testing.assert_array_equal(streamed, normal_block(42, streamed.size))


def test_iter_normal_blocks_rejects_empty_blocks() -> None:
    with pytest.raises(ValueError, match="block_size"):
        next(iter_normal_blocks(1, 0))


def test_vectorised_paths_equal_consecutive_scalar_paths() -> None:
    """Path p of the vectorised form uses draws p·n … (p+1)·n − 1 of ONE shared sampler."""
    args = (100.0, 0.05, 0.01, 0.25, 1 / 52, 26)
    normal = make_normal(mulberry32(2024))
    scalar = np.array([simulate_obs_path(*args, normal) for _ in range(7)])
    vectorised = simulate_obs_paths(*args, 7, 2024)
    assert vectorised.shape == (7, 26)
    np.testing.assert_allclose(vectorised, scalar, rtol=1e-14, atol=0)


def test_single_step_is_the_gbm_formula() -> None:
    """S_dt = S0·exp((r − q − σ²/2)·dt + σ·√dt·Z) with Z the first draw of the stream."""
    S0, r, q, sigma, dt = 100.0, 0.05, 0.02, 0.3, 0.25
    z = make_normal(mulberry32(9))()
    [s1] = simulate_obs_path(S0, r, q, sigma, dt, 1, make_normal(mulberry32(9)))
    assert s1 == S0 * math.exp((r - q - 0.5 * sigma * sigma) * dt + sigma * math.sqrt(dt) * z)


def test_obs_paths_from_normals_matches_simulate() -> None:
    z = normal_block(5, 4 * 10).reshape(4, 10)
    np.testing.assert_array_equal(
        obs_paths_from_normals(50.0, 0.0, 0.0, 0.4, 0.1, z),
        simulate_obs_paths(50.0, 0.0, 0.0, 0.4, 0.1, 10, 4, 5),
    )
    with pytest.raises(ValueError, match="2-D"):
        obs_paths_from_normals(50.0, 0.0, 0.0, 0.4, 0.1, z.ravel())


def test_risk_neutral_drift() -> None:
    """E[S_T] = S0·e^((r−q)T) under the risk-neutral measure (within 4 standard errors)."""
    S0, r, q, sigma, T, steps = 100.0, 0.05, 0.02, 0.3, 1.0, 4
    s_t = simulate_obs_paths(S0, r, q, sigma, T / steps, steps, 100_000, 11)[:, -1]
    stderr = s_t.std() / math.sqrt(s_t.size)
    assert abs(s_t.mean() - S0 * math.exp((r - q) * T)) < 4 * stderr


def test_empty_and_invalid_shapes() -> None:
    assert simulate_obs_paths(100, 0, 0, 0.2, 0.1, 0, 3, 1).shape == (3, 0)
    assert simulate_obs_path(100, 0, 0, 0.2, 0.1, 0, make_normal(mulberry32(1))) == []
    with pytest.raises(ValueError, match="simulate_obs_paths"):
        simulate_obs_paths(100, 0, 0, 0.2, 0.1, -1, 3, 1)
