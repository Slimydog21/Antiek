"""DP-aware preference learning over private user signals.

Sprint 22+ substrate plumbing (master-spec §16.2 + §13.9).

Shapes binary preference observations (did the operator follow the
dispatch suggestion? did they accept a generated synthesis tier?
did they keep a thought-partner CHALLENGE block?) into a randomized-
response stream, accounts the per-category ε spend against the
configured surface in ``EpsilonRegistry``, and emits a debiased
``LearnedPreference`` consumable downstream by the dispatch router
or the skill-growth Phase 8 gate.

Per master-spec §16.2 binding REJECT canon:
- Total ε per category never exceeds the surface's
  ``epsilon_per_day`` budget (registry-enforced at config time;
  re-enforced here at observation time).
- The stream raises ``PreferenceBudgetExhausted`` when an observation
  would push the cumulative spend past the budget.
- ε ≤ 10 hard cap is enforced by the registry's ``MAX_EPSILON``;
  this module never bypasses it.

This is NOT a deep-learning module. It is a substrate-level wrapper
that:
  1. Records a noisy boolean per observation via ``LocalRandomizer``.
  2. Spends ε per observation against an in-memory accumulator
     keyed by category, checked against the registry's daily budget.
  3. Aggregates into a debiased rate estimate when asked.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .epsilon_registry import EpsilonRegistry, EpsilonRegistryError
from .shuffler import (
    NoisyAggregate,
    aggregate_with_dp,
    randomized_response,
)

ObservationEmitHook = Callable[[
    str,    # category
    bool,   # noisy_value (the randomized output, NOT the truth)
    float,  # per_obs_epsilon
    float,  # cumulative_epsilon_spent
    float,  # category_budget
    str,    # user_id
], None]
"""Optional callback invoked once per accepted observation. Production
wires this to the typed-event broadcaster (see
``substrate/dp_shuffler/event_emit.py``). The truth value is NEVER
passed — only the noisy randomized output, per the local-DP
invariant + master-spec §16.2."""


PREFERENCE_PER_OBS_EPSILON: float = 0.01
"""Per-observation ε spend. Conservative — lets us record up to ~100
observations per category before brushing a default ``low``
sensitivity surface's 4.0 daily budget, or ~1000 per the 10.0 hard
cap."""


class PreferenceBudgetExhausted(Exception):
    """Raised when a category has spent its full ε budget for the day."""


@dataclass(frozen=True)
class PreferenceObservation:
    """A single binary preference signal from a user session."""

    category: str  # e.g. "dispatch_followed_suggestion"
    true_value: bool
    user_id: str = "__operator__"


@dataclass(frozen=True)
class LearnedPreference:
    """Aggregated preference verdict for a single category."""

    category: str
    aggregate: NoisyAggregate
    epsilon_spent: float
    epsilon_budget: float
    user_count: int


@dataclass
class PreferenceLearningStream:
    """In-memory accumulator for noisy preference observations.

    The stream:
      - Consults the registry for each category's per-day ε budget.
      - Tracks cumulative ε per category locally.
      - Stores only the noisy boolean (the truth is discarded after
        randomization — local DP guarantee).
      - Raises ``PreferenceBudgetExhausted`` once the budget would be
        exceeded by the next observation.

    The caller is responsible for resetting the stream daily (real
    deployments persist the cumulative spend across process restarts;
    this scaffold keeps it in-memory).
    """

    registry: EpsilonRegistry
    per_obs_epsilon: float = PREFERENCE_PER_OBS_EPSILON
    on_observation: ObservationEmitHook | None = None
    _noisy_by_category: dict[str, list[bool]] = field(default_factory=dict)
    _users_by_category: dict[str, set[str]] = field(default_factory=dict)
    _spent_by_category: dict[str, float] = field(default_factory=dict)

    def _budget_for(self, category: str) -> float:
        cfg = self.registry.surfaces.get(category)
        if cfg is None:
            raise EpsilonRegistryError(
                f"category {category!r} is not registered. Register the "
                f"surface before recording preference observations."
            )
        return cfg.epsilon_per_day

    def record(self, obs: PreferenceObservation) -> None:
        """Record one observation with per-obs ε spend.

        Raises:
          PreferenceBudgetExhausted: the next observation would push
            the category's cumulative spend past its daily ε budget.
          EpsilonRegistryError: the category is not registered. The
            caller must register the surface explicitly with the
            chosen sensitivity tier — this module does NOT
            auto-register, so the operator's published trust-center
            budget stays the source of truth.
        """
        budget = self._budget_for(obs.category)
        spent = self._spent_by_category.get(obs.category, 0.0)
        if spent + self.per_obs_epsilon > budget:
            raise PreferenceBudgetExhausted(
                f"category {obs.category!r} would exceed daily ε budget "
                f"{budget} (already spent {spent}, next obs costs "
                f"{self.per_obs_epsilon})"
            )
        noisy = randomized_response(obs.true_value, self.per_obs_epsilon)
        self._noisy_by_category.setdefault(obs.category, []).append(noisy)
        self._users_by_category.setdefault(obs.category, set()).add(obs.user_id)
        new_spent = spent + self.per_obs_epsilon
        self._spent_by_category[obs.category] = new_spent

        if self.on_observation is not None:
            # NEVER pass obs.true_value to the hook — only the noisy
            # randomized output. The local-DP invariant + §16.2 require
            # the truth to be discarded after randomization.
            self.on_observation(
                obs.category,
                noisy,
                self.per_obs_epsilon,
                new_spent,
                budget,
                obs.user_id,
            )

    def record_many(self, observations: Iterable[PreferenceObservation]) -> None:
        for o in observations:
            self.record(o)

    def aggregate(self, category: str) -> LearnedPreference:
        """Aggregate the noisy responses into a debiased rate.

        Returns an aggregate with ``aggregate.sample_count == 0`` if
        no observations have been recorded for the category.
        """
        noisy = self._noisy_by_category.get(category, [])
        users = self._users_by_category.get(category, set())
        agg = aggregate_with_dp(noisy, self.per_obs_epsilon)
        spent = self._spent_by_category.get(category, 0.0)
        # If the category is unregistered, surface a budget of 0.0
        # rather than raise — ``aggregate`` is read-only.
        try:
            budget = self._budget_for(category)
        except EpsilonRegistryError:
            budget = 0.0
        return LearnedPreference(
            category=category,
            aggregate=agg,
            epsilon_spent=spent,
            epsilon_budget=budget,
            user_count=len(users),
        )

    def reset_daily(self) -> None:
        """Reset cumulative ε spend at day-boundary. Real deployments
        wire this to a daily cron."""
        self._spent_by_category.clear()
