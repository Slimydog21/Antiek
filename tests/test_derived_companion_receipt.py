from __future__ import annotations

import sqlite3

import pytest

from runtime.research_runner.derived_companion_receipt import (
    COMPANION_OPERATION,
    COMPANION_SEAM_ID,
    SettledCompanionReceiptVerifier,
    companion_operation_digest,
    companion_settlement_evidence,
)
from substrate.research_artifact.grounded_companion_answer import (
    AnswerAdmissionExpectation,
    GroundedAnswerError,
)
from substrate.research_spend import (
    BindingConflict,
    InvalidTransition,
    LedgerIntegrityError,
    PaidHoldIntent,
    ResearchSpendLedger,
    RunBinding,
)

TURN_ID = "dturn_" + "1" * 32
PACK_SHA = "2" * 64
OUTPUT_SHA = "3" * 64
PROVIDER_SHA = "4" * 64


def _settled(
    tmp_path,
    *,
    seam: str = COMPANION_SEAM_ID,
    operation: str = COMPANION_OPERATION,
    actual: int = 8,
    evidence: dict[str, str] | None = None,
):
    path = tmp_path / "spend.sqlite3"
    ledger = ResearchSpendLedger(path)
    ledger.ensure_schema()
    binding = RunBinding("run-companion-1", "owner-a", "session-a", "5" * 64, 1)
    ledger.create_or_reopen_run("create-companion-run", binding, 100)
    intent = PaidHoldIntent(
        reservation_key="companion-reservation-1",
        seam_id=seam,
        provider="verified-provider",
        model="grounded-model",
        operation=operation,
        operation_digest=companion_operation_digest(TURN_ID, PACK_SHA),
        projection_digest="6" * 64,
        rate_snapshot="verified-provider:2026-07-15",
        provider_idempotency_key="7" * 64,
    )
    hold = ledger.reserve_paid("reserve-companion", binding, intent, 10)
    ledger.mark_dispatch_possible("dispatch-companion", hold.hold_id)
    ledger.settle(
        "settle-companion",
        hold.hold_id,
        actual,
        evidence
        or companion_settlement_evidence(
            turn_id=TURN_ID,
            evidence_pack_sha256=PACK_SHA,
            output_digest=OUTPUT_SHA,
            provider_response_digest=PROVIDER_SHA,
        ),
    )
    return path, ledger, hold.hold_id


def _expectation(**changes: str) -> AnswerAdmissionExpectation:
    values = {
        "turn_id": TURN_ID,
        "evidence_pack_sha256": PACK_SHA,
        "output_digest": OUTPUT_SHA,
    }
    values.update(changes)
    return AnswerAdmissionExpectation(**values)


def test_projects_owner_scoped_integrity_checked_settlement_after_reopen(tmp_path) -> None:
    path, ledger, hold_id = _settled(tmp_path)
    first = ledger.settled_hold_receipt(hold_id, "owner-a")
    reopened = ResearchSpendLedger(path).settled_hold_receipt(hold_id, "owner-a")
    assert reopened == first
    assert first.hold.actual_cents == 8
    assert first.command_key == "settle-companion"
    assert first.evidence_sha256 != first.resolution_intent_sha256
    with pytest.raises(BindingConflict, match="unavailable"):
        ledger.settled_hold_receipt(hold_id, "owner-b")


def test_settlement_projection_refuses_unsettled_and_corrupt_receipts(tmp_path) -> None:
    ledger = ResearchSpendLedger(tmp_path / "spend.sqlite3")
    ledger.ensure_schema()
    binding = RunBinding("run-companion-1", "owner-a", "session-a", "5" * 64, 1)
    ledger.create_or_reopen_run("create-companion-run", binding, 100)
    intent = PaidHoldIntent(
        "reservation",
        COMPANION_SEAM_ID,
        "provider",
        "model",
        COMPANION_OPERATION,
        companion_operation_digest(TURN_ID, PACK_SHA),
        "6" * 64,
        "rate",
        "7" * 64,
    )
    hold = ledger.reserve_paid("reserve", binding, intent, 10)
    with pytest.raises(InvalidTransition, match="project settlement"):
        ledger.settled_hold_receipt(hold.hold_id, "owner-a")

    path, reopened, settled_id = _settled(tmp_path / "corrupt")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE research_spend_holds SET resolution_intent_sha256=? WHERE hold_id=?",
            ("f" * 64, settled_id),
        )
    with pytest.raises(LedgerIntegrityError, match="command binding"):
        reopened.settled_hold_receipt(settled_id, "owner-a")


