"""Tests for orchestration/invariants/deep_research_complete.py (SPR-DRL-01)."""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from orchestration.invariants.deep_research_complete import (  # noqa: E402
    DeepResearchIncompleteError,
    assert_deep_research_complete,
    check_deep_research_complete,
)
from orchestration.phase_runner import enter_phase, exit_phase, verify_phase  # noqa: E402
from orchestration.phase_runner.postconditions import default_research_dir  # noqa: E402
from substrate.event_log import emit_typed  # noqa: E402
from substrate.schemas import (  # noqa: E402
    AutoPatchAppliedPayload,
    ConstraintCompliance,
    FalsificationCondition,
    InvestigationCompletedPayload,
    MasterMdWrittenPayload,
    SynthesizeDeliveredPayload,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    yield


def _emit_synthesize(investigation_id: str) -> None:
    emit_typed(
        investigation_id,
        SynthesizeDeliveredPayload(
            thesis_summary="Thesis holds under current evidence.",
            implicit_recommendation="proceed",
            thesis_components=[],
            falsification_conditions=[
                FalsificationCondition(
                    condition="Revenue growth falls below 10% YoY",
                    specific_observable="Annual report disclosure",
                ),
            ],
            execution_risks=[],
            constraint_compliance=ConstraintCompliance(
                hard_constraints_satisfied=True,
                soft_constraints_violated=[],
                violations_justified=[],
            ),
            reasoning_paths_used=[],
            constraint_loop_status="single_pass",  # type: ignore[arg-type]
        ),
        role="synthesizer",
        policy_id="test/stub",
    )


def _verify_phases_6_8(investigation_id: str) -> None:
    for phase in range(1, 6):
        enter_phase(investigation_id, phase)
        exit_phase(investigation_id, phase)
        verify_phase(investigation_id, phase)
    for phase in (6, 7, 8):
        enter_phase(investigation_id, phase)
        exit_phase(investigation_id, phase)
        verify_phase(investigation_id, phase)


def _emit_full_loop_one_tail(investigation_id: str, *, research_dir: str) -> None:
    _emit_synthesize(investigation_id)
    emit_typed(
        investigation_id,
        MasterMdWrittenPayload(
            path=os.path.join(research_dir, "MASTER.md"),
            synthesis_id=f"syn-{investigation_id}",
            byte_count=4096,
            topic_slug="topic",
            param_version="0.1.0",
        ),
        synthesis_id=f"syn-{investigation_id}",
        role="master_md",
    )
    emit_typed(
        investigation_id,
        AutoPatchAppliedPayload(
            synthesis_id=f"syn-{investigation_id}",
            matched_domains=["topic-knowledge"],
            patched=["topic-knowledge"],
            skipped=[],
            errors=[],
            status="patched",
        ),
        synthesis_id=f"syn-{investigation_id}",
        role="auto_patch",
    )
    _verify_phases_6_8(investigation_id)


def test_drw_only_trajectory_fails_without_synthesis():
    """MOCK gather path: no synthesize.delivered, no investigation.completed."""
    ok, reason = check_deep_research_complete("inv-drw-only")
    assert ok is False
    assert "investigation.completed" in reason
    assert "phase 6" in reason


def test_loop_one_pre_emit_passes_without_completed_event(tmp_path):
    inv = "inv-pre-emit"
    research_dir = default_research_dir(inv)
    os.makedirs(research_dir, exist_ok=True)
    _emit_full_loop_one_tail(inv, research_dir=research_dir)

    ok, _ = check_deep_research_complete(
        inv, research_dir=research_dir, require_terminal_event=False,
    )
    assert ok is True


def test_retrospective_requires_investigation_completed(tmp_path):
    inv = "inv-retro"
    research_dir = default_research_dir(inv)
    os.makedirs(research_dir, exist_ok=True)
    _emit_full_loop_one_tail(inv, research_dir=research_dir)

    ok, reason = check_deep_research_complete(inv, research_dir=research_dir)
    assert ok is False
    assert "investigation.completed" in reason


def test_full_trajectory_passes(tmp_path):
    inv = "inv-full"
    research_dir = default_research_dir(inv)
    os.makedirs(research_dir, exist_ok=True)
    _emit_full_loop_one_tail(inv, research_dir=research_dir)
    emit_typed(
        inv,
        InvestigationCompletedPayload(
            thesis_summary="Thesis holds under current evidence.",
            implicit_recommendation="proceed",
            constraint_loop_status="single_pass",  # type: ignore[arg-type]
            constraint_loop_iterations=1,
            master_md_path=os.path.join(research_dir, "MASTER.md"),
            domains_patched=["topic-knowledge"],
            total_phases_verified=8,
        ),
        role="orchestrator",
        policy_id="test/stub",
    )

    ok, reason = check_deep_research_complete(inv, research_dir=research_dir)
    assert ok is True
    assert "deep research complete" in reason


def test_assert_raises_deep_research_incomplete_error():
    with pytest.raises(DeepResearchIncompleteError, match="inv-assert"):
        assert_deep_research_complete("inv-assert")