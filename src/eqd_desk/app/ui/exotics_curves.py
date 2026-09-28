"""Seeds, control bounds, chart data and readout numbers for the exotics page.

PURE (no Streamlit): everything the exotics page plots or prints is computed here from the
engine (:mod:`eqd_desk.engine.exotics`), with the same inputs, sweeps and arithmetic as the
React views (``web/src/components/exotics/*View.tsx``), so both apps print the same numbers:

- the seeds (each view's ``seed()``) and the slider bounds (``LabeledSlider`` props);
- the sweeps behind each chart: a barrier's metric vs spot (with the vanilla beside it),
  the digital vs its replicating call spread, the autocallable's sample paths and barrier
  levels, the variance swap's 1/K² strip, its smile and the skew effect on the fair vol;
- the small derived numbers of the readouts (% of vanilla, the knock-in + knock-out =
  vanilla parity, the detail lines under each hero number).

Beyond the React views: the barrier and the digital expose r and q; the digital can pay the
asset instead of cash (asset-or-nothing = vanilla call + K cash digitals, replicated with
spreads the same way); the variance swap's skew can be switched off (a flat smile prices
variance at the ATM vol) and its strip's strike range and count are controls. At the
defaults (cash payout, skew on, the engine's strip) every number is the React one.

Every sweep is evaluated on :func:`~eqd_desk.app.ui.charts.sweep_x` points (React's
``lo + ((hi − lo)·i)/N``), so each value is bit-identical to the React chart's. Checked
against direct engine calls in ``tests/ui/test_exotics_curves.py``.

Units: spot, strikes, barriers and prices in index points of the snapshot currency; T in
years; r, q continuously compounded decimals; vols decimal; greeks in desk units (see
:mod:`eqd_desk.engine.exotics.numeric_greeks`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final, Literal

import pandas as pd

from eqd_desk.app.ui.charts import sweep_x
from eqd_desk.app.ui.format import fmt_money, fmt_num, js_round, to_fixed
from eqd_desk.content import ExoticKind, ExoticMetric
from eqd_desk.data import MarketSnapshot
from eqd_desk.engine import BsmInputs, OptionType, analyze_option
from eqd_desk.engine import price as vanilla_price
from eqd_desk.engine.exotics import (
    AutocallInputs,
    AutocallResult,
    BarrierInputs,
    BarrierKind,
    DigitalInputs,
    ExoticGreeks,
    VarSwapInputs,
    VarSwapResult,
    VolFn,
    asset_or_nothing_price,
    autocall_greeks,
    barrier_greeks,
    barrier_price,
    call_spread_replication,
    cash_or_nothing_price,
    digital_greeks,
    numeric_greeks,
    price_autocall,
    price_variance_swap,
    simulate_obs_paths,
)

# ------------------------------------------------------------------ shared


@dataclass(frozen=True, slots=True)
class Bounds:
    """Range and increment of one slider (React ``LabeledSlider`` ``min`` / ``max`` /
    ``step``)."""

    lo: float
    hi: float
    step: float


def listed_step(spot: float) -> float:
    """The index's listed-strike grid in points: 25 above 2,000 (SPX, SX5E), else 5 (React
    ``const step = snapshot.spot >= 2000 ? 25 : 5``)."""
    return 25.0 if spot >= 2000 else 5.0


def to_grid(x: float, step: float) -> float:
    """``x`` rounded to the nearest multiple of ``step`` (React ``Math.round(x / step) *
    step``, ties toward +∞)."""
    return js_round(x / step) * step


def metric_value(values: ExoticGreeks, metric: ExoticMetric) -> float:
    """One metric (``"price"`` or a greek) of an exotic's :class:`ExoticGreeks`."""
    return values.as_dict()[metric]


VOL_BOUNDS: Final = Bounds(0.05, 0.8, 0.0025)
"""σ slider of the barrier and the digital (decimal vol)."""
RATE_BOUNDS: Final = Bounds(-0.02, 0.1, 0.0005)
"""r slider (the greeks lab's range)."""
DIV_BOUNDS: Final = Bounds(0.0, 0.06, 0.0005)
"""q slider (the greeks lab's range)."""

PRICED_READOUT_KEYS: Final[tuple[ExoticMetric, ...]] = ("delta", "gamma", "vega", "theta", "rho")
"""Greek rows under the barrier's and the digital's premium."""
AUTOCALL_READOUT_KEYS: Final[tuple[ExoticMetric, ...]] = ("delta", "vega", "theta", "rho")
"""Greek rows of the autocallable (Monte-Carlo gamma is too noisy to print)."""

