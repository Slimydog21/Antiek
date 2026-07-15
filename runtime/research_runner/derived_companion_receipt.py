"""Verify settled research spend as a derived companion answer receipt."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Final

from substrate.research_artifact.grounded_companion_answer import (
    AnswerAdmissionExpectation,
    GroundedAnswerError,
    VerifiedCompanionExecutionReceipt,
)
from substrate.research_spend import PaidHoldState, ResearchSpendLedger

SETTLEMENT_SCHEMA_VERSION: Final = "antiek.derived-companion-settlement.v1"
COMPANION_SEAM_ID: Final = "derived_companion.answer"
COMPANION_OPERATION: Final = "answer"
_SHA = re.compile(r"[0-9a-f]{64}")
_TURN = re.compile(r"dturn_[0-9a-f]{32}")


def companion_operation_digest(turn_id: str, evidence_pack_sha256: str) -> str:
    _validate_identity(turn_id, evidence_pack_sha256)
    return _digest(
        {
            "evidence_pack_sha256": evidence_pack_sha256,
            "schema_version": SETTLEMENT_SCHEMA_VERSION,
            "turn_id": turn_id,
        }
    )


def companion_settlement_evidence(
    *,
    turn_id: str,
    evidence_pack_sha256: str,
    output_digest: str,
    provider_response_digest: str,
) -> dict[str, str]:
    _validate_identity(turn_id, evidence_pack_sha256)
    if not _SHA.fullmatch(output_digest) or not _SHA.fullmatch(provider_response_digest):
        raise ValueError("companion output evidence digests must be lowercase SHA-256")
    return {
        "evidence_pack_sha256": evidence_pack_sha256,
        "output_digest": output_digest,
        "provider_response_digest": provider_response_digest,
        "schema_version": SETTLEMENT_SCHEMA_VERSION,
        "turn_id": turn_id,
    }


@dataclass(frozen=True)
class SettledCompanionReceiptVerifier:
    ledger: ResearchSpendLedger
    owner_user_id: str
    hold_id: str

    def __post_init__(self) -> None:
        if not self.owner_user_id.strip() or not self.hold_id.strip():
            raise ValueError("companion receipt verifier identity is required")

    def __call__(
        self,
        expectation: AnswerAdmissionExpectation,
    ) -> VerifiedCompanionExecutionReceipt:
        try:
            receipt = self.ledger.settled_hold_receipt(self.hold_id, self.owner_user_id)
            hold = receipt.hold
            if (
                hold.state is not PaidHoldState.SETTLED
                or hold.actual_cents is None
                or hold.actual_cents > hold.projected_max_cents
                or hold.intent.seam_id != COMPANION_SEAM_ID
                or hold.intent.operation != COMPANION_OPERATION
                or hold.intent.operation_digest
                != companion_operation_digest(expectation.turn_id, expectation.evidence_pack_sha256)
            ):
                raise ValueError("settled hold is not an eligible companion execution")
            evidence = json.loads(receipt.evidence_json)
            expected_evidence = companion_settlement_evidence(
                turn_id=expectation.turn_id,
                evidence_pack_sha256=expectation.evidence_pack_sha256,
                output_digest=expectation.output_digest,
                provider_response_digest=str(evidence.get("provider_response_digest", "")),
            )
            if evidence != expected_evidence:
                raise ValueError("settlement evidence does not bind the answer")
            identity = {
                "actual_cents": hold.actual_cents,
                "command_key": receipt.command_key,
                "evidence_sha256": receipt.evidence_sha256,
                "hold_id": hold.hold_id,
                "model": hold.intent.model,
                "operation_digest": hold.intent.operation_digest,
                "owner_user_id": self.owner_user_id,
                "provider": hold.intent.provider,
                "provider_response_digest": evidence["provider_response_digest"],
                "resolved_at": hold.resolved_at,
                "run_id": hold.run_id,
            }
            receipt_id = "rex_" + _digest({"domain": "companion-receipt-id-v1", **identity})
            receipt_digest = _digest(
                {
                    "domain": "companion-receipt-digest-v1",
                    "receipt_id": receipt_id,
                    **identity,
                }
            )
            return VerifiedCompanionExecutionReceipt(
                receipt_id=receipt_id,
                receipt_digest=receipt_digest,
                status="settled",
                provider=hold.intent.provider,
                model=hold.intent.model,
                turn_id=expectation.turn_id,
                evidence_pack_sha256=expectation.evidence_pack_sha256,
                output_digest=expectation.output_digest,
            )
        except GroundedAnswerError:
            raise
        except Exception as exc:
            raise GroundedAnswerError("settled companion receipt is unavailable") from exc


def _validate_identity(turn_id: str, evidence_pack_sha256: str) -> None:
    if not _TURN.fullmatch(turn_id) or not _SHA.fullmatch(evidence_pack_sha256):
        raise ValueError("companion settlement identity is invalid")


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "COMPANION_OPERATION",
    "COMPANION_SEAM_ID",
    "SETTLEMENT_SCHEMA_VERSION",
    "SettledCompanionReceiptVerifier",
    "companion_operation_digest",
    "companion_settlement_evidence",
]
