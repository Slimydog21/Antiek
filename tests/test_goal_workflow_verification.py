"""Goal harness — deep research protocol, HTML KB projection, reading surface."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from acquisition.snapshot.reader_html import build_reader_snapshot, sanitize_html_fragment
from orchestration.phase_log import PhaseLog
from orchestration.phase_runner import enter_phase, exit_phase, verify_phase
from orchestration.phase_runner.postconditions import run_check
from substrate.constants import AUTONOMOUS_RESEARCH_PHASES
from substrate.event_log import emit_typed
from substrate.research_artifact.projection_verify import verify_kb_projection
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ArtifactInsight, ResearchArtifactBody
from substrate.schemas import (
    AutoPatchAppliedPayload,
    ConstraintCompliance,
    FalsificationCondition,
    MasterMdWrittenPayload,
    SynthesizeDeliveredPayload,
)


def _seed_research_dir(base: Path) -> str:
    base.mkdir(parents=True, exist_ok=True)
    pad = "content. " * 80
    (base / "orientation.md").write_text(
        "# Orientation\n\n"
        + ("intro " * 120)
        + "\n\n## Prior Graph Knowledge\n\nchunk_goal123 cited.\n"
    )
    for name in (
        "round1-technical.md",
        "round1-competitive.md",
        "round1-strategic.md",
    ):
        (base / name).write_text(pad)
    (base / "round1-critique.md").write_text(
        "Critique covers technical, competitive, strategic.\n" + pad
    )
    (base / "round2-technical.md").write_text(pad)
    (base / "round2-critique.md").write_text("Round 2 critique " * 40)
    (base / "MASTER.md").write_text("MASTER synthesis " * 200)
    return str(base)


def test_kb_html_projection_script_free_roundtrip():
    body = ResearchArtifactBody(
        investigation_id="inv-goal-html",
        problem_question="How does HTML standardize condensed research?",
        insights=[
            ArtifactInsight(
                node_id="n-1", text="Graph-sourced finding.", confidence="high"
            ),
        ],
        synthesis_excerpt="Condensed synthesis for the knowledge base.",
        agent_notes=["Operator note from reading session."],
    )
    result = verify_kb_projection(body)
    assert result.ok is True, result.detail
    html = render_html(body, interactive=False)
    assert "Graph-sourced finding." in html
    assert 'type="application/json"' in html


def test_reading_snapshot_sanitizes_and_renders():
    dirty = "<p>Claim</p><script>evil()</script>"
    clean = sanitize_html_fragment(dirty)
    assert "<script>" not in clean
    page = build_reader_snapshot(
        source_url="https://example.com/paper",
        document_id="doc-goal-1",
        ip_holder_id=None,
        main_html=clean,
        ingested_at="2026-06-26T00:00:00Z",
        title="Goal reading fixture",
    )
    assert "doc-goal-1" in page
    assert "Claim" in page
    assert "<script>" not in page


@pytest.fixture(autouse=True)
def _goal_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))


def test_nine_phase_runner_logs_verified_transitions(tmp_path):
    inv = "inv-goal-9phase"
    research_dir = _seed_research_dir(tmp_path / "research" / inv)
    skills = tmp_path / "skills"
    (skills / "quantum-knowledge").mkdir(parents=True)
    skill_md = skills / "quantum-knowledge" / "SKILL.md"
    skill_md.write_text("# Quantum\n\n## Domain Fundamentals\n\n(seed)\n")

    emit_typed(
        inv,
        SynthesizeDeliveredPayload(
            thesis_summary="Goal thesis is supported.",
            implicit_recommendation="proceed",
            thesis_components=[],
            falsification_conditions=[
                FalsificationCondition(
                    condition="Revenue misses plan",
                    specific_observable="10-K filing",
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
        policy_id="stub/stub",
    )
    emit_typed(
        inv,
        MasterMdWrittenPayload(
            path=os.path.join(research_dir, "MASTER.md"),
            synthesis_id="syn-goal",
            byte_count=8000,
            topic_slug="goal",
            param_version="0.1.0",
        ),
        synthesis_id="syn-goal",
        role="master_md",
    )
    emit_typed(
        inv,
        AutoPatchAppliedPayload(
            synthesis_id="syn-goal",
            matched_domains=["quantum-knowledge"],
            patched=["quantum-knowledge"],
            skipped=[],
            errors=[],
            status="patched",
        ),
        synthesis_id="syn-goal",
        role="auto_patch",
    )
    skill_md.write_text(skill_md.read_text() + "\n## Key Players\n\n(growth)\n")

    def post(phase: int, investigation_id: str) -> tuple[bool, str]:
        return run_check(
            phase,
            investigation_id,
            research_dir=research_dir,
            knowledge_skills_dir=str(skills),
        )

    for phase in AUTONOMOUS_RESEARCH_PHASES:
        enter_phase(inv, phase, topic="goal nine-phase")
        exit_phase(inv, phase, outputs_paths=[str(skill_md)] if phase == 8 else None)
        outcome = verify_phase(inv, phase, postcondition_check=post)
        assert outcome.passed is True, f"phase {phase}: {outcome.reason}"

    plog = PhaseLog.open(inv)
    for phase in AUTONOMOUS_RESEARCH_PHASES:
        plog.assert_phase_completed(phase)
    plog.assert_ready_for_completion()