DEFAULT_METRIC: Final[Mapping[ExoticKind, ExoticMetric]] = MappingProxyType(
    {"barrier": "gamma", "digital": "price", "autocall": "delta", "varswap": "price"}
)
"""The metric each view opens on (React ``useState<ExoticMetric>(…)``); the variance swap
has none (it shows no greeks)."""

# ------------------------------------------------------------------ barrier

BARRIER_KIND_LABELS: Final[Mapping[BarrierKind, str]] = MappingProxyType(
    {"down-out": "Down-out", "down-in": "Down-in", "up-out": "Up-out", "up-in": "Up-in"}
)
"""The barrier-kind segments, in React order (BarrierView ``KINDS``)."""

BARRIER_CHART_METRICS: Final[tuple[ExoticMetric, ...]] = ("price", "delta", "gamma", "vega")
"""Metrics offered by the barrier chart's own selector."""

BARRIER_T_BOUNDS: Final = Bounds(0.02, 2.0, 0.01)
"""Barrier time-to-expiry slider (years)."""

BARRIER_SWEEP: Final = (0.55, 1.45, 120)
"""Barrier chart: spot from 0.55× to 1.45× the snapshot spot, 120 intervals."""


def barrier_seed(snap: MarketSnapshot) -> BarrierInputs:
    """The barrier view's opening inputs: a 6-month down-and-out call struck at the money
    (K = spot on the strike grid) with the barrier 10% below, at the snapshot's vol."""
    step = listed_step(snap.spot)
    return BarrierInputs(
        S=snap.spot,
        K=to_grid(snap.spot, step),
        T=0.5,
        r=snap.r,
        q=snap.q,
        sigma=snap.atm_vol_30d,
        type="call",
        H=to_grid(snap.spot * 0.9, step),
        kind="down-out",
    )


def level_bounds(spot: float, lo_mult: float, hi_mult: float) -> Bounds:
    """A spot / strike / barrier slider: ``lo_mult``…``hi_mult`` × spot, both ends on the
    strike grid, moving in fifths of it (React ``round(spot·m)``, ``step / 5``)."""
    step = listed_step(spot)
    return Bounds(to_grid(spot * lo_mult, step), to_grid(spot * hi_mult, step), step / 5)


def barrier_bounds(spot: float) -> dict[str, Bounds]:
    """Slider bounds of the barrier view, keyed by input name (S, K, H, T, sigma, r, q)."""
    return {
        "S": level_bounds(spot, 0.6, 1.4),
        "K": level_bounds(spot, 0.6, 1.4),
        "H": level_bounds(spot, 0.5, 1.5),
        "T": BARRIER_T_BOUNDS,
        "sigma": VOL_BOUNDS,
        "r": RATE_BOUNDS,
        "q": DIV_BOUNDS,
    }


def vanilla_inputs(i: BarrierInputs | DigitalInputs) -> BsmInputs:
    """The plain vanilla with the same S, K, T, r, q, σ as an exotic."""
    return BsmInputs(S=i.S, K=i.K, T=i.T, r=i.r, q=i.q, sigma=i.sigma)


def vanilla_metric(i: BarrierInputs, metric: ExoticMetric) -> float:
    """The same metric of the vanilla with the barrier's inputs (analytic BSM, desk units)."""
    reported = analyze_option(vanilla_inputs(i), i.type).reported
    return float(getattr(reported, metric))


def barrier_curve(i: BarrierInputs, metric: ExoticMetric, spot: float) -> pd.DataFrame:
    """The barrier chart: ``metric`` of the barrier option and of the matching vanilla as
    spot sweeps 0.55…1.45 × ``spot`` (the snapshot spot, so the axis stays put while the
    inputs move).

    Columns: ``S``, ``barrier`` (bump greeks, :func:`barrier_greeks`) and ``vanilla``
    (analytic BSM). Near a knock-out barrier the barrier's gamma spikes while the vanilla's
    stays smooth: that contrast is the chart's lesson.
    """
    lo_mult, hi_mult, n = BARRIER_SWEEP
    xs = sweep_x(spot * lo_mult, spot * hi_mult, n)
    return pd.DataFrame(
        {
            "S": xs,
            "barrier": [metric_value(barrier_greeks(replace(i, S=x)), metric) for x in xs],
            "vanilla": [vanilla_metric(replace(i, S=x), metric) for x in xs],
        }
    )


BARRIER_COMPLEMENT: Final[Mapping[BarrierKind, BarrierKind]] = MappingProxyType(
    {"down-out": "down-in", "down-in": "down-out", "up-out": "up-in", "up-in": "up-out"}
)
"""The barrier with the same level and direction but the opposite effect."""


