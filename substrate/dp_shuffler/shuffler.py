"""Local-DP randomization + shuffler aggregation.

Sprint 19+ substrate plumbing. Implements the local-DP randomized-
response primitive + a simple shuffler aggregator. Real cryptographic
shuffler (e.g. via Mozilla's Prio) is a later integration; this
module provides the math + protocol shape so the surface ships with
the right contract from day one.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


class ShufflerError(Exception):
    pass


@dataclass(frozen=True)
class LocalRandomizer:
    """Local randomized-response primitive. Given a boolean truth
    value, returns a noisy boolean such that the conditional
    probability of returning the true value is e^ε / (1 + e^ε).

    The classical RR construction guarantees ε-LDP."""

    epsilon: float

    def randomize(self, true_value: bool, *, rng: random.Random | None = None) -> bool:
        rng = rng or random.SystemRandom()
        # Probability of returning the truth.
        p_truth = math.exp(self.epsilon) / (1 + math.exp(self.epsilon))
        return true_value if rng.random() < p_truth else not true_value


@dataclass(frozen=True)
class NoisyAggregate:
    """Result of DP aggregation. Carries the noisy estimate + the
    epsilon parameter so consumers can reason about confidence."""

    estimate: float
    epsilon: float
    sample_count: int


def randomized_response(
    true_value: bool,
    epsilon: float,
    *,
    rng: random.Random | None = None,
) -> bool:
    """Convenience wrapper around LocalRandomizer for one-off calls."""
    return LocalRandomizer(epsilon=epsilon).randomize(true_value, rng=rng)


def aggregate_with_dp(
    noisy_responses: list[bool],
    epsilon: float,
) -> NoisyAggregate:
    """Aggregate noisy responses into a debiased estimate of the
    underlying true rate. Classical RR debiasing formula:

      p_truth = (n_true_responses / n) - (1 - p) / (2p - 1)

    where p = e^ε / (1 + e^ε).
    """
    if not noisy_responses:
        return NoisyAggregate(estimate=0.0, epsilon=epsilon, sample_count=0)
    if epsilon <= 0:
        raise ShufflerError(
            f"epsilon must be positive for aggregation, got {epsilon}"
        )
    p = math.exp(epsilon) / (1 + math.exp(epsilon))
    observed = sum(1 for r in noisy_responses if r) / len(noisy_responses)
    # Debias.
    estimate = (observed - (1 - p)) / (2 * p - 1)
    # Clip to [0, 1] for boolean rate interpretation.
    estimate = max(0.0, min(1.0, estimate))
    return NoisyAggregate(
        estimate=estimate,
        epsilon=epsilon,
        sample_count=len(noisy_responses),
    )
