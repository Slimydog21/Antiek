"""Tests for orchestration/phase_runner/postconditions.py
(Sprint 8 day 2).

Coverage — file-artifact phases (1-5, 7 fallback):

1. Phase 1: missing file / too short / missing section / no citations /
   happy path.
2. Phase 2: all 3 files present + sized OK; missing one rejected; too-small.
3. Phase 3: missing file / missing dimensions / happy.
4. Phase 4: no round2 files; round2-critique excluded from match;
   happy with one deep dive.
5. Phase 5: missing / too small / happy.

Coverage — trajectory phases (6, 8):

6. Phase 6: no event rejected; converged + non-vacuous → passed;
   converged + vacuous (empty / single-word / stub) → rejected;
   max_iterations_reached → rejected.
7. Phase 8: AUTO_PATCH_APPLIED with patched → passed; AUTO_PATCH_APPLIED
   with status=no_match → rejected; skill-file mtime fallback path.

8. Phase 7: MASTER_MD_WRITTEN event → passed; file fallback < floor
   rejected; file fallback OK; neither → rejected.

9. Phase 9: delegates to PhaseLog; raises until ready.

10. run_check dispatcher: unknown phase rejected; kwarg filtering.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from orchestration.phase_log import PhaseLog  # noqa: E402
from orchestration.phase_runner.postconditions import (  # noqa: E402
    CHECKS,
    check_phase_1,
    check_phase_2,
    check_phase_3,
    check_phase_4,
    check_phase_5,
    check_phase_6,
    check_phase_7,
    check_phase_8,
    check_phase_9,
    run_check,
)
from substrate.event_log import emit_typed  # noqa: E402
from substrate.schemas import (  # noqa: E402
    AutoPatchAppliedPayload,
    ConstraintCompliance,
    FalsificationCondition,
    MasterMdWrittenPayload,
    SynthesizeDeliveredPayload,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    yield


@pytest.fixture
def research_dir(tmp_path) -> str:
    d = tmp_path / "research"
    d.mkdir()
    return str(d)


def _write(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# 1. Phase 1
# ---------------------------------------------------------------------------


def test_phase_1_missing_file(research_dir):
    ok, reason = check_phase_1("inv-p1", research_dir=research_dir)
    assert ok is False
    assert "not found" in reason


def test_phase_1_too_short(research_dir):
    _write(os.path.join(research_dir, "orientation.md"), "too short")
    ok, reason = check_phase_1("inv-p1", research_dir=research_dir)
    assert ok is False
    assert "too short" in reason


def test_phase_1_missing_section(research_dir):
    body = "# Orientation\n\n" + ("filler text " * 50)  # ≥ 500 chars
    _write(os.path.join(research_dir, "orientation.md"), body)
    ok, reason = check_phase_1("inv-p1", research_dir=research_dir)
    assert ok is False
    assert "Prior Graph Knowledge" in reason


def test_phase_1_section_with_no_citations(research_dir):
    body = (
        "# Orientation\n\n## Prior Graph Knowledge\n\n"
        + ("no citations here. " * 30)
    )
    _write(os.path.join(research_dir, "orientation.md"), body)
    ok, _ = check_phase_1("inv-p1", research_dir=research_dir)
    assert ok is False


def test_phase_1_happy_with_regex_citation(research_dir):
    body = (
        "# Orientation\n\n"
        + ("introductory prose. " * 30)
        + "\n\n## Prior Graph Knowledge\n\n"
        + "Based on chunk_abc123 we know X."
    )
    _write(os.path.join(research_dir, "orientation.md"), body)
    ok, reason = check_phase_1("inv-p1", research_dir=research_dir)
    assert ok is True
    assert "OK" in reason


# ---------------------------------------------------------------------------
# 2. Phase 2
# ---------------------------------------------------------------------------


def _write_round1(research_dir):
    body = "round 1 dimension content. " * 50  # > 500 bytes
    for name in ("round1-technical.md", "round1-competitive.md",
                 "round1-strategic.md"):
        _write(os.path.join(research_dir, name), body)


def test_phase_2_all_present_ok(research_dir):
    _write_round1(research_dir)
    ok, _ = check_phase_2("inv-p2", research_dir=research_dir)
    assert ok is True


def test_phase_2_missing_one_rejected(research_dir):
    _write_round1(research_dir)
    os.remove(os.path.join(research_dir, "round1-strategic.md"))
    ok, reason = check_phase_2("inv-p2", research_dir=research_dir)
    assert ok is False
    assert "missing" in reason


def test_phase_2_too_small_rejected(research_dir):
    _write_round1(research_dir)
    _write(os.path.join(research_dir, "round1-strategic.md"), "tiny")
    ok, reason = check_phase_2("inv-p2", research_dir=research_dir)
    assert ok is False
    assert "≤500 bytes" in reason


# ---------------------------------------------------------------------------
# 3. Phase 3
# ---------------------------------------------------------------------------


def test_phase_3_missing(research_dir):
    ok, reason = check_phase_3("inv-p3", research_dir=research_dir)
    assert ok is False
    assert "not found" in reason


def test_phase_3_missing_dimensions(research_dir):
    _write(os.path.join(research_dir, "round1-critique.md"),
           "Critique mentioning only technical dimension.")
    ok, reason = check_phase_3("inv-p3", research_dir=research_dir)
    assert ok is False
    assert "competitive" in reason and "strategic" in reason


def test_phase_3_happy(research_dir):
    body = "Critique covers technical, competitive, and strategic dimensions."
    _write(os.path.join(research_dir, "round1-critique.md"), body)
    ok, _ = check_phase_3("inv-p3", research_dir=research_dir)
    assert ok is True


# ---------------------------------------------------------------------------
# 4. Phase 4
# ---------------------------------------------------------------------------


def test_phase_4_no_round2_files(research_dir):
    ok, reason = check_phase_4("inv-p4", research_dir=research_dir)
    assert ok is False


def test_phase_4_critique_excluded(research_dir):
    """round2-critique.md belongs to Phase 5, NOT Phase 4."""
    _write(os.path.join(research_dir, "round2-critique.md"),
           "critique body " * 100)
    ok, _ = check_phase_4("inv-p4", research_dir=research_dir)
    assert ok is False


def test_phase_4_happy(research_dir):
    _write(os.path.join(research_dir, "round2-technical.md"),
           "deep dive content. " * 50)
    ok, _ = check_phase_4("inv-p4", research_dir=research_dir)
    assert ok is True


# ---------------------------------------------------------------------------
# 5. Phase 5
# ---------------------------------------------------------------------------


def test_phase_5_missing(research_dir):
    ok, _ = check_phase_5("inv-p5", research_dir=research_dir)
    assert ok is False


def test_phase_5_too_small(research_dir):
    _write(os.path.join(research_dir, "round2-critique.md"), "tiny")
    ok, _ = check_phase_5("inv-p5", research_dir=research_dir)
    assert ok is False


def test_phase_5_happy(research_dir):
    _write(os.path.join(research_dir, "round2-critique.md"),
           "round 2 critique body " * 50)
    ok, _ = check_phase_5("inv-p5", research_dir=research_dir)
    assert ok is True


# ---------------------------------------------------------------------------
# 6. Phase 6 (trajectory-based)
# ---------------------------------------------------------------------------


def _emit_synthesize_delivered(
    investigation_id: str, *,
    status: str = "single_pass",
    falsifications: list | None = None,
) -> None:
    if falsifications is None:
        falsifications = [
            FalsificationCondition(
                condition="ARR growth falls below 80% YoY",
                specific_observable="Q4 financial disclosure",
            ),
        ]
    emit_typed(
        investigation_id,
        SynthesizeDeliveredPayload(
            thesis_summary="X is well-supported.",
            implicit_recommendation="proceed",
            thesis_components=[],
            falsification_conditions=falsifications,
            execution_risks=[],
            constraint_compliance=ConstraintCompliance(
                hard_constraints_satisfied=True,
                soft_constraints_violated=[],
                violations_justified=[],
            ),
            reasoning_paths_used=[],
            constraint_loop_status=status,  # type: ignore[arg-type]
        ),
        role="synthesizer", policy_id="stub/stub",
    )


def test_phase_6_no_event():
    ok, reason = check_phase_6("inv-p6n")
    assert ok is False
    assert "no synthesize.delivered" in reason


def test_phase_6_passed_with_non_vacuous():
    _emit_synthesize_delivered("inv-p6o", status="passed")
    ok, reason = check_phase_6("inv-p6o")
    assert ok is True
    assert "passed" in reason


def test_phase_6_single_pass_with_non_vacuous():
    _emit_synthesize_delivered("inv-p6s", status="single_pass")
    ok, _ = check_phase_6("inv-p6s")
    assert ok is True


def test_phase_6_max_iterations_rejected():
    _emit_synthesize_delivered("inv-p6m", status="max_iterations_reached")
    ok, reason = check_phase_6("inv-p6m")
    assert ok is False


def test_phase_6_vacuous_empty_rejected():
    _emit_synthesize_delivered("inv-p6v", falsifications=[])
    ok, reason = check_phase_6("inv-p6v")
    assert ok is False
    assert "vacuous" in reason


def test_phase_6_vacuous_single_word_rejected():
    _emit_synthesize_delivered("inv-p6sw", falsifications=[
        FalsificationCondition(condition="wrong", specific_observable="ob1"),
        FalsificationCondition(condition="broken", specific_observable="ob2"),
    ])
    ok, _ = check_phase_6("inv-p6sw")
    assert ok is False


def test_phase_6_vacuous_stub_rejected():
    _emit_synthesize_delivered("inv-p6stub", falsifications=[
        FalsificationCondition(
            condition="Stub answer placeholder",
            specific_observable="stub",
        ),
    ])
    ok, _ = check_phase_6("inv-p6stub")
    assert ok is False


def test_phase_6_insufficient_evidence_with_empty_falsifications_accepted():
    """Regression for 2026-05-18 H2.5 incident.

    The synthesizer's contract: when it cannot produce a defensible
    thesis with non-vacuous falsifications, signal
    ``insufficient_evidence`` and emit empty falsification_conditions.
    This is a converged terminal state — the substrate ran, tried,
    and the answer is "no defensible thesis." Phase 6 must accept it,
    or Loop 1 has no way to end an underdetermined investigation
    cleanly. The parser at roles/synthesizer/parser.py already honors
    this escape hatch; this test locks in that the postcondition
    matches."""
    emit_typed(
        "inv-p6ie",
        SynthesizeDeliveredPayload(
            thesis_summary="",
            implicit_recommendation="insufficient_evidence",
            thesis_components=[],
            falsification_conditions=[],  # empty — would normally be vacuous
            execution_risks=[],
            constraint_compliance=ConstraintCompliance(
                hard_constraints_satisfied=False,
                soft_constraints_violated=[],
                violations_justified=[],
            ),
            reasoning_paths_used=[],
            constraint_loop_status="single_pass",  # type: ignore[arg-type]
        ),
        role="synthesizer", policy_id="stub/stub",
    )
    ok, reason = check_phase_6("inv-p6ie")
    assert ok is True
    assert "insufficient_evidence" in reason


# ---------------------------------------------------------------------------
# 7. Phase 7
# ---------------------------------------------------------------------------


def test_phase_7_via_event(research_dir):
    emit_typed(
        "inv-p7e",
        MasterMdWrittenPayload(
            path="/some/path/MASTER.md",
            synthesis_id="syn-1",
            byte_count=4096,
            topic_slug="t",
            param_version="0.1.0",
        ),
        synthesis_id="syn-1",
        role="master_md",
    )
    ok, reason = check_phase_7("inv-p7e", research_dir=research_dir)
    assert ok is True
    assert "master_md_written" in reason


def test_phase_7_file_fallback_ok(research_dir):
    _write(os.path.join(research_dir, "MASTER.md"), "x" * 3000)
    ok, _ = check_phase_7("inv-p7f", research_dir=research_dir)
    assert ok is True


def test_phase_7_file_too_small_rejected(research_dir):
    _write(os.path.join(research_dir, "MASTER.md"), "tiny")
    ok, reason = check_phase_7("inv-p7s", research_dir=research_dir)
    assert ok is False
    assert "too small" in reason


def test_phase_7_neither_event_nor_file_rejected(research_dir):
    ok, _ = check_phase_7("inv-p7none", research_dir=research_dir)
    assert ok is False


# ---------------------------------------------------------------------------
# 8. Phase 8 (KEYSTONE)
# ---------------------------------------------------------------------------


def test_phase_8_auto_patch_with_patched_passes(tmp_path):
    emit_typed(
        "inv-p8e",
        AutoPatchAppliedPayload(
            synthesis_id="syn-1",
            matched_domains=["quantum-knowledge"],
            patched=["quantum-knowledge"],
            skipped=[],
            errors=[],
            status="patched",
        ),
        synthesis_id="syn-1",
        role="auto_patch",
    )
    ok, reason = check_phase_8(
        "inv-p8e", knowledge_skills_dir=str(tmp_path / "skills"),
    )
    assert ok is True
    assert "auto_patch_applied" in reason


def test_phase_8_no_match_rejected_when_no_file_growth(tmp_path):
    """status=no_match with no skill files → rejected."""
    emit_typed(
        "inv-p8nm",
        AutoPatchAppliedPayload(
            synthesis_id="syn-1",
            matched_domains=[],
            patched=[],  # no domains patched
            skipped=[],
            errors=[],
            status="no_match",
        ),
        synthesis_id="syn-1",
        role="auto_patch",
    )
    ok, reason = check_phase_8(
        "inv-p8nm", knowledge_skills_dir=str(tmp_path / "skills-nm"),
    )
    assert ok is False


def test_phase_8_insufficient_evidence_short_circuits_pass(tmp_path):
    """2026-05-18 H2.5: when upstream synthesis was insufficient_evidence,
    Phase 8 cannot produce non-empty patched lists (no defensible
    thesis → no knowledge to extract). Phase 8 short-circuits to PASS
    so the substrate can end an underdetermined investigation cleanly.
    Mirrors Phase 6's same-sprint escape hatch."""
    emit_typed(
        "inv-p8ie",
        SynthesizeDeliveredPayload(
            thesis_summary="No qualifying evidence on the question.",
            implicit_recommendation="insufficient_evidence",
            thesis_components=[],
            falsification_conditions=[],
            execution_risks=[],
            constraint_compliance=ConstraintCompliance(
                hard_constraints_satisfied=False,
                soft_constraints_violated=[],
                violations_justified=[],
            ),
            reasoning_paths_used=[],
            constraint_loop_status="single_pass",  # type: ignore[arg-type]
        ),
        role="synthesizer", policy_id="stub/stub",
    )
    # Phase 8 is asked to verify with NO auto_patch_applied event and
    # NO skill files. Pre-H2.5 this would fail; post-H2.5 the
    # insufficient_evidence verdict short-circuits to pass before the
    # A/B checks run.
    ok, reason = check_phase_8(
        "inv-p8ie", knowledge_skills_dir=str(tmp_path / "skills-ie"),
    )
    assert ok is True
    assert "insufficient_evidence" in reason