@dataclass(frozen=True, slots=True)
class BarrierParity:
    """Knock-in + knock-out = vanilla, for the barrier's direction and level."""

    out_kind: BarrierKind
    in_kind: BarrierKind
    knock_out: float
    """Premium of the knock-out."""
    knock_in: float
    """Premium of the knock-in."""
    vanilla: float
    """Premium of the vanilla."""

    @property
    def total(self) -> float:
        """Knock-in + knock-out (equals :attr:`vanilla` up to rounding)."""
        return self.knock_in + self.knock_out


def barrier_parity(i: BarrierInputs) -> BarrierParity:
    """Both halves of the barrier's in/out pair and the vanilla they add up to."""
    out_kind = i.kind if i.kind.endswith("out") else BARRIER_COMPLEMENT[i.kind]
    in_kind = BARRIER_COMPLEMENT[out_kind]
    return BarrierParity(
        out_kind=out_kind,
        in_kind=in_kind,
        knock_out=barrier_price(replace(i, kind=out_kind)),
        knock_in=barrier_price(replace(i, kind=in_kind)),
        vanilla=analyze_option(vanilla_inputs(i), i.type).reported.price,
    )


def pct_of_vanilla(price: float, vanilla: float) -> int:
    """The barrier premium as a whole percentage of the vanilla (the React tag
    ``Math.round(pct * 100)``; 0 when the vanilla is worth nothing)."""
    pct = price / vanilla if vanilla != 0 else 0.0
    return js_round(pct * 100)


@dataclass(frozen=True, slots=True)
class BarrierData:
    """Everything the barrier view shows for one set of inputs."""

    greeks: ExoticGreeks
    """Price and bump greeks of the barrier option."""
    parity: BarrierParity
    """Its in/out pair and the vanilla they add up to."""
    curve: pd.DataFrame
    """The chart sweep (:func:`barrier_curve`)."""


def barrier_data(i: BarrierInputs, metric: ExoticMetric, spot: float) -> BarrierData:
    """Price, greeks, in/out parity and the chart sweep of a barrier option."""
    return BarrierData(barrier_greeks(i), barrier_parity(i), barrier_curve(i, metric, spot))


# ------------------------------------------------------------------ digital

DIGITAL_CHART_METRICS: Final[tuple[ExoticMetric, ...]] = ("price", "delta", "gamma")
"""Metrics offered by the digital chart's own selector."""

DIGITAL_T_BOUNDS: Final = Bounds(0.005, 1.5, 0.005)
"""Digital time-to-expiry slider (years): down to ~2 days, to watch the step sharpen."""
DIGITAL_CASH_BOUNDS: Final = Bounds(10.0, 500.0, 10.0)
"""Cash payout Q slider."""

DIGITAL_SWEEP: Final = (0.7, 1.3, 140)
"""Digital chart: spot from 0.7× to 1.3× the snapshot spot, 140 intervals."""


def digital_seed(snap: MarketSnapshot) -> DigitalInputs:
    """The digital view's opening inputs: a 3-month cash-or-nothing call paying 100, struck
    at the money (on the strike grid), at the snapshot's vol."""
    return DigitalInputs(
        S=snap.spot,
        K=to_grid(snap.spot, listed_step(snap.spot)),
        T=0.25,
        r=snap.r,
        q=snap.q,
        sigma=snap.atm_vol_30d,
        type="call",
        cash=100.0,
    )


def digital_width_seed(spot: float) -> float:
    """Opening call-spread width Δ: 2% of spot on the strike grid."""
    return to_grid(spot * 0.02, listed_step(spot))


def digital_bounds(spot: float) -> dict[str, Bounds]:
    """Slider bounds of the digital view, keyed by input name (S, K, T, sigma, r, q, cash,
    width)."""
    step = listed_step(spot)
    return {
        "S": level_bounds(spot, 0.6, 1.4),
        "K": level_bounds(spot, 0.6, 1.4),
        "T": DIGITAL_T_BOUNDS,
        "sigma": VOL_BOUNDS,
        "r": RATE_BOUNDS,
        "q": DIV_BOUNDS,
        "cash": DIGITAL_CASH_BOUNDS,
        "width": Bounds(step / 5, to_grid(spot * 0.1, step), step / 5),
    }


DigitalPayout = Literal["cash", "asset"]
"""What an in-the-money digital pays at expiry: a fixed cash amount Q (cash-or-nothing, the
React view) or the asset itself, S_T (asset-or-nothing)."""

DIGITAL_PAYOUT_LABELS: Final[Mapping[DigitalPayout, str]] = MappingProxyType(
    {"cash": "Cash-or-nothing", "asset": "Asset-or-nothing"}
)
"""The payout segments, cash first (the React view's only payout)."""


