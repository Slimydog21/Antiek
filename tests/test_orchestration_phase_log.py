"""Tests for orchestration/phase_log/ (Sprint 5 day 3-4 migration).

Coverage:

1. State machine — enter → exit → verify writes JSON and mirrors typed
   events with the right action_type + envelope phase.
2. Unknown phase ID rejected at all entry points.
3. verify() requires non-empty evidence.
4. assert_phase_completed raises in each failure shape (never entered,
   entered-not-exited, exited-not-verified).
5. assert_ready_for_completion raises with aggregated messages when
   ANY required phase failed; passes silently when all did.
6. PhaseLog.open round-trips through disk (state persists across opens).
7. hash_paths is deterministic, order-independent, sensitive to
   content changes, distinguishes missing-file from empty-file.
8. Atomic write — the on-disk file is never half-written.
9. Telemetry-failure isolation — a broken emit must not break the
   state machine.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from orchestration.phase_log import (  # noqa: E402
    PhaseAssertionError,
    PhaseLog,
    emit_phase_enter,
    emit_phase_exit,
    emit_phase_verify,
    hash_paths,
)
from substrate.constants import (  # noqa: E402
    ANTIEK_PARAM_VERSION,
    AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    PhaseEnterPayload,
    PhaseExitPayload,
    PhaseVerifyPayload,
)


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    d = tmp_path / "phase_logs"
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(d))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    return d


# ---------------------------------------------------------------------------
# 1. State machine + typed event mirror
# ---------------------------------------------------------------------------


def test_enter_writes_json_and_mirrors_typed_event(log_dir):
    log = PhaseLog.open("inv-1", topic="t")
    log.enter(8, note="phase 8 begun", metadata_json='{"src": "test"}')

    # JSON state
    snap = log.snapshot()
    assert snap["param_version"] == ANTIEK_PARAM_VERSION
    rec = snap["phases"]["8"]
    assert rec["entered_at"] != ""
    assert rec["enter_note"] == "phase 8 begun"
    assert rec["enter_metadata_json"] == '{"src": "test"}'
    assert rec["verified"] is False

    # Trajectory mirror
    rows = trajectory("inv-1")
    assert len(rows) == 1
    e = Event.model_validate(rows[0])
    assert e.action_type == ActionType.PHASE_ENTER.value
    assert e.phase == 8
    assert e.role == "phase_log"
    assert isinstance(e.payload, PhaseEnterPayload)
    assert e.payload.note == "phase 8 begun"
    assert e.payload.metadata_json == '{"src": "test"}'


def test_exit_records_outputs_hash_and_paths(log_dir, tmp_path):
    output = tmp_path / "skill.md"
    output.write_text("# growth")
    log = PhaseLog.open("inv-2")
    log.enter(8)
    log.exit(8, outputs_paths=[str(output)])

    snap = log.snapshot()["phases"]["8"]
    assert "outputs_hash" in snap and len(snap["outputs_hash"]) == 64
    assert snap["outputs_paths"] == [str(output)]

    rows = trajectory("inv-2")
    exit_rows = [r for r in rows if r["action_type"] == ActionType.PHASE_EXIT.value]
    assert len(exit_rows) == 1
    e = Event.model_validate(exit_rows[0])
    assert isinstance(e.payload, PhaseExitPayload)
    assert e.payload.outputs_hash == snap["outputs_hash"]
    assert e.phase == 8


def test_exit_outputs_hash_kwarg_overrides_outputs_paths(log_dir, tmp_path):
    out = tmp_path / "x.md"
    out.write_text("x")
    log = PhaseLog.open("inv-prec")
    log.enter(8)
    log.exit(8, outputs_hash="precomputed-hash", outputs_paths=[str(out)])
    assert log.snapshot()["phases"]["8"]["outputs_hash"] == "precomputed-hash"
    # outputs_paths NOT recorded when an explicit hash was supplied
    assert "outputs_paths" not in log.snapshot()["phases"]["8"]


def test_verify_writes_evidence_and_mirrors_typed_event(log_dir):
    log = PhaseLog.open("inv-v")
    log.enter(8)
    log.exit(8, outputs_hash="abc")
    log.verify(8, evidence="ran skill diff: +120 lines on skill.md")

    snap = log.snapshot()["phases"]["8"]
    assert snap["verified"] is True
    assert snap["verification_evidence"].startswith("ran skill diff")

    rows = trajectory("inv-v")
    verify_rows = [r for r in rows if r["action_type"] == ActionType.PHASE_VERIFY.value]
    assert len(verify_rows) == 1
    e = Event.model_validate(verify_rows[0])
    assert isinstance(e.payload, PhaseVerifyPayload)
    assert e.payload.verification_evidence.startswith("ran skill diff")
    assert e.phase == 8


# ---------------------------------------------------------------------------
# 2. Unknown phase ID rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_phase", [0, 10, -1, 99])
def test_enter_rejects_unknown_phase(log_dir, bad_phase):
    log = PhaseLog.open("inv-bp")
    with pytest.raises(ValueError, match="AUTONOMOUS_RESEARCH_PHASES"):
        log.enter(bad_phase)


def test_exit_rejects_unknown_phase(log_dir):
    log = PhaseLog.open("inv-bp2")
    with pytest.raises(ValueError, match="AUTONOMOUS_RESEARCH_PHASES"):
        log.exit(99)


def test_verify_rejects_unknown_phase(log_dir):
    log = PhaseLog.open("inv-bp3")
    with pytest.raises(ValueError, match="AUTONOMOUS_RESEARCH_PHASES"):
        log.verify(99, evidence="x")


# ---------------------------------------------------------------------------
# 3. verify() requires evidence
# ---------------------------------------------------------------------------


def test_verify_rejects_empty_evidence(log_dir):
    """Phase 8 in particular cannot pass with a vacuous verify()."""
    log = PhaseLog.open("inv-noev")
    log.enter(8)
    log.exit(8)
    with pytest.raises(ValueError, match="evidence is required"):
        log.verify(8, evidence="")


# ---------------------------------------------------------------------------
# 4. assert_phase_completed failure shapes
# ---------------------------------------------------------------------------


def test_assert_phase_completed_raises_when_never_entered(log_dir):
    log = PhaseLog.open("inv-a1")
    with pytest.raises(PhaseAssertionError, match="never entered"):
        log.assert_phase_completed(8)


def test_assert_phase_completed_raises_when_entered_not_exited(log_dir):
    log = PhaseLog.open("inv-a2")
    log.enter(8)
    with pytest.raises(PhaseAssertionError, match="never exited"):
        log.assert_phase_completed(8)


def test_assert_phase_completed_raises_when_not_verified(log_dir):
    log = PhaseLog.open("inv-a3")
    log.enter(8)
    log.exit(8)
    with pytest.raises(PhaseAssertionError, match="MUST be verified"):
        log.assert_phase_completed(8)


def test_assert_phase_completed_passes_on_full_lifecycle(log_dir):
    log = PhaseLog.open("inv-a4")
    log.enter(8)
    log.exit(8)
    log.verify(8, evidence="ok")
    # No exception
    log.assert_phase_completed(8)


# ---------------------------------------------------------------------------
# 5. assert_ready_for_completion
# ---------------------------------------------------------------------------


def test_assert_ready_passes_when_all_required_verified(log_dir):
    log = PhaseLog.open("inv-rdy")
    for p in AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION:
        log.enter(p)
        log.exit(p)
        log.verify(p, evidence=f"phase {p} done")
    log.assert_ready_for_completion()  # no raise


def test_assert_ready_aggregates_all_missing_required_phases(log_dir):
    """When MULTIPLE required phases are missing, the error message
    must list every one — not just stop at the first."""
    log = PhaseLog.open("inv-miss")
    # Verify 6, leave 7 + 8 missing entirely.
    log.enter(6)
    log.exit(6)
    log.verify(6, evidence="ok")

    with pytest.raises(PhaseAssertionError) as excinfo:
        log.assert_ready_for_completion()
    msg = str(excinfo.value)
    assert "Phase 7" in msg
    assert "Phase 8" in msg


# ---------------------------------------------------------------------------
# 6. Disk round-trip
# ---------------------------------------------------------------------------


def test_state_persists_across_opens(log_dir):
    log1 = PhaseLog.open("inv-persist", topic="bears")
    log1.enter(8, note="first run")
    log1.exit(8, outputs_hash="h1")

    log2 = PhaseLog.open("inv-persist")
    snap = log2.snapshot()
    assert snap["topic"] == "bears"
    assert snap["phases"]["8"]["enter_note"] == "first run"
    assert snap["phases"]["8"]["outputs_hash"] == "h1"


def test_open_creates_log_dir_if_missing(tmp_path, monkeypatch):
    d = tmp_path / "deep" / "nested" / "phase_logs"
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(d))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    assert not d.exists()
    PhaseLog.open("inv-mkdir")
    assert d.exists()


# ---------------------------------------------------------------------------
# 7. hash_paths determinism + sensitivity
# ---------------------------------------------------------------------------


def test_hash_paths_deterministic(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("alpha")
    b.write_text("beta")
    h1 = hash_paths([str(a), str(b)])
    h2 = hash_paths([str(a), str(b)])
    assert h1 == h2
    assert len(h1) == 64


def test_hash_paths_order_independent(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("alpha")
    b.write_text("beta")
    assert hash_paths([str(a), str(b)]) == hash_paths([str(b), str(a)])


def test_hash_paths_sensitive_to_content(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("alpha")
    h_before = hash_paths([str(a)])
    a.write_text("alpha-changed")
    assert hash_paths([str(a)]) != h_before


def test_hash_paths_distinguishes_missing_from_empty(tmp_path):
    empty = tmp_path / "e.txt"
    empty.write_text("")
    h_empty = hash_paths([str(empty)])
    h_missing = hash_paths([str(tmp_path / "absent.txt")])
    assert h_empty != h_missing


# ---------------------------------------------------------------------------
# 8. Atomic write
# ---------------------------------------------------------------------------


def test_save_is_atomic(log_dir):
    """A crash mid-write must leave the prior valid snapshot, not a
    truncated file. Tested by reading the file between operations."""
    log = PhaseLog.open("inv-atomic")
    log.enter(8)
    on_disk = json.loads(open(log.path).read())
    assert "phases" in on_disk
    log.exit(8, outputs_hash="abc")
    on_disk = json.loads(open(log.path).read())
    assert on_disk["phases"]["8"]["outputs_hash"] == "abc"
    # The .tmp sentinel must not linger after a successful save.
    assert not os.path.exists(log.path + ".tmp")


# ---------------------------------------------------------------------------
# 9. Telemetry-failure isolation
# ---------------------------------------------------------------------------


def test_state_machine_survives_emit_failure(log_dir, monkeypatch):
    """If the typed-event emitter raises (e.g. file-system issue, bad
    schema), the JSON write MUST still have happened. The substrate
    rule: telemetry failures never break a real synthesis."""
    import orchestration.phase_log.log as log_module

    def _boom(**_kw):
        raise RuntimeError("simulated emit failure")
    monkeypatch.setattr(log_module, "emit_phase_enter", _boom)

    log = PhaseLog.open("inv-emit-fail")
    log.enter(8)  # MUST NOT raise

    snap = log.snapshot()
    assert "entered_at" in snap["phases"]["8"]


# ---------------------------------------------------------------------------
# 10. Direct emit helpers round-trip
# ---------------------------------------------------------------------------


def test_emit_phase_enter_round_trips(log_dir):
    eid = emit_phase_enter(
        investigation_id="inv-direct",
        phase=8, entered_at="2026-05-17T12:00:00.000000Z",
        note="direct", metadata_json='{"k": "v"}',
    )
    e = Event.model_validate(trajectory("inv-direct")[0])
    assert e.event_id == eid
    assert e.action_type == ActionType.PHASE_ENTER.value
    assert e.phase == 8
    assert isinstance(e.payload, PhaseEnterPayload)
    assert e.payload.metadata_json == '{"k": "v"}'


def test_emit_phase_exit_allows_none_outputs_hash(log_dir):
    emit_phase_exit(
        investigation_id="inv-dexit", phase=7,
        exited_at="2026-05-17T12:00:00.000000Z", outputs_hash=None,
    )
    e = Event.model_validate(trajectory("inv-dexit")[0])
    assert e.payload.outputs_hash is None


def test_emit_phase_verify_round_trips(log_dir):
    emit_phase_verify(
        investigation_id="inv-dver", phase=8,
        verified_at="2026-05-17T12:00:00.000000Z",
        verification_evidence="sha256: deadbeef",
    )
    e = Event.model_validate(trajectory("inv-dver")[0])
    assert e.payload.verification_evidence == "sha256: deadbeef"
