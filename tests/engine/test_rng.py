from __future__ import annotations

import numpy as np
import pytest

from eqd_desk.engine.rng import Mulberry32, NormalSampler, normal_block, uniform_block

SEEDS = [0, 1, 42, 0x5EED, 123456789, 4294967295, -7]


@pytest.mark.parametrize("seed", SEEDS)
def test_uniform_block_equals_scalar_stream(seed: int) -> None:
    rng = Mulberry32(seed)
    scalar = np.array([rng() for _ in range(1000)])
    np.testing.assert_array_equal(uniform_block(seed, 1000), scalar)


def test_uniform_block_offset_continues_the_stream() -> None:
    full = uniform_block(7, 300)
    np.testing.assert_array_equal(uniform_block(7, 100, offset=200), full[200:])


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("n", [0, 1, 2, 3, 1001])
def test_normal_block_equals_scalar_stream(seed: int, n: int) -> None:
    sampler = NormalSampler(Mulberry32(seed))
    scalar = np.array([sampler() for _ in range(n)])
    np.testing.assert_allclose(normal_block(seed, n), scalar, rtol=1e-15, atol=0)


def test_uniforms_are_in_unit_interval_and_look_uniform() -> None:
    u = uniform_block(2024, 200_000)
    assert u.min() >= 0.0
    assert u.max() < 1.0
    assert abs(u.mean() - 0.5) < 3e-3
    assert abs(u.var() - 1 / 12) < 3e-3


def test_normals_have_unit_moments() -> None:
    z = normal_block(99, 200_000)
    assert abs(z.mean()) < 1e-2
    assert abs(z.std() - 1.0) < 1e-2


def test_rejects_negative_sizes() -> None:
    with pytest.raises(ValueError, match="uniform_block"):
        uniform_block(1, -1)
    with pytest.raises(ValueError, match="normal_block"):
        normal_block(1, -1)
