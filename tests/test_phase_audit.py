"""Tests for orchestration/audit/phase_audit.py (Sprint 8 day 2).

Coverage:

1. Clean state: a fresh investigation with no phase_log entries
   produces 3 missing_phase findings (one per required phase 6/7/8).
2. Phase 6 entered+verified, 7/8 missing → 2 missing_phase findings.
3. Phase verified but live postcondition fails → adds
   postcondition_failed finding.
4. Phase 8 verified but no AUTO_PATCH_APPLIED with patched →
   adds no_auto_patch finding (the silent-failure mode).
5. Phase 8 verified WITH AUTO_PATCH_APPLIED patched → no
   no_auto_patch finding.
6. Empty skill dir → adds empty_skill_dir finding (warning).
7. Skill dir with at least one domain → no empty_skill_dir finding.
8. ``audit_phase_log(emit=True)`` writes AUDIT_FINDING_EMITTED events
   into the trajectory (one per finding).
9. ``audit_phase_log(emit=False)`` returns findings without emitting.
10. Severity dispatching: missing_phase + unverified_phase + no_auto_patch
    are critical; postcondition_failed + empty_skill_dir are warning.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from orchestration.audit import (  # noqa: E402
    audit_phase_log,
    collect_findings,
)
from orchestration.phase_log import PhaseLog  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    AuditFindingPayload,
    AutoPatchAppliedPayload,
    Event,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv(
        "ANTIEK_KNOWLEDGE_SKILLS_DIR", str(tmp_path / "skills"),
    )
    yield


@pytest.fixture
def skills_root(tmp_path) -> Path:
    return tmp_path / "skills"


def _verify_phase(plog: PhaseLog, phase: int, *, evidence: str = "ok") -> None:
    plog.enter(phase)
    plog.exit(phase)
    plog.verify(phase, evidence=evidence)


# ---------------------------------------------------------------------------
# 1. Clean state — 3 missing required phases
# ---------------------------------------------------------------------------


def test_clean_state_yields_three_missing_phase_findings():
    findings = collect_findings("inv-clean")
    missing = [f for f in findings if f.category == "missing_phase"]
    assert len(missing) == 3
    phases_flagged = {f.target_phase for f in missing}
    assert phases_flagged == {6, 7, 8}
    # All critical.
    assert all(f.severity == "critical" for f in missing)


# ---------------------------------------------------------------------------
# 2. Partial completion
# ---------------------------------------------------------------------------


def test_partial_phase_completion(skills_root):
    plog = PhaseLog.open("inv-partial")
    _verify_phase(plog, 6)
    findings = collect_findings("inv-partial")
    missing = [f for f in findings if f.category == "missing_phase"]
    assert {f.target_phase for f in missing} == {7, 8}


# ---------------------------------------------------------------------------
# 3. unverified_phase
# ---------------------------------------------------------------------------


def test_entered_but_unverified_phase_flagged():
    plog = PhaseLog.open("inv-unver")
    plog.enter(6)
    plog.exit(6)
    # No verify.
    findings = collect_findings("inv-unver")
    unverified = [f for f in findings if f.category == "unverified_phase"]
    assert len(unverified) == 1
    assert unverified[0].target_phase == 6
    assert unverified[0].severity == "critical"


# ---------------------------------------------------------------------------
# 4. postcondition_failed
# ---------------------------------------------------------------------------


def test_verified_phase_with_failing_live_postcondition_flagged(research_dir=None):
    """Phase 7 verified in log but no MASTER.md on disk + no
    MASTER_MD_WRITTEN event → live postcondition fails → finding."""
    plog = PhaseLog.open("inv-pf")
    _verify_phase(plog, 7)  # marked verified via PhaseLog.verify directly
    findings = collect_findings("inv-pf")
    pcond_failed = [
        f for f in findings if f.category == "postcondition_failed"
    ]
    assert any(f.target_phase == 7 for f in pcond_failed)
    assert all(f.severity == "warning" for f in pcond_failed)


# ---------------------------------------------------------------------------
# 5. no_auto_patch (the silent-failure mode)
# ---------------------------------------------------------------------------


def test_phase_8_verified_without_auto_patch_event_flagged(skills_root):
    """Phase 8 verified in log but trajectory has no
    AUTO_PATCH_APPLIED with patched domains → no_auto_patch critical."""
    plog = PhaseLog.open("inv-nap")
    _verify_phase(plog, 8)
    findings = collect_findings("inv-nap")
    no_ap = [f for f in findings if f.category == "no_auto_patch"]
    assert len(no_ap) == 1
    assert no_ap[0].severity == "critical"
    assert no_ap[0].target_phase == 8


def test_phase_8_verified_with_auto_patch_event_clears_no_auto_patch():
    inv = "inv-ap-ok"
    plog = PhaseLog.open(inv)
    _verify_phase(plog, 8)

    emit_typed(
        inv,
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
    findings = collect_findings(inv)
    no_ap = [f for f in findings if f.category == "no_auto_patch"]
    assert no_ap == []


def test_phase_8_verified_with_auto_patch_no_match_still_flagged():
    """An AUTO_PATCH_APPLIED with status=no_match (patched=[]) does
    NOT satisfy the gate."""
    inv = "inv-ap-nm"
    plog = PhaseLog.open(inv)
    _verify_phase(plog, 8)
    emit_typed(
        inv,
        AutoPatchAppliedPayload(
            synthesis_id="syn-1",
            matched_domains=[],
            patched=[],
            skipped=[],
            errors=[],
            status="no_match",
        ),
        synthesis_id="syn-1",
        role="auto_patch",
    )
    findings = collect_findings(inv)
    assert any(f.category == "no_auto_patch" for f in findings)


# ---------------------------------------------------------------------------
# 6-7. empty_skill_dir
# ---------------------------------------------------------------------------


def test_empty_skill_dir_flagged(skills_root):
    skills_root.mkdir(parents=True)
    findings = collect_findings("inv-esd")
    empty = [f for f in findings if f.category == "empty_skill_dir"]
    assert len(empty) == 1
    assert empty[0].severity == "warning"
    assert empty[0].target_path == str(skills_root)


def test_skill_dir_with_domain_not_flagged(skills_root):
    (skills_root / "quantum-knowledge").mkdir(parents=True)
    findings = collect_findings("inv-popsd")
    empty = [f for f in findings if f.category == "empty_skill_dir"]
    assert empty == []


def test_missing_skill_dir_not_flagged():
    """A non-existent skills dir is handled by Phase 8 postcondition,
    not surfaced as a separate empty_skill_dir finding."""
    findings = collect_findings("inv-no-skill-dir")
    empty = [f for f in findings if f.category == "empty_skill_dir"]
    assert empty == []


# ---------------------------------------------------------------------------
# 8-9. emit vs collect
# ---------------------------------------------------------------------------


def test_audit_emits_one_event_per_finding():
    plog = PhaseLog.open("inv-emit")
    _verify_phase(plog, 6)  # 7 + 8 still missing → 2 findings
    findings = audit_phase_log("inv-emit", emit=True)
    audit_rows = [
        r for r in trajectory("inv-emit")
        if r["action_type"] == ActionType.AUDIT_FINDING_EMITTED.value
    ]
    assert len(audit_rows) == len(findings)
    # Validate one event end-to-end.
    e = Event.model_validate(audit_rows[0])
    assert isinstance(e.payload, AuditFindingPayload)
    assert e.role == "phase_auditor"


def test_audit_emit_false_does_not_write_events():
    findings = audit_phase_log("inv-noemit", emit=False)
    audit_rows = [
        r for r in trajectory("inv-noemit")
        if r["action_type"] == ActionType.AUDIT_FINDING_EMITTED.value
    ]
    assert audit_rows == []
    assert len(findings) >= 1  # missing_phase findings still surfaced


# ---------------------------------------------------------------------------
# 10. Severity dispatch
# ---------------------------------------------------------------------------


def test_severity_assignments():
    plog = PhaseLog.open("inv-sev")
    plog.enter(6)
    plog.exit(6)  # unverified → critical
    _verify_phase(plog, 8)  # verified but no auto_patch → critical
    _verify_phase(plog, 7)  # verified but no MASTER.md → warning (postcond)

    findings = collect_findings("inv-sev")
    by_cat = {f.category: f for f in findings}

    # missing_phase (any) → critical
    missing = [f for f in findings if f.category == "missing_phase"]
    assert all(f.severity == "critical" for f in missing)

    # unverified_phase → critical
    assert by_cat["unverified_phase"].severity == "critical"

    # no_auto_patch → critical
    assert by_cat["no_auto_patch"].severity == "critical"

    # postcondition_failed → warning
    pcond = [f for f in findings if f.category == "postcondition_failed"]
    assert all(f.severity == "warning" for f in pcond)
