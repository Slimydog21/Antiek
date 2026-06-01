"""AFF SPR-09 M4 — signed-delta aggregation with a confidence interval.

Aggregates n paired arm-runs into a per-metric SIGNED delta = warm_mean −
cold_mean, with a confidence interval over the n runs. The variance is reported,
never hidden (rigor #3): a single warm-vs-cold pair is anecdote, so the CI is
computed from the n runs, not hard-coded.

THE NON-NEGOTIABLE (the one cardinal sin guard): the delta is NEVER abs()'d,
clamped, or floored at zero. A positive delta (warm MORE expensive than cold) is
a legitimate falsification of the flywheel and is emitted as a positive number.
``test_positive_delta_reported`` injects warm > cold synthetic runs and asserts a
strictly positive reported delta — if this code clamped, that test would fail.

Default mock CI (§2): a 10 000-resample bias-corrected percentile bootstrap, 95%,
seeded for reproducibility. A t-interval is also available
(``method="t"``) for the small-n case; the README documents which and why. The
SAME seed reproduces the SAME deltas (M4 acceptance) — the bootstrap RNG is
seeded off the run seed + the metric name so each metric's resample is
independent yet deterministic.
"""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from typing import List, Sequence, Tuple

from .measure import CostToResolve, METRIC_NAMES
from .result_schema import ArmComparison, MetricDelta

DEFAULT_BOOTSTRAP_RESAMPLES = 10_000
DEFAULT_CI = 0.95


def _metric_value(cost: CostToResolve, metric: str) -> float:
    return float(getattr(cost, metric))


def _metric_seed(seed: int, metric: str) -> int:
    """A stable per-(seed, metric) RNG seed. Process-independent (unlike builtin
    ``hash``) so the bootstrap CI reproduces across CI runs."""
    h = hashlib.sha256(f"{seed}:{metric}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _paired_diffs(
    warm: Sequence[CostToResolve],
    cold: Sequence[CostToResolve],
    metric: str,
) -> List[float]:
    """Per-run warm − cold differences for one metric. Runs are paired by index
    (run i warm vs run i cold), so the difference cancels per-run shared noise —
    the paired design the §2 confounds-held protocol assumes."""
    n = min(len(warm), len(cold))
    return [_metric_value(warm[i], metric) - _metric_value(cold[i], metric) for i in range(n)]


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _normal_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation). Used for
    the bias-correction z-quantiles and the percentile lookups."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile of an already-sorted sequence. ``q`` in
    [0, 1]."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = q * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def bootstrap_ci(
    diffs: Sequence[float],
    *,
    confidence: float = DEFAULT_CI,
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = 0,
) -> Tuple[float, float, float]:
    """Bias-corrected percentile bootstrap CI of the MEAN of ``diffs``.

    Returns ``(point, ci_low, ci_high)`` where ``point`` is the observed mean
    (signed, NEVER clamped). The bias correction (z0) shifts the percentile
    lookups to account for skew in the resample distribution — the §2
    "bias-corrected bootstrap". Seeded off ``seed`` so the same inputs reproduce
    the same interval (M4 determinism)."""
    n = len(diffs)
    point = statistics.fmean(diffs) if n else 0.0
    if n <= 1:
        return point, point, point

    rng = random.Random(seed)
    means: List[float] = []
    for _ in range(resamples):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.fmean(sample))
    means.sort()

    # Bias correction z0: the normal quantile of the fraction of resample means
    # below the observed point estimate. Falls back to the plain percentile
    # method when every resample is identical (degenerate, zero-variance data).
    below = sum(1 for m in means if m < point)
    prop = below / resamples
    if prop <= 0.0 or prop >= 1.0:
        z0 = 0.0
    else:
        z0 = _normal_ppf(prop)

    alpha = 1.0 - confidence
    z_lo = _normal_ppf(alpha / 2.0)
    z_hi = _normal_ppf(1.0 - alpha / 2.0)
    q_lo = _normal_cdf(2 * z0 + z_lo)
    q_hi = _normal_cdf(2 * z0 + z_hi)

    ci_low = _percentile(means, q_lo)
    ci_high = _percentile(means, q_hi)
    # Guard ordering only (numerical), never the SIGN or magnitude of the point.
    if ci_low > ci_high:
        ci_low, ci_high = ci_high, ci_low
    return point, ci_low, ci_high


def t_interval(diffs: Sequence[float], *, confidence: float = DEFAULT_CI) -> Tuple[float, float, float]:
    """Student-t CI of the mean of ``diffs``. Returns ``(point, ci_low,
    ci_high)``. Available for the small-n case where a bootstrap of few distinct
    values under-covers; the README documents the choice."""
    n = len(diffs)
    point = statistics.fmean(diffs) if n else 0.0
    if n <= 1:
        return point, point, point
    sd = statistics.stdev(diffs)
    se = sd / math.sqrt(n)
    # t critical via the Cornish-Fisher-free route: for n≥2 we approximate the
    # t-quantile from the normal with a small-sample inflation. For exactness on
    # tiny n the bootstrap is the default; this is the documented alternative.
    z = _normal_ppf(1.0 - (1.0 - confidence) / 2.0)
    # Welch-style inflation factor approximating t_{df}/z for df=n-1.
    df = n - 1
    inflate = 1.0 + (z * z + 1.0) / (4.0 * df)
    half = z * inflate * se
    return point, point - half, point + half


def _delta_for_metric(
    metric: str,
    warm: Sequence[CostToResolve],
    cold: Sequence[CostToResolve],
    *,
    method: str,
    confidence: float,
    resamples: int,
    seed: int,
) -> MetricDelta:
    diffs = _paired_diffs(warm, cold, metric)
    n = len(diffs)
    warm_mean = statistics.fmean(_metric_value(c, metric) for c in warm[:n]) if n else 0.0
    cold_mean = statistics.fmean(_metric_value(c, metric) for c in cold[:n]) if n else 0.0
    if method == "t":
        point, lo, hi = t_interval(diffs, confidence=confidence)
    else:
        # Per-metric independent-yet-deterministic RNG seed. ``hashlib`` (not
        # builtin ``hash``, which is salted per-process) so the same seed
        # reproduces the same CI bounds ACROSS processes — the M4 determinism
        # guarantee survives a fresh CI run.
        point, lo, hi = bootstrap_ci(
            diffs, confidence=confidence, resamples=resamples,
            seed=_metric_seed(seed, metric),
        )
    return MetricDelta(
        metric=metric,
        delta=point,
        ci_low=lo,
        ci_high=hi,
        warm_mean=warm_mean,
        cold_mean=cold_mean,
        n=n,
    )


def aggregate_comparison(
    label: str,
    warm: Sequence[CostToResolve],
    cold: Sequence[CostToResolve],
    *,
    metrics: Sequence[str] = METRIC_NAMES,
    method: str = "bootstrap",
    confidence: float = DEFAULT_CI,
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = 0,
) -> ArmComparison:
    """Aggregate one arm pair (``warm`` vs ``cold``) into a per-metric signed
    delta + CI. ``warm`` here is the experimental arm of the comparison and
    ``cold`` the baseline — for the validity control, pass the irrelevant arm as
    ``warm`` and the cold arm as ``cold`` so its delta has the same warm−cold
    sign convention as the headline."""
    deltas = [
        _delta_for_metric(
            m, warm, cold, method=method, confidence=confidence,
            resamples=resamples, seed=seed,
        )
        for m in metrics
    ]
    return ArmComparison(label=label, metrics=deltas)
