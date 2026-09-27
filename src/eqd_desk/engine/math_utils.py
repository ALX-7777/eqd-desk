"""Standard-normal density and cumulative distribution: the only "special functions" the
engine needs.

Accuracy here propagates into every price and greek, so we use a machine-precision
cumulative normal rather than a quick 1e-7 approximation.
"""

from __future__ import annotations

import math

SQRT_2PI = math.sqrt(2.0 * math.pi)
"""√(2π), used by the normal density and the CDF tail (2.5066282746310002)."""


def norm_pdf(x: float) -> float:
    """Standard-normal probability density function φ(x) = exp(−x²/2) / √(2π).

    Exact to machine precision.
    """
    return math.exp(-0.5 * x * x) / SQRT_2PI


def norm_cdf(x: float) -> float:
    """Standard-normal cumulative distribution function N(x) = P(Z ≤ x).

    Implementation: Graeme West (2009), "Better approximations to cumulative normal
    functions", Wilmott Magazine, a transcription of Hart's (1968) rational
    approximation (algorithm 5666). Accuracy is ~1e-14 relative or better near the
    centre (|x| ≲ 4) and degrades gracefully in the far tails (≈1e-11 at |x|≈5, ≈1e-8
    at |x|≈8), inherent to Hart 5666 and still orders of magnitude tighter than anything
    option pricing needs. A simple erf-based formula would lose far more relative
    accuracy in those wings.

    The routine computes the SMALL-tail probability ``c = P(Z > |x|)`` using a rational
    approximation for |x| < 7.07 and a continued fraction beyond it, then reflects:
    N(x) = c for x ≤ 0, and N(x) = 1 − c for x > 0. Working on the small tail this way
    avoids catastrophic cancellation, which is exactly why callers should pass
    ``norm_cdf(-d)`` directly instead of computing ``1 - norm_cdf(d)``.
    """
    z = abs(x)

    if z > 37.0:
        # Beyond ~37 standard deviations the tail underflows to 0 in double precision.
        c = 0.0
    else:
        e = math.exp(-0.5 * z * z)
        if z < 7.07106781186547:
            # Rational approximation (numerator degree 6 / denominator degree 7).
            num = 3.52624965998911e-2 * z + 0.700383064443688
            num = num * z + 6.37396220353165
            num = num * z + 33.912866078383
            num = num * z + 112.079291497871
            num = num * z + 221.213596169931
            num = num * z + 220.206867912376

            den = 8.83883476483184e-2 * z + 1.75566716318264
            den = den * z + 16.064177579207
            den = den * z + 86.7807322029461
            den = den * z + 296.564248779674
            den = den * z + 637.333633378831
            den = den * z + 793.826512519948
            den = den * z + 440.413735824752

            c = (e * num) / den
        else:
            # Continued-fraction tail keeps RELATIVE accuracy for large |x|.
            f = z + 1.0 / (z + 2.0 / (z + 3.0 / (z + 4.0 / (z + 13.0 / 20.0))))
            c = e / (SQRT_2PI * f)

    return c if x <= 0 else 1.0 - c
