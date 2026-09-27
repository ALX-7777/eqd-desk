"""Property-based tests (Hypothesis): no-arbitrage identities over random inputs."""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from eqd_desk.engine import BsmInputs, call_price, delta, gamma, put_price, raw_greeks, vega

inputs = st.builds(
    BsmInputs,
    S=st.floats(1.0, 10_000.0),
    K=st.floats(1.0, 10_000.0),
    T=st.floats(1 / 365, 5.0),
    r=st.floats(-0.02, 0.10),
    q=st.floats(0.0, 0.08),
    sigma=st.floats(0.02, 1.5),
).filter(lambda i: 0.2 < i.S / i.K < 5.0)  # keep strikes where prices are not all rounding


@settings(max_examples=300, deadline=None)
@given(inputs)
def test_put_call_parity(i: BsmInputs) -> None:
    lhs = call_price(i) - put_price(i)
    rhs = i.S * math.exp(-i.q * i.T) - i.K * math.exp(-i.r * i.T)
    assert math.isclose(lhs, rhs, rel_tol=1e-9, abs_tol=1e-9 * max(i.S, i.K))


@settings(max_examples=300, deadline=None)
@given(inputs)
def test_price_bounds(i: BsmInputs) -> None:
    c, p = call_price(i), put_price(i)
    tol = 1e-9 * max(i.S, i.K)
    assert -tol <= c <= i.S * math.exp(-i.q * i.T) + tol
    assert -tol <= p <= i.K * math.exp(-i.r * i.T) + tol


@settings(max_examples=300, deadline=None)
@given(inputs)
def test_greek_signs_and_parities(i: BsmInputs) -> None:
    df_q = math.exp(-i.q * i.T)
    assert gamma(i) >= 0
    assert vega(i) >= 0
    assert math.isclose(delta(i, "call") - delta(i, "put"), df_q, abs_tol=1e-12)
    g = raw_greeks(i, "call")
    assert all(math.isfinite(v) for v in g.as_dict().values())
