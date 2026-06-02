"""Tests for orchestration/phase_runner/ (Sprint 8 day 1).

Coverage — library API:

A. enter_phase:
   1. Happy path enters phase 1 (no precondition).
   2. Phase 2 with phase 1 done OK.
   3. Phase 2 without phase 1 done → PhaseAssertionError.
   4. enforce_precondition=False bypasses precondition check.
   5. Unknown phase number rejected (delegates to PhaseLog._phase_key).

B. exit_phase:
   6. Round-trip enter → exit → snapshot shows both timestamps.
   7. exit with outputs_paths computes outputs_hash.

C. verify_phase:
   8. Default no-op postcondition passes structurally.
   9. Injected postcondition returning (False, reason) leaves log
      UNVERIFIED (the load-bearing gate).
   10. Injected postcondition returning (True, evidence) writes
       evidence into the log.

D. assert_phase / assert_ready_for_completion:
   11. assert_phase raises before verify; passes after.
   12. assert_ready_for_completion raises until 6, 7, 8 all verified.

E. check_precondition:
   13. Phase 1 has no precondition (first phase).
   14. Phase 2 with no phase 1 → missing_phases=(1,).
   15. Phase 6 with phases 1-5 done → ok.
   16. Phase 6 with phase 3 missing → missing_phases includes 3.
   17. Unknown phase rejected at precondition layer too.

F. phase_status:
   18. Returns snapshot + live postcondition results + required-for-completion.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from orchestration.phase_log import PhaseAssertionError, PhaseLog  # noqa: E402
from orchestration.phase_runner import (  # noqa: E402
    PreconditionOutcome,
    VerifyOutcome,
    assert_phase,
    assert_ready_for_completion,
    check_precondition,
    enter_phase,
    exit_phase,
    phase_status,
    verify_phase,
)


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    d = tmp_path / "phase_logs"
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(d))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    return d


# ---------------------------------------------------------------------------
# A. enter_phase
# ---------------------------------------------------------------------------


def test_enter_phase_1_no_precondition(log_dir):
    enter_phase("inv-e1", 1, topic="t")
    snap = PhaseLog.open("inv-e1").snapshot()
    assert "1" in snap["phases"]
    assert snap["phases"]["1"]["entered_at"]


def test_enter_phase_2_with_phase_1_complete(log_dir):
    enter_phase("inv-e2", 1)
    exit_phase("inv-e2", 1)
    enter_phase("inv-e2", 2)  # OK


def test_enter_phase_2_without_phase_1_raises(log_dir):
    with pytest.raises(PhaseAssertionError, match="requires prior phases"):
        enter_phase("inv-e2b", 2)


def test_enter_phase_no_precondition_bypass(log_dir):
    """Recovery path — operator can enter a phase out of order
    explicitly with enforce_precondition=False."""
    enter_phase("inv-bypass", 6, enforce_precondition=False)
    snap = PhaseLog.open("inv-bypass").snapshot()
    assert "6" in snap["phases"]


def test_enter_phase_unknown_phase_rejected(log_dir):
    with pytest.raises((ValueError, PhaseAssertionError)):
        enter_phase("inv-bad", 99, enforce_precondition=False)


# ---------------------------------------------------------------------------
# B. exit_phase
# ---------------------------------------------------------------------------


def test_enter_exit_round_trip(log_dir):
    enter_phase("inv-rt", 1)
    exit_phase("inv-rt", 1)
    rec = PhaseLog.open("inv-rt").snapshot()["phases"]["1"]
    assert rec["entered_at"]
    assert rec["exited_at"]


def test_exit_computes_outputs_hash(log_dir, tmp_path):
    out = tmp_path / "out.md"
    out.write_text("# done")
    enter_phase("inv-h", 1)
    exit_phase("inv-h", 1, outputs_paths=[str(out)])
    rec = PhaseLog.open("inv-h").snapshot()["phases"]["1"]
    assert rec.get("outputs_hash")
    assert len(rec["outputs_hash"]) == 64


# ---------------------------------------------------------------------------
# C. verify_phase
# ---------------------------------------------------------------------------


def test_verify_default_passes_structurally(log_dir):
    enter_phase("inv-v1", 1)
    exit_phase("inv-v1", 1)
    outcome = verify_phase("inv-v1", 1)
    assert isinstance(outcome, VerifyOutcome)
    assert outcome.passed is True
    rec = PhaseLog.open("inv-v1").snapshot()["phases"]["1"]
    assert rec["verified"] is True


def test_verify_failing_postcondition_leaves_log_unverified(log_dir):
    """The load-bearing gate: postcondition fail → log NOT marked
    verified → assert refuses to advance."""
    enter_phase("inv-vf", 8, enforce_precondition=False)
    exit_phase("inv-vf", 8)

    def failing_check(phase, investigation_id):
        return False, f"skill.md did not grow for {investigation_id}"

    outcome = verify_phase("inv-vf", 8, postcondition_check=failing_check)
    assert outcome.passed is False
    assert "did not grow" in outcome.reason
    rec = PhaseLog.open("inv-vf").snapshot()["phases"]["8"]
    assert rec.get("verified") is False
    # A subsequent assertion MUST refuse.
    with pytest.raises(PhaseAssertionError, match="MUST be verified"):
        assert_phase("inv-vf", 8)


def test_verify_passing_postcondition_writes_evidence(log_dir):
    enter_phase("inv-vp", 8, enforce_precondition=False)
    exit_phase("inv-vp", 8)

    def passing_check(phase, investigation_id):
        return True, "skill.md grew by 120 lines"

    outcome = verify_phase("inv-vp", 8, postcondition_check=passing_check)
    assert outcome.passed is True
    rec = PhaseLog.open("inv-vp").snapshot()["phases"]["8"]
    assert rec["verified"] is True
    assert "120 lines" in rec["verification_evidence"]


def test_verify_postcondition_receives_phase_and_investigation_id(log_dir):
    captured = []

    def capture(phase, iid):
        captured.append((phase, iid))
        return True, "ok"

    enter_phase("inv-cap", 1)
    exit_phase("inv-cap", 1)
    verify_phase("inv-cap", 1, postcondition_check=capture)
    assert captured == [(1, "inv-cap")]


# ---------------------------------------------------------------------------
# D. assert_phase / assert_ready_for_completion
# ---------------------------------------------------------------------------


def test_assert_phase_raises_before_verify(log_dir):
    enter_phase("inv-as", 1)
    exit_phase("inv-as", 1)
    with pytest.raises(PhaseAssertionError, match="MUST be verified"):
        assert_phase("inv-as", 1)
    verify_phase("inv-as", 1)
    assert_phase("inv-as", 1)  # no raise


def test_assert_ready_for_completion_requires_6_7_8(log_dir):
    inv = "inv-rdy"
    # Complete phases 1-5 (entered + exited; verify is optional for
    # non-required phases).
    for phase in range(1, 6):
        enter_phase(inv, phase)
        exit_phase(inv, phase)
        verify_phase(inv, phase)

    # Phase 6 unverified → assert_ready_for_completion raises.
    enter_phase(inv, 6)
    exit_phase(inv, 6)
    with pytest.raises(PhaseAssertionError):
        assert_ready_for_completion(inv)

    # Verify 6, 7, 8.
    verify_phase(inv, 6)
    enter_phase(inv, 7)
    exit_phase(inv, 7)
    verify_phase(inv, 7)
    enter_phase(inv, 8)
    exit_phase(inv, 8)
    verify_phase(inv, 8)

    assert_ready_for_completion(inv)  # no raise


# ---------------------------------------------------------------------------
# E. check_precondition
# ---------------------------------------------------------------------------


def test_precondition_phase_1_is_first(log_dir):
    outcome = check_precondition("inv-p1", 1)
    assert isinstance(outcome, PreconditionOutcome)
    assert outcome.ok is True
    assert outcome.missing_phases == ()


def test_precondition_phase_2_missing_phase_1(log_dir):
    outcome = check_precondition("inv-p2", 2)
    assert outcome.ok is False
    assert outcome.missing_phases == (1,)


def test_precondition_phase_6_all_prior_done(log_dir):
    inv = "inv-p6"
    for phase in range(1, 6):
        enter_phase(inv, phase)
        exit_phase(inv, phase)
    outcome = check_precondition(inv, 6)
    assert outcome.ok is True


def test_precondition_phase_6_with_gap(log_dir):
    inv = "inv-p6g"
    for phase in (1, 2, 4, 5):  # missing 3
        enter_phase(inv, phase, enforce_precondition=False)
        exit_phase(inv, phase)
    outcome = check_precondition(inv, 6)
    assert outcome.ok is False
    assert 3 in outcome.missing_phases


def test_precondition_unknown_phase_rejected(log_dir):
    outcome = check_precondition("inv-bad", 99)
    assert outcome.ok is False


def test_precondition_entered_but_not_exited_counts_as_missing(log_dir):
    """A phase that was entered but didn't exit yet is NOT complete.
    Precondition for the next phase must reject."""
    enter_phase("inv-mid", 1)
    # No exit.
    outcome = check_precondition("inv-mid", 2)
    assert outcome.ok is False
    assert 1 in outcome.missing_phases


# ---------------------------------------------------------------------------
# F. phase_status
# ---------------------------------------------------------------------------


def test_phase_status_returns_snapshot_plus_live_check(log_dir):
    inv = "inv-st"
    enter_phase(inv, 1)
    exit_phase(inv, 1)
    verify_phase(inv, 1)

    snap = phase_status(inv)
    assert "phase_log" in snap
    assert "postconditions_live" in snap
    assert "required_for_completion" in snap
    assert snap["required_for_completion"] == [6, 7, 8]
    assert "1" in snap["postconditions_live"]
    assert snap["postconditions_live"]["1"]["passed"] is True


def test_phase_status_with_failing_check_reports_failed_live(log_dir):
    inv = "inv-stf"
    enter_phase(inv, 1)
    exit_phase(inv, 1)
    verify_phase(inv, 1)

    def fail(phase, iid):
        return False, "diagnostic-only failure"

    snap = phase_status(inv, postcondition_check=fail)
    assert snap["postconditions_live"]["1"]["passed"] is False
    # IMPORTANT: live check is observe-only — log not modified.
    rec = PhaseLog.open(inv).snapshot()["phases"]["1"]
    assert rec["verified"] is True  # still verified from earlier call
