"""Phase-8 calibration status reporting tests."""

from __future__ import annotations

from orchestration.audit.phase8_calibration_status import (
    phase8_calibration_status,
    record_phase8_gate_review,
    summarize_phase8_calibration,
)
from substrate.event_log import emit_typed
from substrate.schemas import SkillPatchGateDecidedPayload, SkillPatchGateReviewedPayload


def _decision(
    *,
    patch_id: str = "patch-1",
    would_accept: bool = False,
    operator_reviewed: bool = False,
    operator_agreed: bool | None = None,
) -> SkillPatchGateDecidedPayload:
    return SkillPatchGateDecidedPayload(
        synthesis_id="syn-inv-1",
        patch_id=patch_id,
        mode="shadow",
        decision="shadow",
        would_accept=would_accept,
        baseline_backtest_score=0.0,
        candidate_backtest_score=0.0,
        delta=0.0,
        epsilon_required=0.02,
        cohort_size=0,
        minimum_cohort_size=50,
        matched_domains=["quantum-computing-knowledge"],
        notes="shadow-mode: patch applied regardless",
        operator_reviewed=operator_reviewed,
        operator_agreed=operator_agreed,
    )


def _review(
    *,
    patch_id: str = "patch-1",
    operator_accept: bool = False,
) -> SkillPatchGateReviewedPayload:
    return SkillPatchGateReviewedPayload(
        synthesis_id="syn-inv-1",
        patch_id=patch_id,
        decision_event_id="evt-decision",
        reviewer="operator",
        operator_accept=operator_accept,
        review_notes="manual review",
    )


def test_phase8_calibration_status_reports_unreviewed_shadow_evidence():
    status = summarize_phase8_calibration([_decision()])

    assert status.shadow_decisions_collected == 1
    assert status.operator_reviewed == 0
    assert status.operator_agreed == 0
    assert status.agreement_rate is None
    assert status.ready_for_enforcing is False
    assert (
        status.summary
        == "1 shadow decisions collected; 0 operator-reviewed; "
        "current epsilon agreement = n/a"
    )


def test_phase8_calibration_status_requires_reviewed_agreement():
    payloads = [_decision(operator_reviewed=True, operator_agreed=True) for _ in range(8)]
    payloads.extend(
        _decision(operator_reviewed=True, operator_agreed=False) for _ in range(2)
    )

    status = summarize_phase8_calibration(payloads)

    assert status.shadow_decisions_collected == 10
    assert status.operator_reviewed == 10
    assert status.operator_agreed == 8
    assert status.agreement_rate == 0.8
    assert status.ready_for_enforcing is True
    assert status.summary.endswith("current epsilon agreement = 80%")


def test_phase8_calibration_status_counts_review_events():
    status = summarize_phase8_calibration(
        [
            _decision(patch_id="patch-reject", would_accept=False),
            _decision(patch_id="patch-accept", would_accept=True),
        ],
        reviews=[
            _review(patch_id="patch-reject", operator_accept=False),
            _review(patch_id="patch-accept", operator_accept=False),
        ],
    )

    assert status.shadow_decisions_collected == 2
    assert status.operator_reviewed == 2
    assert status.operator_agreed == 1
    assert status.agreement_rate == 0.5
    assert status.ready_for_enforcing is False


def test_phase8_calibration_status_loads_typed_events(tmp_path):
    events_dir = tmp_path / "events"
    emit_typed(
        "inv-1",
        _decision(),
        synthesis_id="syn-inv-1",
        role="phase8_gate",
        events_dir=str(events_dir),
    )

    status = phase8_calibration_status(["inv-1"], events_dir=str(events_dir))

    assert status.shadow_decisions_collected == 1
    assert status.summary.startswith("1 shadow decisions collected")


def test_record_phase8_gate_review_round_trips_through_event_log(tmp_path):
    events_dir = tmp_path / "events"
    decision_id = emit_typed(
        "inv-1",
        _decision(patch_id="patch-review", would_accept=False),
        synthesis_id="syn-inv-1",
        role="phase8_gate",
        events_dir=str(events_dir),
    )
    assert decision_id is not None

    review_id = record_phase8_gate_review(
        investigation_id="inv-1",
        synthesis_id="syn-inv-1",
        patch_id="patch-review",
        decision_event_id=decision_id,
        reviewer="operator",
        operator_accept=False,
        review_notes="reject matches the shadow decision",
        events_dir=str(events_dir),
    )
    assert review_id is not None

    status = phase8_calibration_status(["inv-1"], events_dir=str(events_dir))

    assert status.shadow_decisions_collected == 1
    assert status.operator_reviewed == 1
    assert status.operator_agreed == 1
    assert status.agreement_rate == 1.0
    assert status.summary.endswith("current epsilon agreement = 100%")