def test_phase_8_skill_file_mtime_fallback(tmp_path):
    """No AUTO_PATCH_APPLIED event but a skill file modified recently
    → passes (mtime fallback).

    History (H4.5, 2026-05-18): this test previously constructed
    ``started_at`` as a naive datetime via
    ``datetime.fromtimestamp(past)``, which the buggy postcondition's
    naive-timestamp comparison silently treated as local time —
    round-tripping the test's UTC epoch through the operator's
    timezone offset. The bug masked itself by accepting the malformed
    cutoff and producing the expected boolean result. After the fix,
    ``started_at`` is explicitly UTC-aware, and the postcondition
    accepts that without ambiguity."""
    skills_root = tmp_path / "skills"
    quantum_dir = skills_root / "quantum-knowledge"
    quantum_dir.mkdir(parents=True)
    skill_file = quantum_dir / "SKILL.md"
    skill_file.write_text("# Quantum\n\n## Findings\n")

    # Use a past investigation start (1 hour ago) so the file's NOW
    # mtime is strictly after it. UTC-aware throughout.
    past = datetime.now(UTC).timestamp() - 3600
    os.utime(str(skill_file), (past + 1800, past + 1800))  # 30 min after start
    started_at = datetime.fromtimestamp(past, tz=UTC)

    ok, reason = check_phase_8(
        "inv-p8mtime",
        knowledge_skills_dir=str(skills_root),
        investigation_started_at=started_at,
    )
    assert ok is True
    assert "modified after" in reason


