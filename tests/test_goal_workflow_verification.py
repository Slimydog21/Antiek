"""Goal harness — deep research protocol, HTML KB projection, reading surface.

Complements ``tests/test_goal_harness_deliverables.py`` (entrypoint registry).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from interfaces.reading.kb_artifact import consume_kb_artifact
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


def _apply_phase_outputs(
    inv: str,
    phase: int,
    research_dir: Path,
    skills: Path,
) -> list[str]:
    """Simulate phase artifacts only when that phase exits (clean intake)."""
    paths: list[str] = []
    pad = "content. " * 80
    if phase == 1:
        p = research_dir / "orientation.md"
        p.write_text(
            "# Orientation\n\n"
            + ("intro " * 120)
            + "\n\n## Prior Graph Knowledge\n\nchunk_goal123 cited.\n"
        )
        paths.append(str(p))
    elif phase == 2:
        for name in (
            "round1-technical.md",
            "round1-competitive.md",
            "round1-strategic.md",
        ):
            fp = research_dir / name
            fp.write_text(pad)
            paths.append(str(fp))
    elif phase == 3:
        p = research_dir / "round1-critique.md"
        p.write_text("Critique covers technical, competitive, strategic.\n" + pad)
        paths.append(str(p))
    elif phase == 4:
        p = research_dir / "round2-technical.md"
        p.write_text(pad)
        paths.append(str(p))
    elif phase == 5:
        p = research_dir / "round2-critique.md"
        p.write_text("Round 2 critique " * 40)
        paths.append(str(p))
    elif phase == 6:
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
    elif phase == 7:
        p = research_dir / "MASTER.md"
        p.write_text("MASTER synthesis " * 200)
        paths.append(str(p))
        emit_typed(
            inv,
            MasterMdWrittenPayload(
                path=str(p),
                synthesis_id="syn-goal",
                byte_count=p.stat().st_size,
                topic_slug="goal",
                param_version="0.1.0",
            ),
            synthesis_id="syn-goal",
            role="master_md",
        )
    elif phase == 8:
        skill_md = skills / "quantum-knowledge" / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.write_text("# Quantum\n\n## Domain Fundamentals\n\n(seed)\n")
        skill_md.write_text(
            skill_md.read_text() + "\n## Key Players\n\n(growth)\n"
        )
        paths.append(str(skill_md))
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
    return paths


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


def test_reading_kb_artifact_load_render_condense(tmp_path):
    body = ResearchArtifactBody(
        investigation_id="inv-read-kb",
        problem_question="Reading consumes HTML projections",
        insights=[
            ArtifactInsight(node_id="node-42", text="Claim with provenance."),
        ],
        synthesis_excerpt="Short synthesis for reader.",
    )
    html_path = tmp_path / "inv-read-kb.html"
    html_path.write_text(render_html(body, interactive=False), encoding="utf-8")
    view = consume_kb_artifact(html_path)
    assert view.investigation_id == "inv-read-kb"
    assert view.script_free is True
    assert view.findings[0][0] == "node-42"
    assert view.content_hash == body.content_hash()
    assert view.html_bytes > 0


@pytest.fixture(autouse=True)
def _goal_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))


def test_nine_phase_runner_clean_intake_logs_verified(tmp_path):
    inv = "inv-goal-9phase"
    research_dir = tmp_path / "research" / inv
    research_dir.mkdir(parents=True)
    assert not any(research_dir.iterdir()), "intake must start empty"
    skills = tmp_path / "skills"

    def post(phase: int, investigation_id: str) -> tuple[bool, str]:
        return run_check(
            phase,
            investigation_id,
            research_dir=str(research_dir),
            knowledge_skills_dir=str(skills),
        )

    trace: list[dict[str, object]] = []
    for phase in AUTONOMOUS_RESEARCH_PHASES:
        enter_phase(inv, phase, topic="goal nine-phase clean")
        out_paths = _apply_phase_outputs(inv, phase, research_dir, skills)
        exit_phase(inv, phase, outputs_paths=out_paths or None)
        outcome = verify_phase(inv, phase, postcondition_check=post)
        trace.append(
            {
                "phase": phase,
                "passed": outcome.passed,
                "reason": outcome.reason,
                "outputs": out_paths,
            }
        )
        assert outcome.passed is True, f"phase {phase}: {outcome.reason}"

    plog = PhaseLog.open(inv)
    for phase in AUTONOMOUS_RESEARCH_PHASES:
        plog.assert_phase_completed(phase)
    plog.assert_ready_for_completion()
    snap = plog.snapshot()
    assert len(trace) == 9
    assert snap.get("phases", {}).get("8", {}).get("verified") is True
    # Embeddable evidence blob for goal harness logs
    print("PHASE_TRACE_JSON=" + json.dumps(trace))
    print("PHASE_LOG_SNAPSHOT_JSON=" + json.dumps(snap))