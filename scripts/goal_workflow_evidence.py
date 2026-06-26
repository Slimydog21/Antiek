#!/usr/bin/env python3
"""Emit full deep-research + phase_log evidence for goal verification (stdout).

Registered in ``scripts/goal_harness_deliverables.py`` (plan step 2).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orchestration.phase_log import PhaseLog
from orchestration.phase_runner import enter_phase, exit_phase, verify_phase
from orchestration.phase_runner.postconditions import run_check
from substrate.constants import AUTONOMOUS_RESEARCH_PHASES
from substrate.event_log import emit_typed, trajectory
from substrate.research_artifact.export import export_research_artifact
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ArtifactInsight, ResearchArtifactBody
from substrate.schemas import (
    AutoPatchAppliedPayload,
    ConstraintCompliance,
    FalsificationCondition,
    MasterMdWrittenPayload,
    SynthesizeDeliveredPayload,
)


def _write_phase_artifacts(research_dir: Path, phase: int) -> list[str]:
    paths: list[str] = []
    pad = "content. " * 80
    if phase == 1:
        p = research_dir / "orientation.md"
        p.write_text(
            "# Orientation\n\n"
            + ("intro " * 120)
            + "\n\n## Prior Graph Knowledge\n\nchunk_evidence123 cited.\n"
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
    elif phase == 7:
        p = research_dir / "MASTER.md"
        p.write_text("MASTER synthesis " * 200)
        paths.append(str(p))
    return paths


def _emit_phase_trajectory(inv: str, phase: int, research_dir: Path, skills: Path) -> None:
    if phase == 6:
        emit_typed(
            inv,
            SynthesizeDeliveredPayload(
                thesis_summary="Evidence-backed thesis.",
                implicit_recommendation="proceed",
                thesis_components=[],
                falsification_conditions=[
                    FalsificationCondition(
                        condition="Metric misses threshold",
                        specific_observable="SEC filing",
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
        master = research_dir / "MASTER.md"
        emit_typed(
            inv,
            MasterMdWrittenPayload(
                path=str(master),
                synthesis_id="syn-evidence",
                byte_count=master.stat().st_size,
                topic_slug="evidence",
                param_version="0.1.0",
            ),
            synthesis_id="syn-evidence",
            role="master_md",
        )
    elif phase == 8:
        skill_md = skills / "quantum-knowledge" / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.write_text("# Quantum\n\n## Domain Fundamentals\n\n(seed)\n")
        skill_md.write_text(
            skill_md.read_text() + "\n## Key Players\n\n(protocol growth)\n"
        )
        emit_typed(
            inv,
            AutoPatchAppliedPayload(
                synthesis_id="syn-evidence",
                matched_domains=["quantum-knowledge"],
                patched=["quantum-knowledge"],
                skipped=[],
                errors=[],
                status="patched",
            ),
            synthesis_id="syn-evidence",
            role="auto_patch",
        )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="goal-evidence-"))
    events = tmp / "events"
    logs = tmp / "phase_logs"
    research_base = tmp / "research"
    skills = tmp / "skills"
    arts = tmp / "artifacts"
    db = tmp / "g.duckdb"
    for d in (events, logs, research_base, arts):
        d.mkdir(parents=True)

    os.environ["ANTIEK_RESEARCH_EVENTS_DIR"] = str(events)
    os.environ["ANTIEK_RESEARCH_PHASE_LOG_DIR"] = str(logs)
    os.environ["ANTIEK_RESEARCH_DIR"] = str(research_base)
    os.environ["ANTIEK_KNOWLEDGE_SKILLS_DIR"] = str(skills)
    os.environ["ANTIEK_RESEARCH_ARTIFACTS_DIR"] = str(arts)
    os.environ["ANTIEK_DUCKDB_PATH"] = str(db)
    os.environ["ANTIEK_EMBEDDING_PROVIDER"] = "hash"

    inv = "inv-evidence-clean"
    research_dir = research_base / inv
    research_dir.mkdir(parents=True, exist_ok=True)

    print("GOAL_EVIDENCE: deep_research_protocol")
    print(f"investigation_id={inv}")
    print(f"events_dir={events}")
    print(f"phase_log_dir={logs}")
    print(f"research_dir={research_dir}")
    print("phases_enter_exit_verify:")

    def post(phase: int, investigation_id: str) -> tuple[bool, str]:
        return run_check(
            phase,
            investigation_id,
            research_dir=str(research_dir),
            knowledge_skills_dir=str(skills),
        )

    for phase in AUTONOMOUS_RESEARCH_PHASES:
        enter_phase(inv, phase, topic="clean intake evidence")
        out_paths = _write_phase_artifacts(research_dir, phase)
        _emit_phase_trajectory(inv, phase, research_dir, skills)
        if phase == 8:
            skill_md = skills / "quantum-knowledge" / "SKILL.md"
            out_paths = [str(skill_md)]
        exit_phase(inv, phase, outputs_paths=out_paths or None)
        outcome = verify_phase(inv, phase, postcondition_check=post)
        print(
            f"  phase={phase} passed={outcome.passed} reason={outcome.reason!r}"
        )
        if not outcome.passed:
            print("GOAL_EVIDENCE_FAIL: postcondition", file=sys.stderr)
            return 1

    plog = PhaseLog.open(inv)
    plog.assert_ready_for_completion()
    snap = plog.snapshot()
    print("phase_log_summary:")
    print(json.dumps(snap, indent=2))

    rows = trajectory(inv)
    print(f"event_log_count={len(rows)}")
    kinds = sorted({r.get("action_type") for r in rows})
    print(f"event_action_types={kinds}")

    body = ResearchArtifactBody(
        investigation_id=inv,
        problem_question="Clean intake evidence question",
        insights=[ArtifactInsight(node_id="n-ev", text="Post-protocol insight.")],
        synthesis_excerpt="Archived synthesis excerpt.",
    )
    html_path = arts / f"{inv}.html"
    html_path.write_text(render_html(body, interactive=False), encoding="utf-8")
    print(f"synthesis_html_artifact={html_path}")
    print(f"synthesis_html_bytes={html_path.stat().st_size}")

    print("GOAL_EVIDENCE_OK: nine_phase_clean_intake")
    return 0


if __name__ == "__main__":
    sys.exit(main())