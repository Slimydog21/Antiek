"""DP-preference-driven dispatch hints (master-spec §13.5 + §16.2).

Bridges the DP preference learning stream (``substrate/dp_shuffler/
preference_learning.py``) to the dispatch router. The bridge produces
ADVISORY hints — never overrides — about which tier to route a role
through, derived from accumulated noisy preference observations.

Design:

  - Each per-role per-quality preference rides in its own DP
    category: ``dispatch_prefer_higher_tier__<role>`` (e.g.
    ``dispatch_prefer_higher_tier__synthesizer``).
  - When the noisy aggregate's debiased estimate exceeds the
    configurable ``THRESHOLD_PROBABILITY`` (default 0.55), the hint
    recommends the role's ``upgrade_tier`` fallback. Below threshold
    the hint stays at the configured tier.
  - Hints carry the ε confidence (low-ε aggregates have wide bounds;
    the caller can choose to weight the hint less).
  - Refuses to recommend without a minimum sample count (default 20)
    — too few observations and the noise drowns any signal.

The router itself does not consume this module; callers that want
the preference-driven behavior call ``recommend_tier()`` and pass the
chosen tier through the existing dispatch surface. This keeps the
dispatch contract clean and the hint surface composable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from substrate.dp_shuffler.preference_learning import (
    PreferenceLearningStream,
)


THRESHOLD_PROBABILITY: float = 0.55
"""Minimum debiased rate to recommend the upgrade tier. Above 0.55:
a clear majority of users prefer the upgrade for this role. Below:
stay with the configured baseline."""

MIN_SAMPLE_COUNT: int = 20
"""Minimum noisy observations before we trust the aggregate enough to
emit a non-default recommendation. Below this, the hint stays at the
fallback tier regardless of the estimate."""


@dataclass(frozen=True)
class TierRecommendation:
    """One advisory verdict about which tier to use for a role."""

    role: str
    recommended_tier: str
    fallback_tier: str
    upgrade_tier: Optional[str]
    debiased_estimate: float
    sample_count: int
    confidence_eps: float  # the per-obs ε used in this aggregate
    reason: str


def category_for_role(role: str) -> str:
    """Canonical DP category name for the per-role upgrade preference.

    Stable across calls so the EpsilonRegistry can register once per
    role and the aggregate accumulates over time."""
    return f"dispatch_prefer_higher_tier__{role}"


def recommend_tier(
    *,
    role: str,
    fallback_tier: str,
    upgrade_tier: Optional[str],
    stream: PreferenceLearningStream,
    threshold: float = THRESHOLD_PROBABILITY,
    min_samples: int = MIN_SAMPLE_COUNT,
) -> TierRecommendation:
    """Recommend a tier for ``role`` using the DP preference aggregate.

    Args:
      role: e.g. ``"synthesizer"`` or ``"parameter_extractor"``.
      fallback_tier: the configured baseline (e.g. ``"pro"``).
      upgrade_tier: the higher tier the recommendation could promote
        to (e.g. ``"synthesis"``). If None, the hint always returns
        the fallback.
      stream: the in-process preference learning stream that has been
        accumulating observations across the calling sessions.
      threshold: rate above which we recommend the upgrade tier.
      min_samples: minimum observations before any non-default hint.

    Returns a ``TierRecommendation`` regardless of state — callers can
    inspect ``reason`` to understand the verdict.
    """
    category = category_for_role(role)
    learned = stream.aggregate(category)
    n = learned.aggregate.sample_count
    estimate = learned.aggregate.estimate

    if upgrade_tier is None:
        return TierRecommendation(
            role=role,
            recommended_tier=fallback_tier,
            fallback_tier=fallback_tier,
            upgrade_tier=None,
            debiased_estimate=estimate,
            sample_count=n,
            confidence_eps=stream.per_obs_epsilon,
            reason="no_upgrade_tier_configured",
        )

    if n < min_samples:
        return TierRecommendation(
            role=role,
            recommended_tier=fallback_tier,
            fallback_tier=fallback_tier,
            upgrade_tier=upgrade_tier,
            debiased_estimate=estimate,
            sample_count=n,
            confidence_eps=stream.per_obs_epsilon,
            reason=(
                f"insufficient_samples: {n} < {min_samples} (DP noise "
                f"dominates signal at this scale)"
            ),
        )

    if estimate >= threshold:
        return TierRecommendation(
            role=role,
            recommended_tier=upgrade_tier,
            fallback_tier=fallback_tier,
            upgrade_tier=upgrade_tier,
            debiased_estimate=estimate,
            sample_count=n,
            confidence_eps=stream.per_obs_epsilon,
            reason=(
                f"estimate={estimate:.3f} ≥ threshold={threshold} "
                f"with n={n}; users prefer upgrade"
            ),
        )

    return TierRecommendation(
        role=role,
        recommended_tier=fallback_tier,
        fallback_tier=fallback_tier,
        upgrade_tier=upgrade_tier,
        debiased_estimate=estimate,
        sample_count=n,
        confidence_eps=stream.per_obs_epsilon,
        reason=(
            f"estimate={estimate:.3f} < threshold={threshold}; "
            f"stay on fallback"
        ),
    )


__all__ = [
    "MIN_SAMPLE_COUNT",
    "THRESHOLD_PROBABILITY",
    "TierRecommendation",
    "category_for_role",
    "recommend_tier",
]
