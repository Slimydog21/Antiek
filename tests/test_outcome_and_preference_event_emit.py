"""Outcome + DP preference event-emission tests.

Covers:
  - POST /outcomes → emits typed ``outcome.recorded`` event
  - DP preference observation → emits typed
    ``preference.observation.recorded`` event with NOISY value only
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
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


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-outcome-emit-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class _RecordingBroadcaster:
    def __init__(self) -> None:
        self.events: list = []

    async def broadcast(self, event) -> None:
        self.events.append(event)


def _seed_synthesis(db_path: str, synthesis_id: str) -> None:
    from runtime.db_lock import connect_write

    with connect_write(db_path, purpose="test:seed_synthesis") as con:
        con.execute(
            "INSERT INTO syntheses ("
            "synthesis_id, target_question, synthesis_timestamp, "
            "status, implicit_recommendation"
            ") VALUES (?, ?, CURRENT_TIMESTAMP, 'draft', 'undetermined')",
            [synthesis_id, "test question"],
        )


# ── Outcome event emission ─────────────────────────────────────────


def _strip_action_type(evt) -> str:
    at = evt.action_type
    return at.value if hasattr(at, "value") else at


def test_post_outcome_emits_typed_event(isolated_db):
    """POST /outcomes records the row AND broadcasts the typed
    ``outcome.recorded`` event."""
    app = create_app(register_wrestling=False)
    bus = _RecordingBroadcaster()
    app.state.broadcaster = bus
    client = TestClient(app)
    synth_id = f"syn-{uuid.uuid4().hex[:10]}"
    _seed_synthesis(isolated_db, synth_id)

    resp = client.post(
        "/outcomes",
        json={
            "synthesis_id": synth_id,
            "thesis_outcomes": [
                {"thesis_claim": "x", "outcome": "confirmed", "evidence": ""},
            ],
            "notes": "graded validated",
        },
    )
    assert resp.status_code == 200, resp.text
    outcome_events = [
        e for e in bus.events
        if _strip_action_type(e) == "outcome.recorded"
    ]
    assert len(outcome_events) == 1
    evt = outcome_events[0]
    assert evt.synthesis_id == synth_id
    assert evt.payload.observer == "__operator__"
    assert evt.payload.thesis_outcomes[0].outcome == "confirmed"


def test_post_outcome_emits_even_with_no_outcomes_lists(isolated_db):
    """A bare outcome (notes only) still emits the typed event."""
    app = create_app(register_wrestling=False)
    bus = _RecordingBroadcaster()
    app.state.broadcaster = bus
    client = TestClient(app)
    synth_id = f"syn-{uuid.uuid4().hex[:10]}"
    _seed_synthesis(isolated_db, synth_id)

    resp = client.post(
        "/outcomes",
        json={"synthesis_id": synth_id, "notes": "indeterminate observation"},
    )
    assert resp.status_code == 200
    outcome_events = [
        e for e in bus.events
        if _strip_action_type(e) == "outcome.recorded"
    ]
    assert len(outcome_events) == 1
    assert outcome_events[0].payload.notes == "indeterminate observation"


# ── DP preference event emission ───────────────────────────────────


def _registry_with(name: str, eps: float = 1.0):
    reg = EpsilonRegistry()
    register_surface(
        reg, surface_name=name, epsilon_per_day=eps,
        sensitivity="low", description="test",
    )
    return reg


def test_preference_stream_emits_per_observation():
    """Each accepted observation flows through the hook → typed event."""
    reg = _registry_with("dispatch_followed", eps=1.0)
    captured: list[Event] = []
    hook = make_broadcasting_observation_hook(
        investigation_id="inv-1",
        broadcast=captured.append,
    )
    stream = PreferenceLearningStream(
        registry=reg, per_obs_epsilon=0.01, on_observation=hook,
    )

    stream.record(
        PreferenceObservation(category="dispatch_followed", true_value=True),
    )
    stream.record(
        PreferenceObservation(category="dispatch_followed", true_value=False),
    )

    assert len(captured) == 2
    for evt in captured:
        assert isinstance(evt.payload, PreferenceObservationRecordedPayload)
        assert evt.action_type == ActionType.PREFERENCE_OBSERVATION_RECORDED.value
        assert evt.payload.category == "dispatch_followed"


def test_preference_event_carries_only_noisy_value():
    """The hook MUST NOT see the truth value — only the noisy
    randomized output. Enforced at the source in
    ``PreferenceLearningStream.record``."""
    # Headroom in the budget so floating-point summation doesn't
    # trip the cap before the test completes.
    reg = _registry_with("cat", eps=2.0)
    captured: list[Event] = []
    hook = make_broadcasting_observation_hook(
        investigation_id="inv-1",
        broadcast=captured.append,
    )
    stream = PreferenceLearningStream(
        registry=reg, per_obs_epsilon=0.01, on_observation=hook,
    )

    # Record many of the same truth value; randomized response means
    # we expect mixed True/False noisy values out — i.e. the hook is
    # NOT receiving the truth directly.
    for _ in range(100):
        stream.record(
            PreferenceObservation(category="cat", true_value=True),
        )
    noisy_values = [evt.payload.noisy_value for evt in captured]
    # If the truth had leaked, all 100 would be True. The randomized
    # response with ε=0.01 should produce at most ~50% truth-rate
    # (very high noise). We just require that NOT all values are True
    # — confirming randomization is happening and the hook never saw
    # the truth.
    assert not all(noisy_values), (
        "Hook is seeing the truth value — local-DP invariant violated"
    )


def test_preference_event_tracks_cumulative_spend():
    """Cumulative ε spend climbs monotonically per category."""
    reg = _registry_with("cat", eps=1.0)
    captured: list[Event] = []
    hook = make_broadcasting_observation_hook(
        investigation_id="inv-1",
        broadcast=captured.append,
    )
    stream = PreferenceLearningStream(
        registry=reg, per_obs_epsilon=0.05, on_observation=hook,
    )

    for _ in range(3):
        stream.record(
            PreferenceObservation(category="cat", true_value=True),
        )
    spent_values = [e.payload.cumulative_epsilon_spent for e in captured]
    assert spent_values == pytest.approx([0.05, 0.10, 0.15], abs=1e-9)


def test_preference_hook_not_called_when_budget_exhausted():
    """When the budget overflows, the observation is rejected BEFORE
    the hook fires — no event leaks."""
    reg = _registry_with("cat", eps=0.02)
    captured: list[Event] = []
    hook = make_broadcasting_observation_hook(
        investigation_id="inv-1",
        broadcast=captured.append,
    )
    stream = PreferenceLearningStream(
        registry=reg, per_obs_epsilon=0.01, on_observation=hook,
    )
    # Fill the budget — 2 observations allowed.
    stream.record(PreferenceObservation(category="cat", true_value=True))
    stream.record(PreferenceObservation(category="cat", true_value=False))
    assert len(captured) == 2

    # Third observation must raise + emit nothing.
    from substrate.dp_shuffler.preference_learning import (
        PreferenceBudgetExhausted,
    )
    with pytest.raises(PreferenceBudgetExhausted):
        stream.record(
            PreferenceObservation(category="cat", true_value=True),
        )
    assert len(captured) == 2  # unchanged
