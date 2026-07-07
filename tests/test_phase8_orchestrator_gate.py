"""Phase-8 orchestrator gate wiring tests (GF-3b)."""

from __future__ import annotations

import pytest

import interfaces.research.api  # noqa: F401,E402
import orchestration.loop_one.orchestrator as orch  # noqa: E402
from orchestration.audit import record_phase8_gate_review  # noqa: E402
from orchestration.loop_one.orchestrator import (  # noqa: E402
    PHASE8_CALIBRATION_INVESTIGATION_IDS_ENV,
    InvestigationContext,
    _phase8_gate_from_runtime_env,
    _run_phase_8,
)
from skills.domain.extract import ExtractionResult  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas.events import (  # noqa: E402
    ActionType,
    AutoPatchAppliedPayload,
    ConstraintCompliance,
    Event,
    SkillPatchGateDecidedPayload,
    SynthesizeDeliveredPayload,
    ThesisComponent,
)


@pytest.fixture(autouse=True)
def _isolate_phase8(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    monkeypatch.delenv("ANTIEK_PHASE8_MODE", raising=False)
    monkeypatch.delenv("ANTIEK_PHASE8_EPSILON", raising=False)
    monkeypatch.delenv("ANTIEK_PHASE8_MINIMUM_COHORT_SIZE", raising=False)
    monkeypatch.delenv(PHASE8_CALIBRATION_INVESTIGATION_IDS_ENV, raising=False)


def _ctx(investigation_id: str = "inv-phase8-gate") -> InvestigationContext:
    ctx = InvestigationContext(
        investigation_id=investigation_id,
        question="Will PsiQuantum's photonic qubit roadmap matter?",
    )
    ctx.synthesis = SynthesizeDeliveredPayload(
        thesis_summary="PsiQuantum photonic qubit evidence supports the roadmap.",
        implicit_recommendation="proceed",  # type: ignore[arg-type]
        thesis_components=[
            ThesisComponent(
                claim="PsiQuantum photonic qubit evidence supports the roadmap.",
                confidence="high",
                supporting_chunk_ids=["chunk-1"],
            ),
        ],
        constraint_compliance=ConstraintCompliance(hard_constraints_satisfied=True),
    )
    return ctx


def _last_auto_patch(investigation_id: str) -> AutoPatchAppliedPayload:
    rows = trajectory(investigation_id)
    events = [
        Event.model_validate(row)
        for row in rows
        if row["action_type"] == ActionType.AUTO_PATCH_APPLIED.value
    ]
    assert events
    payload = events[-1].payload
    assert isinstance(payload, AutoPatchAppliedPayload)
    return payload


def _last_gate_decision(investigation_id: str) -> SkillPatchGateDecidedPayload:
    rows = trajectory(investigation_id)
    events = [
        Event.model_validate(row)
        for row in rows
        if row["action_type"] == ActionType.SKILL_PATCH_GATE_DECIDED.value
    ]
    assert events
    payload = events[-1].payload
    assert isinstance(payload, SkillPatchGateDecidedPayload)
    return payload


def _calibration_decision(patch_id: str) -> SkillPatchGateDecidedPayload:
    return SkillPatchGateDecidedPayload(
        synthesis_id="syn-calibration",
        patch_id=patch_id,
        mode="shadow",
        decision="shadow",
        would_accept=False,
        baseline_backtest_score=0.0,
        candidate_backtest_score=0.0,
        delta=0.0,
        epsilon_required=0.02,
        cohort_size=50,
        minimum_cohort_size=50,
        matched_domains=["quantum-computing-knowledge"],
        notes="shadow-mode: patch applied regardless",
    )


def test_phase8_runtime_gate_requires_calibration_ids_for_enforcing(monkeypatch):
    monkeypatch.setenv("ANTIEK_PHASE8_MODE", "enforcing")

    gate = _phase8_gate_from_runtime_env()

    assert gate.mode == "enforcing"
    assert gate.calibration_ready is False
    assert PHASE8_CALIBRATION_INVESTIGATION_IDS_ENV in gate.calibration_notes


def test_phase8_runtime_gate_loads_ready_calibration_status(monkeypatch):
    monkeypatch.setenv("ANTIEK_PHASE8_MODE", "enforcing")
    monkeypatch.setenv(PHASE8_CALIBRATION_INVESTIGATION_IDS_ENV, "inv-calibration")

    for index in range(10):
        patch_id = f"patch-cal-{index}"
        decision_id = emit_typed(
            "inv-calibration",
            _calibration_decision(patch_id),
            synthesis_id="syn-calibration",
            role="phase8_gate",
        )
        assert decision_id is not None
        review_id = record_phase8_gate_review(
            investigation_id="inv-calibration",
            synthesis_id="syn-calibration",
            patch_id=patch_id,
            decision_event_id=decision_id,
            reviewer="operator",
            operator_accept=False,
        )
        assert review_id is not None

    gate = _phase8_gate_from_runtime_env()

    assert gate.mode == "enforcing"
    assert gate.calibration_ready is True
    assert gate.calibration_notes.endswith("current epsilon agreement = 100%")


@pytest.mark.asyncio
async def test_phase8_enforcing_rejects_before_any_skill_write(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_PHASE8_MODE", "enforcing")
    skills_root = tmp_path / "skills"

    ctx = _ctx()
    ok = await _run_phase_8(ctx)

    assert ok is False
    assert ctx.failed_phase == 8
    assert not (skills_root / "quantum-computing-knowledge" / "SKILL.md").exists()

    gate_decision = _last_gate_decision(ctx.investigation_id)
    assert gate_decision.mode == "enforcing"
    assert gate_decision.decision == "reject"
    assert gate_decision.would_accept is False
    assert gate_decision.cohort_size == 0
    assert gate_decision.minimum_cohort_size == 50
    assert "quantum-computing-knowledge" in gate_decision.matched_domains

    payload = _last_auto_patch(ctx.investigation_id)
    assert payload.status == "rejected_by_phase8_gate"
    assert "quantum-computing-knowledge" in payload.matched_domains
    assert payload.patched == []
    assert payload.errors
    assert payload.errors[0]["domain"] == "phase8-gate"


@pytest.mark.asyncio
async def test_phase8_shadow_mode_preserves_mechanical_fallback(tmp_path, monkeypatch):
    def _no_primary_patch(**_kwargs):
        return ExtractionResult(
            domains_matched=["quantum-computing-knowledge"],
            patched_skills={},
        )

    monkeypatch.setattr(orch, "extract_and_patch", _no_primary_patch)
    skills_root = tmp_path / "skills"

    ctx = _ctx("inv-phase8-shadow")
    ok = await _run_phase_8(ctx)

    assert ok is True
    skill_path = skills_root / "quantum-computing-knowledge" / "SKILL.md"
    assert skill_path.exists()
    assert "<!-- synthesis_id: syn-inv-phase8-shadow -->" in skill_path.read_text()
    assert ctx.patched_domains == ["quantum-computing-knowledge"]

    gate_decision = _last_gate_decision(ctx.investigation_id)
    assert gate_decision.mode == "shadow"
    assert gate_decision.decision == "shadow"
    assert gate_decision.would_accept is False
    assert gate_decision.operator_reviewed is False
    assert gate_decision.operator_agreed is None
    assert gate_decision.matched_domains == ["quantum-computing-knowledge"]

    payload = _last_auto_patch(ctx.investigation_id)
    assert payload.status == "patched"
    assert payload.patched == ["quantum-computing-knowledge"]