def digital_price(i: DigitalInputs, payout: DigitalPayout = "cash") -> float:
    """Closed-form price of the digital: Q·e^(−rT)·N(±d2) for cash-or-nothing,
    S·e^(−qT)·N(±d1) for asset-or-nothing (``cash`` is then ignored)."""
    return cash_or_nothing_price(i) if payout == "cash" else asset_or_nothing_price(i)


def payout_greeks(i: DigitalInputs, payout: DigitalPayout = "cash") -> ExoticGreeks:
    """Price and bump greeks of the digital, in desk units: the engine's
    :func:`digital_greeks` for cash-or-nothing; the same central differences
    (:func:`numeric_greeks`) of :func:`asset_or_nothing_price` for asset-or-nothing."""
    if payout == "cash":
        return digital_greeks(i)

    def px(S: float, sigma: float, T: float, r: float) -> float:
        return asset_or_nothing_price(replace(i, S=S, sigma=sigma, T=T, r=r))

    return numeric_greeks(px, i.S, i.sigma, i.T, i.r)


def payout_amount(i: DigitalInputs, payout: DigitalPayout) -> float:
    """The jump in payoff across the strike that the replicating spreads must deliver: Q for
    cash-or-nothing, K for asset-or-nothing (whose payoff jumps from 0 to S_T ≈ K there)."""
    return i.cash if payout == "cash" else i.K


def replication_price(i: DigitalInputs, width: float, payout: DigitalPayout = "cash") -> float:
    """Price of the static replication of the digital with spreads of width Δ = ``width``.

    Cash-or-nothing: (Q/Δ) call spreads (put spreads for a put), the engine's
    :func:`call_spread_replication`. Asset-or-nothing, from the exact identities
    AoN call = vanilla call + K·(cash digital call, Q = 1) and
    AoN put = K·(cash digital put, Q = 1) − vanilla put, with the cash digital replaced by
    (K/Δ) spreads: vanilla call + (K/Δ) call spreads, or (K/Δ) put spreads − vanilla put.
    Converges to :func:`digital_price` as Δ → 0.
    """
    if payout == "cash":
        return call_spread_replication(i, width)
    spreads = call_spread_replication(replace(i, cash=i.K), width)
    vanilla = vanilla_price(vanilla_inputs(i), i.type)
    return vanilla + spreads if i.type == "call" else spreads - vanilla


@dataclass(frozen=True, slots=True)
class AssetDecomposition:
    """An asset-or-nothing digital split exactly into a vanilla and K cash digitals:
    call = vanilla + K·digital; put = K·digital − vanilla."""

    vanilla: float
    """The vanilla with the same strike and expiry."""
    k_digitals: float
    """K cash-or-nothing digitals paying 1 each (one digital paying K)."""
    sign: Literal[1, -1]
    """+1 for a call (vanilla added), −1 for a put (vanilla subtracted)."""

    @property
    def total(self) -> float:
        """K·digital ± vanilla: the asset-or-nothing price, up to rounding."""
        return self.k_digitals + self.sign * self.vanilla


def asset_decomposition(i: DigitalInputs) -> AssetDecomposition:
    """The asset-or-nothing digital as a vanilla and K cash digitals (closed forms)."""
    return AssetDecomposition(
        vanilla=vanilla_price(vanilla_inputs(i), i.type),
        k_digitals=cash_or_nothing_price(replace(i, cash=i.K)),
        sign=1 if i.type == "call" else -1,
    )


def digital_curve(
    i: DigitalInputs,
    width: float,
    metric: ExoticMetric,
    spot: float,
    payout: DigitalPayout = "cash",
) -> pd.DataFrame:
    """The digital chart as spot sweeps 0.7…1.3 × ``spot``.

    Columns: ``S``; ``digital`` (closed-form price, :func:`digital_price`); ``spread`` (its
    replication with spreads of width ``width``, :func:`replication_price`); ``greek``
    (``metric`` of the digital, by bumping). The replication hugs the digital and converges
    to it as the width or the time to expiry shrinks.
    """
    lo_mult, hi_mult, n = DIGITAL_SWEEP
    xs = sweep_x(spot * lo_mult, spot * hi_mult, n)
    points = [replace(i, S=x) for x in xs]
    return pd.DataFrame(
        {
            "S": xs,
            "digital": [digital_price(p, payout) for p in points],
            "spread": [replication_price(p, width, payout) for p in points],
            "greek": [metric_value(payout_greeks(p, payout), metric) for p in points],
        }
    )