def test_phase_8_naive_started_at_treated_as_utc(tmp_path):
    """Regression for the H4.5 timezone bug: a naive
    ``investigation_started_at`` must be interpreted as UTC, not as
    local time. Pre-fix, ``.timestamp()`` on a naive datetime used
    local time, which on a non-UTC machine shifted the cutoff by the
    local UTC offset and made path B falsely pass even when the
    seed file's mtime predated the real investigation start."""
    import time as _time
    skills_root = tmp_path / "skills"
    quantum_dir = skills_root / "quantum-knowledge"
    quantum_dir.mkdir(parents=True)
    skill_file = quantum_dir / "SKILL.md"
    skill_file.write_text("# Quantum\n\n## Findings\n")

    # Seed file's mtime is exactly NOW.
    now_ts = _time.time()
    os.utime(str(skill_file), (now_ts, now_ts))

    # Pass a naive datetime FIVE MINUTES IN THE FUTURE (UTC). Should
    # be interpreted as UTC, putting the cutoff AFTER the file's
    # mtime, so path B fails. Pre-fix on UTC+N machines, this would
    # silently pass because the naive timestamp() shifted backwards.
    from datetime import timedelta as _timedelta
    future_naive_utc = (datetime.now(UTC) + _timedelta(minutes=5)).replace(tzinfo=None)
    assert future_naive_utc.tzinfo is None, "test setup assumes naive"

    ok, reason = check_phase_8(
        "inv-p8tz",
        knowledge_skills_dir=str(skills_root),
        investigation_started_at=future_naive_utc,
    )
    assert ok is False, (
        f"naive started_at must be UTC; with cutoff 5min in future "
        f"the seed file's NOW mtime cannot satisfy the > check. "
        f"Got ok={ok}, reason={reason}"
    )


