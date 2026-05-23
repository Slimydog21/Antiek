"""Creator earnings distribution — median, p90, long-tail mass.

Per Sprint 25+ doc §2 marketplace metrics: 'creator earnings
distribution (median, p90, long-tail mass)'. Long-tail mass is the
share of total earnings concentrated in the bottom half of creators
(by individual earnings rank) — a healthy marketplace has a heavier
long tail than a winner-takes-all platform.

Input: per-creator paid-cents-in-window. Pure function; window
selection is the caller's responsibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class EarningsBucket:
    """One bucket in the histogram by USD-cents range."""

    lower_cents: int  # inclusive
    upper_cents: int  # exclusive; -1 = open-ended top
    creator_count: int


@dataclass(frozen=True)
class CreatorEarningsDistribution:
    creator_count: int
    total_paid_cents: int
    median_cents: int
    p90_cents: int
    p99_cents: int
    long_tail_mass: float  # share of total earned by bottom-50% creators
    buckets: tuple[EarningsBucket, ...]


def _percentile(sorted_vals: list[int], p: float) -> int:
    """Linear-interpolation percentile. p is in [0, 100]."""
    if not sorted_vals:
        return 0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (p / 100.0) * (len(sorted_vals) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return int(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


_DEFAULT_BUCKETS_CENTS: tuple[tuple[int, int], ...] = (
    (0, 100),         # below $1
    (100, 1_000),     # $1-9.99 (below §9.5 payout threshold)
    (1_000, 5_000),   # $10-49.99 (threshold)
    (5_000, 25_000),  # $50-249.99
    (25_000, 100_000),  # $250-999.99
    (100_000, -1),    # $1000+
)


def compute_creator_distribution(
    creator_paid_cents: dict[str, int],
    *,
    bucket_edges: Optional[tuple[tuple[int, int], ...]] = None,
) -> CreatorEarningsDistribution:
    """Compute the distribution given per-creator paid-cents.

    Args:
        creator_paid_cents: creator_id → cents paid out in the window
        bucket_edges: optional override; (lower_inclusive, upper_exclusive)
                      pairs. Use -1 for upper to mean open-ended.
    """
    if not creator_paid_cents:
        return CreatorEarningsDistribution(
            creator_count=0,
            total_paid_cents=0,
            median_cents=0,
            p90_cents=0,
            p99_cents=0,
            long_tail_mass=0.0,
            buckets=(),
        )

    sorted_vals = sorted(creator_paid_cents.values())
    total = sum(sorted_vals)

    median = _percentile(sorted_vals, 50)
    p90 = _percentile(sorted_vals, 90)
    p99 = _percentile(sorted_vals, 99)

    # Long-tail mass: bottom-50% creators' share of total earnings.
    bottom_half_count = len(sorted_vals) // 2
    bottom_half_sum = sum(sorted_vals[:bottom_half_count])
    long_tail_mass = (bottom_half_sum / total) if total > 0 else 0.0

    edges = bucket_edges if bucket_edges is not None else _DEFAULT_BUCKETS_CENTS
    buckets: list[EarningsBucket] = []
    for lo, hi in edges:
        if hi == -1:
            count = sum(1 for v in sorted_vals if v >= lo)
        else:
            count = sum(1 for v in sorted_vals if lo <= v < hi)
        buckets.append(EarningsBucket(
            lower_cents=lo, upper_cents=hi, creator_count=count,
        ))

    return CreatorEarningsDistribution(
        creator_count=len(sorted_vals),
        total_paid_cents=total,
        median_cents=median,
        p90_cents=p90,
        p99_cents=p99,
        long_tail_mass=long_tail_mass,
        buckets=tuple(buckets),
    )