def spread_convergence(
    i: DigitalInputs, widths: Sequence[float], payout: DigitalPayout = "cash"
) -> pd.DataFrame:
    """The replication's price against the spread width Δ, beside the digital it converges
    to as Δ → 0.

    Columns: ``width``; ``spread`` (:func:`replication_price`); ``digital`` (the exact
    digital, constant); ``size`` (payout/Δ, i.e. Q/Δ or K/Δ: the number of spreads needed,
    which explodes as Δ → 0 — the un-hedgeable bit).
    """
    digital = digital_price(i, payout)
    amount = payout_amount(i, payout)
    return pd.DataFrame(
        {
            "width": list(widths),
            "spread": [replication_price(i, w, payout) for w in widths],
            "digital": [digital] * len(widths),
            "size": [amount / w for w in widths],
        }
    )


def width_grid(bounds: Bounds) -> list[float]:
    """Every slider position of the replication width (``lo``, ``lo + step``, …, ``hi``)."""
    n = max(1, js_round((bounds.hi - bounds.lo) / bounds.step))
    return sweep_x(bounds.lo, bounds.hi, n)


def digital_detail(spread: float, cash: float, width: float, *, label: str = "spread") -> str:
    """The line under the digital premium: the replication's price and the (payout/Δ) size
    it takes (``spread 53.14 · size 0.800×``)."""
    return f"{label} {fmt_money(spread)} · size {fmt_num(cash / width, 3)}×"


def digital_series_labels(option: OptionType, payout: DigitalPayout) -> tuple[str, str]:
    """Legend labels of the (replication, digital) curves: ``("Call spread", "Digital")``
    for a cash call (React), ``("Vanilla + call spreads", "Asset-or-nothing")`` for an
    asset call, ``("Put spreads − vanilla", "Asset-or-nothing")`` for an asset put."""
    if payout == "cash":
        return f"{option.capitalize()} spread", "Digital"
    spreads = "Vanilla + call spreads" if option == "call" else "Put spreads − vanilla"
    return spreads, DIGITAL_PAYOUT_LABELS["asset"]


def replication_recipe(i: DigitalInputs, width: float, payout: DigitalPayout) -> str:
    """What the replication holds, in words and sizes: ``0.800× call spreads`` (cash),
    ``50.4× call spreads + 1 vanilla call`` / ``50.4× put spreads − 1 vanilla put``
    (asset)."""
    spreads = f"{fmt_num(payout_amount(i, payout) / width, 3)}× {i.type} spreads"
    if payout == "cash":
        return spreads
    return f"{spreads} {'+' if i.type == 'call' else '−'} 1 vanilla {i.type}"


@dataclass(frozen=True, slots=True)
class DigitalData:
    """Everything the digital view shows for one set of inputs."""

    greeks: ExoticGreeks
    """Price and bump greeks of the digital."""
    spread: float
    """Price of the replication at the chosen width."""
    curve: pd.DataFrame
    """The chart sweep against spot (:func:`digital_curve`)."""
    convergence: pd.DataFrame
    """The replication against its width (:func:`spread_convergence`), over every slider
    position of the width."""
    decomposition: AssetDecomposition | None = None
    """Vanilla + K cash digitals (asset-or-nothing only)."""


def digital_data(
    i: DigitalInputs,
    width: float,
    metric: ExoticMetric,
    spot: float,
    payout: DigitalPayout = "cash",
) -> DigitalData:
    """Price, greeks, replication and both chart sweeps of a digital (``spot`` is the
    snapshot spot, which fixes the sweep range and the width grid)."""
    return DigitalData(
        payout_greeks(i, payout),
        replication_price(i, width, payout),
        digital_curve(i, width, metric, spot, payout),
        spread_convergence(i, width_grid(digital_bounds(spot)["width"]), payout),
        asset_decomposition(i) if payout == "asset" else None,
    )


# ------------------------------------------------------------------ autocallable

AUTOCALL_PRICE_PATHS: Final = 12_000
"""Monte-Carlo paths for the note value and its diagnostics (React ``priceAutocall(i,
12000)``)."""
AUTOCALL_GREEK_PATHS: Final = 16_000
"""Monte-Carlo paths for the bump greeks (React ``autocallGreeks(i, 16000)``)."""
SAMPLE_PATHS: Final = 8
"""Paths drawn on the chart."""
SAMPLE_STEPS: Final = 60
"""Time steps per drawn path."""
SAMPLE_SEED: Final = 0xC0FFEE
"""Seed of the drawn paths (fixed, so the picture only changes when the inputs do)."""
AUTOCALL_NOTIONAL: Final = 100.0
"""Par of the note."""