# ---------------------------------------------------------------------------
# 9. Phase 9
# ---------------------------------------------------------------------------


def test_phase_9_not_ready_rejected():
    ok, reason = check_phase_9("inv-p9-empty")
    assert ok is False


def test_phase_9_ready_passes():
    inv = "inv-p9-ready"
    plog = PhaseLog.open(inv)
    for phase in (6, 7, 8):
        plog.enter(phase)
        plog.exit(phase)
        plog.verify(phase, evidence=f"phase {phase} verified")
    ok, _ = check_phase_9(inv)
    assert ok is True


# ---------------------------------------------------------------------------
# 10. run_check dispatcher
# ---------------------------------------------------------------------------


def test_run_check_unknown_phase():
    ok, reason = run_check(99, "inv-x")
    assert ok is False
    assert "unknown phase" in reason


def test_run_check_filters_kwargs(research_dir):
    """Phase 1 accepts research_dir but not knowledge_skills_dir.
    The dispatcher must filter so the call doesn't TypeError."""
    body = (
        "# Orientation\n\n"
        + ("intro prose. " * 60)
        + "\n\n## Prior Graph Knowledge\n\n"
        + "node_xyz cited here."
    )
    _write(os.path.join(research_dir, "orientation.md"), body)
    ok, _ = run_check(
        1, "inv-disp", research_dir=research_dir,
        knowledge_skills_dir="/this/is/ignored",
    )
    assert ok is True


def test_checks_dispatch_table_covers_1_through_9():
    assert sorted(CHECKS.keys()) == list(range(1, 10))
