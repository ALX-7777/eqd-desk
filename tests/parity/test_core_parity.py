"""The Python vanilla core reproduces the TypeScript engine (golden values exported by
``web/scripts/golden/core.golden.ts``)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from eqd_desk.engine import BsmInputs, bsm_core, norm_cdf, norm_pdf, raw_greeks
from eqd_desk.engine.rng import Mulberry32, NormalSampler, normal_block, uniform_block
from tests.parity.golden_io import assert_close, load_golden

GOLDEN = load_golden("core")


def _inputs(d: dict[str, float]) -> BsmInputs:
    return BsmInputs(S=d["S"], K=d["K"], T=d["T"], r=d["r"], q=d["q"], sigma=d["sigma"])


def test_norm_functions() -> None:
    for row in GOLDEN["norm"]:
        assert_close(norm_cdf(row["x"]), row["cdf"], label=f"cdf({row['x']})")
        assert_close(norm_pdf(row["x"]), row["pdf"], label=f"pdf({row['x']})")


def test_bsm_core_intermediates() -> None:
    fields = {"d1": "d1", "d2": "d2", "sqrtT": "sqrt_t", "volSqrtT": "vol_sqrt_t",
              "dfR": "df_r", "dfQ": "df_q", "Teff": "t_eff", "sigmaEff": "sigma_eff"}  # fmt: skip
    for row in GOLDEN["cores"]:
        core = bsm_core(_inputs(row["inputs"]))
        for ts_name, py_name in fields.items():
            # d1/d2 blow up to ~1e8 at the σ/T floors; relative tolerance still applies.
            assert_close(getattr(core, py_name), row["core"][ts_name], label=f"{ts_name} {row}")


@pytest.mark.parametrize("chunk", range(8))
def test_price_and_all_raw_greeks(chunk: int) -> None:
    options: list[dict[str, Any]] = GOLDEN["options"]
    for row in options[chunk::8]:
        got = raw_greeks(_inputs(row["inputs"]), row["type"]).as_dict()
        for name, expected in row["raw"].items():
            # Greeks at the T/σ floors reach ~1e8–1e20 in magnitude; scale atol with them.
            assert_close(
                got[name],
                expected,
                atol=1e-12 * max(1.0, row["inputs"]["S"]),
                label=f"{name} {row['type']} {row['inputs']}",
            )


def test_rng_streams_match_typescript() -> None:
    for row in GOLDEN["rng"]:
        seed = row["seed"]
        rng = Mulberry32(seed)
        assert [rng() for _ in row["uniforms"]] == row["uniforms"], f"seed {seed}"
        np.testing.assert_array_equal(uniform_block(seed, len(row["uniforms"])), row["uniforms"])
        sampler = NormalSampler(Mulberry32(seed))
        np.testing.assert_allclose([sampler() for _ in row["normals"]], row["normals"], rtol=1e-14)
        np.testing.assert_allclose(
            normal_block(seed, len(row["normals"])), row["normals"], rtol=1e-14
        )
