"""Phase-8 calibration status reporting tests."""

from __future__ import annotations

from orchestration.audit.phase8_calibration_status import (
    phase8_calibration_status,
    summarize_phase8_calibration,
)
from substrate.event_log import emit_typed
from substrate.schemas import SkillPatchGateDecidedPayload


def _decision(
    *,
    operator_reviewed: bool = False,
    operator_agreed: bool | None = None,
) -> SkillPatchGateDecidedPayload:
    return SkillPatchGateDecidedPayload(
        synthesis_id="syn-inv-1",
        patch_id="patch-1",
        mode="shadow",
        decision="shadow",
        would_accept=False,
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