def test_verifier_is_deterministic_and_exactly_binds_answer(tmp_path) -> None:
    path, ledger, hold_id = _settled(tmp_path)
    first = SettledCompanionReceiptVerifier(ledger, "owner-a", hold_id)(_expectation())
    replay = SettledCompanionReceiptVerifier(ResearchSpendLedger(path), "owner-a", hold_id)(
        _expectation()
    )
    assert replay == first
    assert first.receipt_id.startswith("rex_") and len(first.receipt_id) == 68
    assert first.status == "settled"
    assert (first.provider, first.model) == ("verified-provider", "grounded-model")
    for changed in (
        _expectation(turn_id="dturn_" + "8" * 32),
        _expectation(evidence_pack_sha256="8" * 64),
        _expectation(output_digest="8" * 64),
    ):
        with pytest.raises(GroundedAnswerError, match="unavailable"):
            SettledCompanionReceiptVerifier(ledger, "owner-a", hold_id)(changed)
    with pytest.raises(GroundedAnswerError, match="unavailable"):
        SettledCompanionReceiptVerifier(ledger, "owner-b", hold_id)(_expectation())


@pytest.mark.parametrize(
    "change",
    [
        {"seam": "other.seam"},
        {"operation": "other-operation"},
        {"actual": 11},
    ],
)
def test_verifier_refuses_wrong_or_breached_execution(tmp_path, change) -> None:
    _path, ledger, hold_id = _settled(tmp_path, **change)
    with pytest.raises(GroundedAnswerError, match="unavailable"):
        SettledCompanionReceiptVerifier(ledger, "owner-a", hold_id)(_expectation())


def test_verifier_refuses_evidence_key_smuggling_and_missing_ledger(tmp_path) -> None:
    evidence = companion_settlement_evidence(
        turn_id=TURN_ID,
        evidence_pack_sha256=PACK_SHA,
        output_digest=OUTPUT_SHA,
        provider_response_digest=PROVIDER_SHA,
    )
    evidence["untrusted"] = "smuggled"
    _path, ledger, hold_id = _settled(tmp_path, evidence=evidence)
    with pytest.raises(GroundedAnswerError, match="unavailable"):
        SettledCompanionReceiptVerifier(ledger, "owner-a", hold_id)(_expectation())
    missing = ResearchSpendLedger(tmp_path / "missing.sqlite3")
    with pytest.raises(GroundedAnswerError, match="unavailable"):
        SettledCompanionReceiptVerifier(missing, "owner-a", "missing")(_expectation())


def test_verifier_refuses_released_hold(tmp_path) -> None:
    ledger = ResearchSpendLedger(tmp_path / "spend.sqlite3")
    ledger.ensure_schema()
    binding = RunBinding("run-companion-1", "owner-a", "session-a", "5" * 64, 1)
    ledger.create_or_reopen_run("create-companion-run", binding, 100)
    hold = ledger.reserve_paid(
        "reserve",
        binding,
        PaidHoldIntent(
            "reservation",
            COMPANION_SEAM_ID,
            "provider",
            "model",
            COMPANION_OPERATION,
            companion_operation_digest(TURN_ID, PACK_SHA),
            "6" * 64,
            "rate",
            "7" * 64,
        ),
        10,
    )
    ledger.release("release", hold.hold_id, {"send_marker": "absent"})
    with pytest.raises(GroundedAnswerError, match="unavailable"):
        SettledCompanionReceiptVerifier(ledger, "owner-a", hold.hold_id)(_expectation())


def test_evidence_builder_rejects_malformed_identities() -> None:
    with pytest.raises(ValueError):
        companion_operation_digest("forged", PACK_SHA)
    with pytest.raises(ValueError):
        companion_settlement_evidence(
            turn_id=TURN_ID,
            evidence_pack_sha256=PACK_SHA,
            output_digest="not-a-digest",
            provider_response_digest=PROVIDER_SHA,
        )