def autocall_seed(snap: MarketSnapshot) -> AutocallInputs:
    """The autocallable view's opening note: 3 years, 6 semi-annual observations, 4% coupon
    per period with memory, autocall at 100%, coupon barrier 70%, capital protected down to
    65% of the initial fixing S0 = today's spot."""
    return AutocallInputs(
        S=snap.spot,
        S0=snap.spot,
        sigma=snap.atm_vol_30d,
        r=snap.r,
        q=snap.q,
        maturity=3.0,
        n_obs=6,
        coupon_rate=0.04,
        autocall_barrier=1.0,
        coupon_barrier=0.7,
        protection_barrier=0.65,
        memory=True,
        notional=AUTOCALL_NOTIONAL,
    )


def autocall_bounds(s0: float) -> dict[str, Bounds]:
    """Slider bounds of the autocallable view, keyed by input name. Barriers and the coupon
    are fractions (of S0 and of par); maturity in years."""
    return {
        "S": Bounds(js_round(s0 * 0.4), js_round(s0 * 1.5), s0 / 200),
        "maturity": Bounds(1.0, 6.0, 0.5),
        "n_obs": Bounds(1, 24, 1),
        "coupon_rate": Bounds(0.0, 0.08, 0.0025),
        "autocall_barrier": Bounds(0.8, 1.2, 0.01),
        "coupon_barrier": Bounds(0.4, 1.0, 0.01),
        "protection_barrier": Bounds(0.3, 1.0, 0.01),
        "sigma": Bounds(0.05, 0.6, 0.0025),
    }


@dataclass(frozen=True, slots=True)
class AutocallLevels:
    """The note's barriers as absolute index levels (fractions × S0)."""

    autocall: float
    coupon: float
    protection: float


def autocall_levels(i: AutocallInputs) -> AutocallLevels:
    """Autocall, coupon and protection barriers in index points."""
    return AutocallLevels(
        autocall=i.autocall_barrier * i.S0,
        coupon=i.coupon_barrier * i.S0,
        protection=i.protection_barrier * i.S0,
    )


def observation_times(i: AutocallInputs) -> list[float]:
    """The observation dates in years (k · maturity / n_obs, k = 1…n_obs), as the pricer
    uses them."""
    dt = i.maturity / i.n_obs
    return [k * dt for k in range(1, i.n_obs + 1)]


def sample_paths(
    i: AutocallInputs,
    n_paths: int = SAMPLE_PATHS,
    steps: int = SAMPLE_STEPS,
    seed: int = SAMPLE_SEED,
) -> pd.DataFrame:
    """A few risk-neutral GBM paths of the underlying from today's spot to maturity, for
    the picture (not the price): the React ``paths`` memo, draw for draw.

    Columns: ``t`` (years, (k / steps) · maturity) and ``p0`` … ``p{n-1}`` (index levels,
    starting at S). Path p consumes draws p·steps … (p+1)·steps − 1 of
    ``make_normal(mulberry32(seed))``.
    """
    dt = i.maturity / steps
    levels = simulate_obs_paths(i.S, i.r, i.q, i.sigma, dt, steps, n_paths, seed)
    data: dict[str, list[float]] = {"t": [(k / steps) * i.maturity for k in range(steps + 1)]}
    for p in range(n_paths):
        data[f"p{p}"] = [i.S, *(float(v) for v in levels[p])]
    return pd.DataFrame(data)


def autocall_spot_display(S: float, s0: float) -> str:
    """The spot slider's readout: level and moneyness vs the initial fixing
    (``6,312.45 · 100%``)."""
    return f"{fmt_money(S)} · {js_round((S / s0) * 100)}%"


def autocall_value_label(notional: float) -> str:
    """Label of the note's value (``Note value (par 100)``)."""
    return f"Note value (par {js_number(notional)})"


def autocall_detail(price: float, notional: float) -> str:
    """The line under the note value: value as a percentage of par (``103.2% of par``)."""
    return f"{fmt_num((price / notional) * 100, 4)}% of par"


def mc_badge(stderr: float) -> str:
    """The Monte-Carlo error tag (``MC ±0.060``): one standard error of the price."""
    return f"MC ±{fmt_num(stderr, 2)}"


@dataclass(frozen=True, slots=True)
class AutocallData:
    """Everything the autocallable view shows for one note."""

    result: AutocallResult
    """Monte-Carlo value and diagnostics (:data:`AUTOCALL_PRICE_PATHS` paths)."""
    greeks: ExoticGreeks
    """Bump greeks with common random numbers (:data:`AUTOCALL_GREEK_PATHS` paths)."""
    paths: pd.DataFrame
    """The drawn sample paths (:func:`sample_paths`)."""


def autocall_data(i: AutocallInputs) -> AutocallData:
    """Monte-Carlo value and diagnostics, greeks and sample paths of a note (the React
    view's ``priceAutocall(i, 12000)``, ``autocallGreeks(i, 16000)`` and ``paths``). The
    heavy part of the page: ~0.15 s at the defaults, ~0.5 s with 24 observations."""
    return AutocallData(
        price_autocall(i, AUTOCALL_PRICE_PATHS),
        autocall_greeks(i, AUTOCALL_GREEK_PATHS),
        sample_paths(i),
    )


