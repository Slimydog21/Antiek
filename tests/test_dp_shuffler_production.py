"""DP shuffler production routing (§13.3 + §13.7)."""

from __future__ import annotations

import random

import pytest

from substrate.dp_shuffler.production import (
    TelemetryRefused,
    daily_epsilon_used,
    get_production_registry,
    record_telemetry,
    reset_production_registry_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_production_registry_for_tests()
    yield
    reset_production_registry_for_tests()


def _capture():
    captured: list = []

    def emit(payload):
        captured.append(payload)

    return emit, captured


# ── Canonical surfaces ───────────────────────────────────────────────


def test_canonical_surfaces_pre_registered():
    reg = get_production_registry()
    names = {s.surface_name for s in reg.list_surfaces()}
    assert "skill_invocation_frequency" in names
    assert "source_tier_preference" in names
    assert "query_content_telemetry" in names


def test_skill_invocation_ε_is_2():
    reg = get_production_registry()
    config = reg.surfaces["skill_invocation_frequency"]
    assert config.epsilon_per_day == 2.0
    assert config.sensitivity == "low"
    assert config.opt_in_required is False


def test_source_tier_preference_is_opt_in_with_ε_1():
    reg = get_production_registry()
    config = reg.surfaces["source_tier_preference"]
    assert config.epsilon_per_day == 1.0
    assert config.sensitivity == "medium"
    assert config.opt_in_required is True


def test_query_content_is_forbidden():
    reg = get_production_registry()
    config = reg.surfaces["query_content_telemetry"]
    assert config.sensitivity == "forbidden"
    assert config.epsilon_per_day == 0.0


# ── record_telemetry routing ─────────────────────────────────────────


def test_record_telemetry_emits_dp_routed():
    emit, captured = _capture()
    record_telemetry(
        surface_name="skill_invocation_frequency",
        true_value=True,
        emit_event_fn=emit,
        rng=random.Random(42),
    )
    assert len(captured) == 1
    payload = captured[0]
    assert payload.action_type.value == "dp.routed"
    assert payload.surface_name == "skill_invocation_frequency"
    assert payload.epsilon == 2.0
    assert payload.sensitivity == "low"


def test_record_telemetry_refuses_unregistered_surface():
    emit, _ = _capture()
    with pytest.raises(TelemetryRefused, match="not registered"):
        record_telemetry(
            surface_name="unregistered_surface",
            true_value=True,
            emit_event_fn=emit,
        )


def test_record_telemetry_refuses_forbidden_surface():
    emit, _ = _capture()
    with pytest.raises(TelemetryRefused, match="forbidden"):
        record_telemetry(
            surface_name="query_content_telemetry",
            true_value=True,
            emit_event_fn=emit,
        )


def test_record_telemetry_refuses_opt_in_without_grant():
    emit, _ = _capture()
    with pytest.raises(TelemetryRefused, match="opt-in"):
        record_telemetry(
            surface_name="source_tier_preference",
            true_value=True,
            opt_in_granted=False,
            emit_event_fn=emit,
        )


def test_record_telemetry_accepts_opt_in_with_grant():
    emit, captured = _capture()
    record_telemetry(
        surface_name="source_tier_preference",
        true_value=True,
        opt_in_granted=True,
        emit_event_fn=emit,
    )
    assert len(captured) == 1


def test_was_flipped_correctly_recorded():
    """The dp.routed event records whether RR fired the noise coin —
    NOT the value itself. With high ε the truth probability is high
    so most calls return the truth unflipped."""
    emit, captured = _capture()
    for _ in range(50):
        record_telemetry(
            surface_name="skill_invocation_frequency",
            true_value=True,
            emit_event_fn=emit,
            rng=random.SystemRandom(),
        )
    flipped_count = sum(1 for p in captured if p.was_flipped)
    # With ε=2.0, p_truth ≈ 0.88; expected flips ≈ 50 * 0.12 ≈ 6.
    # Allow generous tolerance for the stochastic test.
    assert 0 <= flipped_count <= 25


# ── Aggregator helper ────────────────────────────────────────────────


def test_daily_epsilon_used_sums_correctly():
    """The aggregator sums ε per surface per day from the dp.routed
    stream — what the Trust Center publishes."""
    events = [
        {
            "emitted_at": "2026-05-22T10:00:00Z",
            "payload": {
                "action_type": "dp.routed",
                "surface_name": "skill_invocation_frequency",
                "epsilon": 2.0,
                "sensitivity": "low",
                "was_flipped": False,
                "stage": "local_randomized",
            },
        },
        {
            "emitted_at": "2026-05-22T11:00:00Z",
            "payload": {
                "action_type": "dp.routed",
                "surface_name": "skill_invocation_frequency",
                "epsilon": 2.0,
                "sensitivity": "low",
                "was_flipped": True,
                "stage": "local_randomized",
            },
        },
        {
            "emitted_at": "2026-05-22T12:00:00Z",
            "payload": {
                "action_type": "dp.routed",
                "surface_name": "source_tier_preference",
                "epsilon": 1.0,
                "sensitivity": "medium",
                "was_flipped": False,
                "stage": "local_randomized",
            },
        },
        # Different day — should not count
        {
            "emitted_at": "2026-05-21T10:00:00Z",
            "payload": {
                "action_type": "dp.routed",
                "surface_name": "skill_invocation_frequency",
                "epsilon": 2.0,
                "sensitivity": "low",
                "was_flipped": False,
                "stage": "local_randomized",
            },
        },
    ]
    total = daily_epsilon_used(
        surface_name="skill_invocation_frequency",
        events=events,
        day_iso="2026-05-22",
    )
    assert total == 4.0  # 2 * 2.0
    total_other = daily_epsilon_used(
        surface_name="source_tier_preference",
        events=events,
        day_iso="2026-05-22",
    )
    assert total_other == 1.0
