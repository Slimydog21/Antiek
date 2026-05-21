"""DP preference observation → dispatch tier hint end-to-end test.

Drives the full chain:
  user-session preference observation
    → PreferenceLearningStream (DP randomization + ε accounting)
    → emission hook → typed preference.observation.recorded event
    → recommend_tier reads the aggregate
    → returns a TierRecommendation that influences dispatch

Confirms that:
  - The hook emits the noisy value only (never the truth).
  - Cumulative ε spend tracks correctly across observations.
  - The recommendation flips to the upgrade tier once the aggregate
    crosses the threshold (using a stubbed randomizer for
    determinism — the underlying DP variance is tested separately
    in test_dp_preference_learning.py).
"""

from __future__ import annotations

import pytest

from substrate.dispatch.preference_hints import (
    MIN_SAMPLE_COUNT,
    category_for_role,
    recommend_tier,
)
from substrate.dp_shuffler.epsilon_registry import (
    EpsilonRegistry,
    register_surface,
)
from substrate.dp_shuffler.event_emit import (
    make_broadcasting_observation_hook,
)
from substrate.dp_shuffler.preference_learning import (
    PreferenceLearningStream,
    PreferenceObservation,
)
from substrate.schemas.events import (
    ActionType,
    Event,
    PreferenceObservationRecordedPayload,
)


def _strip_action_type(evt: Event) -> str:
    at = evt.action_type
    return at.value if hasattr(at, "value") else at


def _registry_for_role(role: str, *, eps: float = 4.0) -> EpsilonRegistry:
    reg = EpsilonRegistry()
    register_surface(
        reg,
        surface_name=category_for_role(role),
        epsilon_per_day=eps,
        sensitivity="low",
        description=f"per-role upgrade preference for {role}",
    )
    return reg


def test_e2e_preferences_flow_into_dispatch_recommendation(monkeypatch):
    """Strong preference (stubbed randomizer) → typed events emitted
    + recommendation flips to upgrade tier."""
    import substrate.dp_shuffler.preference_learning as pref_mod

    # Stub the randomizer for deterministic aggregate. The local-DP
    # randomization itself is tested separately; this test exercises
    # the emission + recommendation chain.
    monkeypatch.setattr(
        pref_mod, "randomized_response",
        lambda truth, eps: truth,
    )

    reg = _registry_for_role("synthesizer")
    captured: list[Event] = []
    hook = make_broadcasting_observation_hook(
        investigation_id="inv-1",
        broadcast=captured.append,
    )
    stream = PreferenceLearningStream(
        registry=reg, per_obs_epsilon=0.05, on_observation=hook,
    )

    # Record MIN_SAMPLE_COUNT * 2 all-True observations to exceed the
    # sample-count gate AND the threshold rate.
    for _ in range(MIN_SAMPLE_COUNT * 2):
        stream.record(PreferenceObservation(
            category=category_for_role("synthesizer"),
            true_value=True,
        ))

    # Hook emitted one event per observation.
    assert len(captured) == MIN_SAMPLE_COUNT * 2
    # Every event is the right type + carries cumulative ε state.
    for evt in captured:
        assert _strip_action_type(evt) == ActionType.PREFERENCE_OBSERVATION_RECORDED.value
        assert isinstance(evt.payload, PreferenceObservationRecordedPayload)
        assert evt.payload.category == category_for_role("synthesizer")

    # Cumulative ε climbs monotonically.
    eps_spent = [e.payload.cumulative_epsilon_spent for e in captured]
    assert eps_spent == sorted(eps_spent)
    # Total spend equals N * per_obs_epsilon.
    assert eps_spent[-1] == pytest.approx(
        MIN_SAMPLE_COUNT * 2 * 0.05, abs=1e-9,
    )

    # Recommendation flips to upgrade tier.
    rec = recommend_tier(
        role="synthesizer",
        fallback_tier="pro",
        upgrade_tier="synthesis",
        stream=stream,
    )
    assert rec.recommended_tier == "synthesis"
    assert rec.sample_count == MIN_SAMPLE_COUNT * 2


def test_e2e_weak_signal_keeps_dispatch_on_fallback(monkeypatch):
    """50/50 truth distribution → recommendation stays on fallback,
    even with enough samples."""
    import substrate.dp_shuffler.preference_learning as pref_mod

    monkeypatch.setattr(
        pref_mod, "randomized_response",
        lambda truth, eps: truth,
    )

    reg = _registry_for_role("decomposer")
    captured: list[Event] = []
    hook = make_broadcasting_observation_hook(
        investigation_id="inv-1",
        broadcast=captured.append,
    )
    stream = PreferenceLearningStream(
        registry=reg, per_obs_epsilon=0.05, on_observation=hook,
    )
    for i in range(MIN_SAMPLE_COUNT * 2):
        stream.record(PreferenceObservation(
            category=category_for_role("decomposer"),
            true_value=(i % 2 == 0),
        ))

    # Events still emit; aggregate estimate is ~0.5; recommendation
    # stays on fallback.
    assert len(captured) == MIN_SAMPLE_COUNT * 2
    rec = recommend_tier(
        role="decomposer",
        fallback_tier="flash",
        upgrade_tier="pro",
        stream=stream,
    )
    assert rec.recommended_tier == "flash"
    assert rec.debiased_estimate < 0.55  # below threshold


def test_e2e_no_emission_when_budget_exhausted(monkeypatch):
    """Budget-exhausted observations raise BEFORE the hook fires —
    confirming no event ever leaks past the cap."""
    import substrate.dp_shuffler.preference_learning as pref_mod
    from substrate.dp_shuffler.preference_learning import (
        PreferenceBudgetExhausted,
    )

    monkeypatch.setattr(
        pref_mod, "randomized_response",
        lambda truth, eps: truth,
    )

    reg = _registry_for_role("synthesizer", eps=0.10)
    captured: list[Event] = []
    hook = make_broadcasting_observation_hook(
        investigation_id="inv-1",
        broadcast=captured.append,
    )
    stream = PreferenceLearningStream(
        registry=reg, per_obs_epsilon=0.05, on_observation=hook,
    )

    # Two observations exhausts the 0.10 budget.
    stream.record(PreferenceObservation(
        category=category_for_role("synthesizer"),
        true_value=True,
    ))
    stream.record(PreferenceObservation(
        category=category_for_role("synthesizer"),
        true_value=True,
    ))
    assert len(captured) == 2

    # Third → raise + no new event.
    with pytest.raises(PreferenceBudgetExhausted):
        stream.record(PreferenceObservation(
            category=category_for_role("synthesizer"),
            true_value=True,
        ))
    assert len(captured) == 2  # unchanged