# ------------------------------------------------------------------ variance swap

VARSWAP_VOL_FLOOR: Final = 0.03
"""Floor of the parametric smile (React ``Math.max(0.03, …)``)."""


@dataclass(frozen=True, slots=True)
class VarSwapControls:
    """The variance swap view's inputs: tenor, a parametric smile (ATM level + skew slope
    and curvature in log-moneyness vs the forward) and the replication strip's strike range.
    """

    T: float
    """Tenor in years."""
    atm_vol: float
    """Implied vol at the forward (decimal)."""
    slope: float
    """Skew slope: vol change per unit of ln(K/F) (negative = equity skew)."""
    curv: float
    """Smile curvature: vol change per unit of ln(K/F)²."""
    lo_mult: float = 0.3
    """Lowest strike of the strip, as a multiple of the forward."""
    hi_mult: float = 3.0
    """Highest strike of the strip, as a multiple of the forward."""
    n_strikes: int = 400
    """Number of strikes in the strip."""
    skew: bool = True
    """False = a FLAT smile at :attr:`atm_vol` (slope and curvature ignored): the strip then
    prices the variance at the ATM vol, which isolates what the skew adds."""

    @property
    def smile_slope(self) -> float:
        """The slope actually used: :attr:`slope`, or 0 with the skew off."""
        return self.slope if self.skew else 0.0

    @property
    def smile_curv(self) -> float:
        """The curvature actually used: :attr:`curv`, or 0 with the skew off."""
        return self.curv if self.skew else 0.0


def varswap_seed(snap: MarketSnapshot) -> VarSwapControls:
    """The variance swap view's opening inputs: 30 days (a VIX-style tenor), the snapshot's
    ATM vol and skew shape, the engine's default strip (0.3…3 × F, 400 strikes)."""
    return VarSwapControls(
        T=30 / 365, atm_vol=snap.atm_vol_30d, slope=snap.skew.slope, curv=snap.skew.curv
    )


def varswap_bounds() -> dict[str, Bounds]:
    """Slider bounds of the variance swap view, keyed by control name."""
    return {
        "T": Bounds(7 / 365, 1.0, 1 / 365),
        "atm_vol": Bounds(0.05, 0.6, 0.0025),
        "slope": Bounds(-1.2, 0.2, 0.01),
        "curv": Bounds(0.0, 2.0, 0.02),
        "lo_mult": Bounds(0.05, 0.95, 0.05),
        "hi_mult": Bounds(1.05, 5.0, 0.05),
        "n_strikes": Bounds(20, 800, 10),
    }


def forward_level(S: float, r: float, q: float, T: float) -> float:
    """Forward F = S·e^((r − q)·T)."""
    return S * math.exp((r - q) * T)


def smile(atm_vol: float, slope: float, curv: float, forward: float) -> VolFn:
    """The parametric smile at one tenor, in log-moneyness vs the forward F:
    σ(K) = max(0.03, atm + slope·ln(K/F) + curv·ln(K/F)²) (React ``volFor``)."""

    def vol_for(K: float) -> float:
        k = math.log(K / forward)
        return max(VARSWAP_VOL_FLOOR, atm_vol + slope * k + curv * k**2)

    return vol_for


@dataclass(frozen=True, slots=True)
class VarSwapView:
    """A priced variance swap and the smile it was priced on."""

    result: VarSwapResult
    vol_for: VolFn

    @property
    def convexity_premium(self) -> float:
        """Fair vol − ATM vol: positive with an equity skew."""
        return self.result.fair_vol - self.result.atm_vol


def price_varswap(c: VarSwapControls, *, S: float, r: float, q: float) -> VarSwapView:
    """Fair variance of the swap by the 1/K²-weighted strip over the controls' smile (flat
    at the ATM vol when the skew is off)."""
    vol_for = smile(c.atm_vol, c.smile_slope, c.smile_curv, forward_level(S, r, q, c.T))
    result = price_variance_swap(
        VarSwapInputs(
            S=S,
            T=c.T,
            r=r,
            q=q,
            vol_for=vol_for,
            lo_mult=c.lo_mult,
            hi_mult=c.hi_mult,
            n_strikes=c.n_strikes,
        )
    )
    return VarSwapView(result, vol_for)


STRIP_EVERY: Final = 3
"""The strip is plotted at every third strike (React down-sampling)."""


