"""Phase 8 shadow calibration status audit tests."""

from __future__ import annotations

import json

import pytest

from compounding.skill_growth import SkillPatchGate
from orchestration.audit.phase8_calibration_status import (
    Phase8CalibrationRecord,
    load_records_jsonl,
    record_from_mapping,
    record_from_patch_outcome,
    summarize_calibration,
    summarize_jsonl,
)


def _record(
    patch_id: str,
    *,
    delta: float,
    operator_accepted: bool | None = None,
) -> Phase8CalibrationRecord:
    return Phase8CalibrationRecord(
        patch_id=patch_id,
        decision="shadow",
        delta=delta,
        epsilon_required=0.02,
        cohort_size=50,
        operator_accepted=operator_accepted,
    )


def test_status_reports_unreviewed_shadow_progress_not_ready() -> None:
    status = summarize_calibration(
        [_record(f"patch-{i}", delta=0.10) for i in range(4)]
    )

    assert status.shadow_decisions_collected == 4
    assert status.operator_reviewed == 0
    assert status.agreement_rate is None
    assert status.calibration_ready is False
    assert "4 shadow decisions collected" in status.one_line()
    assert "operator-reviewed" in status.one_line()
    assert "NOT_READY" in status.one_line()


def test_empty_status_is_not_ready_without_dividing_by_zero() -> None:
    status = summarize_calibration([])

    assert status.shadow_decisions_collected == 0
    assert status.operator_reviewed == 0
    assert status.agreement_rate is None
    assert status.calibration_ready is False


def test_nine_reviewed_shadow_decisions_are_not_ready() -> None:
    status = summarize_calibration(
        [
            _record(f"patch-{i}", delta=0.10, operator_accepted=True)
            for i in range(9)
        ]
    )

    assert status.shadow_decisions_collected == 9
    assert status.operator_reviewed == 9
    assert status.agreement_rate == 1.0
    assert status.calibration_ready is False


def test_below_eighty_percent_agreement_is_not_ready() -> None:
    records = [
        _record(f"patch-agree-{i}", delta=0.10, operator_accepted=True)
        for i in range(7)
    ]
    records.extend(
        _record(f"patch-disagree-{i}", delta=0.10, operator_accepted=False)
        for i in range(3)
    )

    status = summarize_calibration(records)

    assert status.shadow_decisions_collected == 10
    assert status.operator_reviewed == 10
    assert status.agreements == 7
    assert status.agreement_rate == 0.7
    assert status.calibration_ready is False


def test_status_ready_after_required_shadow_reviews_and_agreement() -> None:
    records = [
        _record(f"patch-accept-{i}", delta=0.10, operator_accepted=True)
        for i in range(8)
    ]
    records.extend(
        _record(f"patch-reject-{i}", delta=-0.01, operator_accepted=False)
        for i in range(2)
    )

    status = summarize_calibration(records)

    assert status.shadow_decisions_collected == 10
    assert status.operator_reviewed == 10
    assert status.agreements == 10
    assert status.agreement_rate == 1.0
    assert status.calibration_ready is True
    assert status.one_line().endswith("READY")


def test_record_from_patch_outcome_derives_would_accept() -> None:
    gate = SkillPatchGate(mode="shadow", epsilon=0.05)
    outcome = gate.decide(
        baseline_backtest_score=0.50,
        candidate_backtest_score=0.60,
        cohort_size=50,
    )

    record = record_from_patch_outcome(outcome, operator_accepted=True)

    assert record.patch_id == outcome.patch_id
    assert record.is_shadow is True
    assert record.would_accept is True
    assert record.agrees_with_operator is True


def test_jsonl_loader_accepts_direct_and_event_log_shaped_rows(tmp_path) -> None:
    path = tmp_path / "phase8.jsonl"
    rows = [
        {
            "patch_id": "patch-1",
            "decision": "shadow",
            "delta": 0.04,
            "epsilon_required": 0.02,
            "cohort_size": 50,
            "operator_review": "accept",
        },
        {
            "action_type": "phase8.skill_patch",
            "payload": {
                "patch_id": "patch-2",
                "decision": "shadow",
                "delta": -0.01,
                "epsilon_required": 0.02,
                "cohort_size": 50,
                "operator_accepted": False,
            },
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    records = load_records_jsonl(path)
    status = summarize_jsonl(path, required_shadow_decisions=2, required_agreement=1.0)

    assert [record.patch_id for record in records] == ["patch-1", "patch-2"]
    assert status.operator_reviewed == 2
    assert status.agreement_rate == 1.0
    assert status.calibration_ready is True


def test_record_from_mapping_rejects_unknown_operator_review() -> None:
    with pytest.raises(ValueError, match="unknown operator review"):
        record_from_mapping(
            {
                "patch_id": "patch-x",
                "decision": "shadow",
                "delta": 0.04,
                "epsilon_required": 0.02,
                "cohort_size": 50,
                "operator_review": "maybe",
            }
        )
