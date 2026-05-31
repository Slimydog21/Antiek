"""Phase-6 quality-signal wiring (Foundation v2 SPR-02, M1 + M4).

Gates:
- G2 (groundedness and scorer_error): a forced scorer error SURFACES
  (emits groundedness.failed + logs) and the loop CONTINUES — the old
  except-pass swallow is gone.
- G6 (groundedness and emits_signal): a Phase-6 scoring pass emits BOTH
  groundedness.scored AND rubric.scored, and neither blocks.
"""

from __future__ import annotations

import pytest

# Import the API package FIRST so create_app() runs before the
# orchestrator submodule is imported — mirrors test_loop_one_orchestrator
# and sidesteps the package-init circular import that bites a
# bare ``import orchestration.loop_one.orchestrator``.
import interfaces.research.api  # noqa: F401,E402
from orchestration.loop_one.orchestrator import (  # noqa: E402
    InvestigationContext,
    _score_phase_6_synthesis,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas.events import (
    ActionType,
    ConstraintCompliance,
    SynthesizeDeliveredPayload,
    ThesisComponent,
)


@pytest.fixture(autouse=True)
def _isolate_events(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    # No DB → groundedness resolver yields no chunk text; the scorer still
    # runs and emits (claims score as honestly-ungrounded). That is the
    # offline-safe behaviour we want under test.
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "absent.duckdb"))
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)


def _ctx() -> InvestigationContext:
    ctx = InvestigationContext(investigation_id="inv-spr02", question="q?")
    ctx.synthesis = SynthesizeDeliveredPayload(
        thesis_summary="The radar achieves 24 dB of gain.",
        implicit_recommendation="proceed",  # type: ignore[arg-type]
        thesis_components=[
            ThesisComponent(
                claim="The radar achieves 24 dB of gain.",
                confidence="high",
                supporting_chunk_ids=["chunk-1"],
            ),
        ],
        constraint_compliance=ConstraintCompliance(hard_constraints_satisfied=True),
        conviction_level=0.8,
    )
    return ctx


def _action_types(investigation_id: str) -> list[str]:
    return [r.get("action_type") for r in trajectory(investigation_id)]


def test_groundedness_scorer_error_surfaces_and_loop_continues(monkeypatch, caplog):
    """G2: inject a raising scorer. The crash must SURFACE (failure event
    + log) and the loop must CONTINUE (the helper returns normally)."""
    import substrate.synthesis_rubric as rubric_mod

    def _boom(_payload):
        raise RuntimeError("forced scorer error")

    # Make the style-rubric scorer raise. The helper imports
    # score_synthesis from substrate.synthesis_rubric inside the function,
    # so patching the package attribute is what the import resolves to.
    monkeypatch.setattr(rubric_mod, "score_synthesis", _boom)

    ctx = _ctx()
    # Loop continues: the helper does NOT raise (non-blocking).
    _score_phase_6_synthesis(ctx)  # must not raise

    types = _action_types(ctx.investigation_id)
    # The signal did NOT silently vanish: a failure event surfaced.
    assert ActionType.GROUNDEDNESS_FAILED.value in types, types
    # And it was logged (surfaced), not swallowed.
    assert any("scorer crashed" in r.message for r in caplog.records)


def test_groundedness_scorer_error_emits_failure_payload(monkeypatch):
    """G2 detail: the failure event names the stage + carries the error."""
    import substrate.synthesis_rubric as rubric_mod

    def _boom(_payload):
        raise ValueError("kaboom")

    monkeypatch.setattr(rubric_mod, "score_synthesis", _boom)
    ctx = _ctx()
    _score_phase_6_synthesis(ctx)

    rows = [
        r for r in trajectory(ctx.investigation_id)
        if r.get("action_type") == ActionType.GROUNDEDNESS_FAILED.value
    ]
    assert rows, "expected a groundedness.failed event"
    payload = rows[0]["payload"]
    assert payload["stage"] == "rubric"
    assert payload["error_type"] == "ValueError"
    assert "kaboom" in payload["error"]


def test_groundedness_emits_signal_alongside_rubric_non_blocking():
    """G6: a Phase-6 scoring pass emits BOTH groundedness.scored AND
    rubric.scored, and the helper returns normally (non-blocking)."""
    ctx = _ctx()
    _score_phase_6_synthesis(ctx)  # must not raise

    types = _action_types(ctx.investigation_id)
    assert ActionType.GROUNDEDNESS_SCORED.value in types, types
    assert ActionType.RUBRIC_SCORED.value in types, types


def test_groundedness_scored_payload_shape():
    """The emitted groundedness.scored carries the truth-axis fields:
    a per-synthesis score, claim coverage, the backend, and per-claim
    verdicts."""
    ctx = _ctx()
    _score_phase_6_synthesis(ctx)
    rows = [
        r for r in trajectory(ctx.investigation_id)
        if r.get("action_type") == ActionType.GROUNDEDNESS_SCORED.value
    ]
    assert rows
    payload = rows[0]["payload"]
    assert payload["backend"] == "lexical"
    assert payload["total_claims"] == 1
    assert 0.0 <= payload["groundedness_score"] <= 1.0
    assert payload["per_claim"]
    # The style rubric is still emitted AND labeled SECONDARY.
    rubric_rows = [
        r for r in trajectory(ctx.investigation_id)
        if r.get("action_type") == ActionType.RUBRIC_SCORED.value
    ]
    assert rubric_rows
    assert "SECONDARY" in rubric_rows[0]["payload"]["notes"]
