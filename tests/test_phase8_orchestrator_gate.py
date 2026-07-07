"""Phase-8 orchestrator gate wiring tests (GF-3b)."""

from __future__ import annotations

import pytest

import interfaces.research.api  # noqa: F401,E402
import orchestration.loop_one.orchestrator as orch  # noqa: E402
from compounding.skill_growth import (  # noqa: E402
    CandidateBacktestReplay,
    CandidateSkillOverlay,
    SkillPatchGate,
    evaluate_candidate_replay_for_gate,
)
from middleware.backtest import BacktestReport  # noqa: E402
from orchestration.audit import record_phase8_gate_review  # noqa: E402
from orchestration.loop_one.orchestrator import (  # noqa: E402
    PHASE8_CALIBRATION_INVESTIGATION_IDS_ENV,
    PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS_ENV,
    PHASE8_REPLAY_OVERLAY_PARENT_ENV,
    InvestigationContext,
    _phase8_candidate_replay_evaluation,
    _phase8_gate_decide_from_replay_evaluation,
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


def _report(synthesis_id: str, *, outcome: str = "confirmed") -> BacktestReport:
    return BacktestReport(
        synthesis_id=synthesis_id,
        synthesis_timestamp="2026-01-01T00:00:00Z",
        target_question="Will X work?",
        status="passed",
        implicit_recommendation="proceed",
        substrate_manifest_counts={},
        added_edges_since=0,
        superseded_edges_since=0,
        cited_edges_now_superseded=(),
        chunks_retired_downward=(),
        outcomes=({"thesis_outcomes": [{"outcome": outcome}]},),
    )


def _ready_replay_evaluation(tmp_path):
    overlay = CandidateSkillOverlay(
        baseline_skills_root=tmp_path / "baseline-skills",
        overlay_skills_root=tmp_path / "overlay-skills",
        matched_domains=("quantum-computing-knowledge",),
        patched_domains=("quantum-computing-knowledge",),
        skipped_domains=(),
        status="patched",
        patch_result={"status": "patched"},
    )
    replay = CandidateBacktestReplay(
        overlay=overlay,
        heldout_synthesis_ids=("candidate-1", "candidate-2"),
        reports=(
            _report("candidate-1", outcome="confirmed"),
            _report("candidate-2", outcome="confirmed"),
        ),
        errors=(),
        status="replayed",
    )
    return evaluate_candidate_replay_for_gate(
        baseline_reports=(
            _report("baseline-1", outcome="partially_confirmed"),
            _report("baseline-2", outcome="partially_confirmed"),
        ),
        candidate_replay=replay,
        minimum_graded_outcomes=2,
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


def test_phase8_gate_decision_uses_replay_evaluation_scores(tmp_path):
    gate = SkillPatchGate(mode="enforcing", epsilon=0.01, minimum_cohort_size=2)
    evaluation = _ready_replay_evaluation(tmp_path)

    outcome = _phase8_gate_decide_from_replay_evaluation(gate, evaluation)

    assert outcome.decision == "accept"
    assert outcome.baseline_backtest_score == 0.5
    assert outcome.candidate_backtest_score == 1.0
    assert outcome.cohort_size == 2
    assert outcome.delta == 0.5


def test_phase8_replay_provider_reports_unavailable_runner_when_configured(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS_ENV,
        "heldout-1, heldout-2",
    )
    monkeypatch.setenv(PHASE8_REPLAY_OVERLAY_PARENT_ENV, str(tmp_path / "overlays"))
    ctx = _ctx("inv-phase8-replay-provider")
    synthesis_row = {
        "synthesis_id": "syn-inv-phase8-replay-provider",
        "investigation_id": ctx.investigation_id,
        "target_question": ctx.question,
        "implicit_recommendation": ctx.synthesis.implicit_recommendation,
        "thesis": {"thesis_summary": ctx.synthesis.thesis_summary},
    }

    evaluation = _phase8_candidate_replay_evaluation(
        ctx=ctx,
        synthesis_row=synthesis_row,
        matched_domains=["quantum-computing-knowledge"],
    )

    assert evaluation is not None
    assert evaluation.ready_for_gate is False
    assert evaluation.replay.status == "runner_unavailable"
    assert evaluation.replay.heldout_synthesis_ids == ("heldout-1", "heldout-2")
    assert "production candidate replay runner is not wired" in evaluation.notes
    assert "replay workspace:" in evaluation.notes
    assert evaluation.replay.overlay.overlay_skills_root.is_relative_to(
        tmp_path / "overlays"
    )


def test_phase8_replay_provider_loads_baseline_reports_when_db_configured(
    tmp_path,
    monkeypatch,
):
    from tests.test_skill_growth_replay import _seed_archived_synthesis

    db_path = tmp_path / "graph.duckdb"
    _seed_archived_synthesis(db_path, "heldout-ok")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv(
        PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS_ENV,
        "heldout-ok, heldout-missing",
    )
    monkeypatch.setenv(PHASE8_REPLAY_OVERLAY_PARENT_ENV, str(tmp_path / "overlays"))
    ctx = _ctx("inv-phase8-replay-db")
    synthesis_row = {
        "synthesis_id": "syn-inv-phase8-replay-db",
        "investigation_id": ctx.investigation_id,
        "target_question": ctx.question,
        "implicit_recommendation": ctx.synthesis.implicit_recommendation,
        "thesis": {"thesis_summary": ctx.synthesis.thesis_summary},
    }

    evaluation = _phase8_candidate_replay_evaluation(
        ctx=ctx,
        synthesis_row=synthesis_row,
        matched_domains=["quantum-computing-knowledge"],
    )

    assert evaluation is not None
    assert evaluation.comparison.baseline_score == 1.0
    assert "baseline_graded=1" in evaluation.notes
    assert "heldout-missing" in evaluation.notes
    assert "baseline load errors" in evaluation.notes
    assert evaluation.replay.overlay.overlay_skills_root.is_relative_to(
        tmp_path / "overlays"
    )


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
async def test_phase8_uses_candidate_replay_evaluation_when_available(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ANTIEK_PHASE8_MINIMUM_COHORT_SIZE", "2")

    def _no_primary_patch(**_kwargs):
        return ExtractionResult(
            domains_matched=["quantum-computing-knowledge"],
            patched_skills={},
        )

    evaluation = _ready_replay_evaluation(tmp_path)

    def _evaluation_provider(**kwargs):
        assert kwargs["matched_domains"] == ["quantum-computing-knowledge"]
        assert kwargs["synthesis_row"]["synthesis_id"] == "syn-inv-phase8-replay"
        return evaluation

    monkeypatch.setattr(orch, "extract_and_patch", _no_primary_patch)
    monkeypatch.setattr(
        orch,
        "_phase8_candidate_replay_evaluation",
        _evaluation_provider,
    )

    ctx = _ctx("inv-phase8-replay")
    ok = await _run_phase_8(ctx)

    assert ok is True
    gate_decision = _last_gate_decision(ctx.investigation_id)
    assert gate_decision.baseline_backtest_score == 0.5
    assert gate_decision.candidate_backtest_score == 1.0
    assert gate_decision.cohort_size == 2
    assert gate_decision.delta == 0.5


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