def strip_frame(view: VarSwapView, every: int = STRIP_EVERY) -> pd.DataFrame:
    """The replication strip for the charts, every ``every``-th strike.

    Columns: ``K``; ``contribution`` (ΔK/K² × OTM option price, before the 2·e^(rT)/T
    factor); ``vol`` (the smile at K).
    """
    points = view.result.strip[::every]
    return pd.DataFrame(
        {
            "K": [p.K for p in points],
            "contribution": [p.contribution for p in points],
            "vol": [view.vol_for(p.K) for p in points],
        }
    )


SMILE_MIN_SPAN: Final = 0.04
"""Smallest vol range (4 vol points) the smile chart's axis spans, so a flat smile reads as
a flat line instead of an axis blown up around rounding noise."""


def vol_axis_domain(
    vols: Sequence[float], min_span: float = SMILE_MIN_SPAN
) -> tuple[float, float] | None:
    """The y domain of a vol chart: ``None`` (automatic) when ``vols`` span at least
    ``min_span``, else a band of ``min_span`` centred on them (floored at 0)."""
    lo, hi = min(vols), max(vols)
    if hi - lo >= min_span:
        return None
    bottom = max(0.0, (lo + hi) / 2 - min_span / 2)
    return bottom, bottom + min_span


SKEW_SWEEP_POINTS: Final = 14
"""Intervals of the skew-effect sweep over the slope slider's range (steps of 0.1)."""


def skew_effect(
    c: VarSwapControls, *, S: float, r: float, q: float, slopes: Sequence[float]
) -> pd.DataFrame:
    """Fair vol and ATM vol as the skew slope varies, everything else fixed (the curvature
    in use, 0 with the skew off): the steeper the (negative) skew, the more the 1/K² strip
    pays for the rich downside puts.

    Columns: ``slope``, ``fair_vol``, ``atm_vol``.
    """
    base = replace(c, skew=True, curv=c.smile_curv)
    fair: list[float] = []
    atm: list[float] = []
    for s in slopes:
        view = price_varswap(replace(base, slope=s), S=S, r=r, q=q)
        fair.append(view.result.fair_vol)
        atm.append(view.result.atm_vol)
    return pd.DataFrame({"slope": list(slopes), "fair_vol": fair, "atm_vol": atm})


@dataclass(frozen=True, slots=True)
class VarSwapData:
    """Everything the variance swap view shows for one set of controls."""

    fair_variance: float
    """Annualised fair variance."""
    fair_vol: float
    """√(fair variance)."""
    atm_vol: float
    """Implied vol at the forward."""
    forward: float
    """Forward level F."""
    strip: pd.DataFrame
    """The strip and smile for the charts (:func:`strip_frame`)."""
    skew: pd.DataFrame
    """Fair vol vs skew slope over the slope slider's range (:func:`skew_effect`)."""

    @property
    def convexity_premium(self) -> float:
        """Fair vol − ATM vol: positive with an equity skew."""
        return self.fair_vol - self.atm_vol


def skew_slopes() -> list[float]:
    """The slopes of the skew-effect sweep: the slope slider's range in steps of 0.1."""
    b = varswap_bounds()["slope"]
    return sweep_x(b.lo, b.hi, SKEW_SWEEP_POINTS)


def varswap_data(c: VarSwapControls, *, S: float, r: float, q: float) -> VarSwapData:
    """Fair variance, the plotted strip and smile, and the skew-effect sweep."""
    view = price_varswap(c, S=S, r=r, q=q)
    res = view.result
    return VarSwapData(
        fair_variance=res.fair_variance,
        fair_vol=res.fair_vol,
        atm_vol=res.atm_vol,
        forward=res.forward,
        strip=strip_frame(view),
        skew=skew_effect(c, S=S, r=r, q=q, slopes=skew_slopes()),
    )


# ------------------------------------------------------------------ display helpers


def js_number(v: float) -> str:
    """A number as JavaScript's template literal prints it: ``3``, ``2.5``, ``100``."""
    return str(int(v)) if float(v).is_integer() and abs(v) < 1e21 else repr(float(v))


def metric_axis_title(label: str, unit: str, currency: str, metric: ExoticMetric) -> str:
    """Y-axis title of a metric chart: ``Value (USD)`` for the price, else the greek and its
    desk unit (``Gamma (Δdelta per $1 spot)``)."""
    return f"Value ({currency})" if metric == "price" else f"{label} ({unit})"


def years_display(v: float) -> str:
    """A tenor as ``0.50 y`` (React ``${T.toFixed(2)} y``)."""
    return f"{to_fixed(v, 2)} y"


def maturity_display(v: float) -> str:
    """A maturity as ``3 y`` / ``2.5 y`` (React ``${maturity} y``)."""
    return f"{js_number(v)} y"
