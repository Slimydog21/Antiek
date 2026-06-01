"""AFF SPR-09 M4 — the signed-delta aggregator + CI math.

Direct tests of the CI machinery: the point estimate is the mean of the paired
diffs, the CI brackets the point, and the bootstrap is deterministic on its seed.
The non-clamping behaviour is exercised in test_falsifiability.py.
"""

from __future__ import annotations

from compounding.benchmark.aggregate import aggregate_comparison, bootstrap_ci, t_interval
from compounding.benchmark.measure import CostToResolve


def _cost(token):
    return CostToResolve(
        token_cost_usd=token, input_tokens=0, output_tokens=0, sources_fetched=0,
        wall_ms=0.0, novel_insight_yield=0, redundant_rederivations=0,
    )


def test_point_is_mean_of_paired_diffs():
    warm = [_cost(0.30), _cost(0.20), _cost(0.40)]
    cold = [_cost(0.10), _cost(0.10), _cost(0.10)]
    m = aggregate_comparison("c", warm, cold, seed=1).metric("token_cost_usd")
    # diffs = [0.20, 0.10, 0.30]; mean = 0.20
    assert abs(m.delta - 0.20) < 1e-9
    assert abs(m.warm_mean - 0.30) < 1e-9
    assert abs(m.cold_mean - 0.10) < 1e-9
    assert m.n == 3


def test_ci_brackets_point():
    diffs = [0.18, 0.20, 0.22, 0.19, 0.21, 0.205]
    point, lo, hi = bootstrap_ci(diffs, seed=3, resamples=2000)
    assert lo <= point <= hi


def test_bootstrap_deterministic_on_seed():
    diffs = [0.10, 0.30, 0.05, 0.40, 0.02, 0.35]
    a = bootstrap_ci(diffs, seed=99, resamples=3000)
    b = bootstrap_ci(diffs, seed=99, resamples=3000)
    assert a == b


def test_degenerate_constant_diffs_have_zero_width_ci():
    """All-equal diffs → CI collapses to the point (the deterministic mock
    case). No spurious width is manufactured."""
    point, lo, hi = bootstrap_ci([0.0, 0.0, 0.0, 0.0], seed=1, resamples=1000)
    assert point == lo == hi == 0.0


def test_t_interval_brackets_point():
    diffs = [0.18, 0.20, 0.22, 0.19, 0.21]
    point, lo, hi = t_interval(diffs)
    assert lo < point < hi
