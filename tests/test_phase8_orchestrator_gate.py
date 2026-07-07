"""Phase-8 orchestrator gate wiring tests (GF-3b)."""

from __future__ import annotations

import pytest

import interfaces.research.api  # noqa: F401,E402
import orchestration.loop_one.orchestrator as orch  # noqa: E402
from orchestration.loop_one.orchestrator import (  # noqa: E402
    InvestigationContext,
    _run_phase_8,
)
from skills.domain.extract import ExtractionResult  # noqa: E402
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas.events import (  # noqa: E402
    ActionType,
    AutoPatchAppliedPayload,
    ConstraintCompliance,
    Event,
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


@pytest.mark.asyncio
async def test_phase8_enforcing_rejects_before_any_skill_write(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_PHASE8_MODE", "enforcing")
    skills_root = tmp_path / "skills"

    ctx = _ctx()
    ok = await _run_phase_8(ctx)

    assert ok is False
    assert ctx.failed_phase == 8
    assert not (skills_root / "quantum-computing-knowledge" / "SKILL.md").exists()

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

    payload = _last_auto_patch(ctx.investigation_id)
    assert payload.status == "patched"
    assert payload.patched == ["quantum-computing-knowledge"]
