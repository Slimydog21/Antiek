"""Pure claim-admission preflight for Midnight Oil graph projection."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import (
    REFUSED_GRAPH_ADMISSION_REASONS,
    RETRYABLE_GRAPH_ADMISSION_REASONS,
    GraphAdmissionReason,
    ResearchAcceptancePolicy,
)
from .job import (
    MidnightOilClaimEvidence,
    MidnightOilStepEvidence,
    source_receipt_id,
    validate_step_claim_evidence,
)

_REASON_ORDER: tuple[GraphAdmissionReason, ...] = (
    "policy_authority_drift",
    "legacy_unverified",
    "claim_coverage_missing",
    "receipt_malformed_or_forged",
    "external_receipt_not_admissible_v1",
    "internal_local_chunk_temporarily_missing",
    "operational_artifact_pending",
    "graph_lock_unavailable",
    "deterministic_row_conflict",
)


@dataclass(frozen=True)
class ClaimAdmissionResult:
    covered: tuple[MidnightOilClaimEvidence, ...]
    unverified: tuple[MidnightOilClaimEvidence, ...]
    invalid: tuple[MidnightOilClaimEvidence, ...]
    exploratory: tuple[MidnightOilClaimEvidence, ...]
    reason_codes: tuple[GraphAdmissionReason, ...]

    @property
    def admitted(self) -> bool:
        return not self.reason_codes


def _ordered_reasons(
    reasons: set[GraphAdmissionReason],
) -> tuple[GraphAdmissionReason, ...]:
    return tuple(reason for reason in _REASON_ORDER if reason in reasons)


def _receipt_reason(receipt: dict[str, str]) -> GraphAdmissionReason | None:
    try:
        source_receipt_id(receipt)
    except (TypeError, ValueError):
        return "receipt_malformed_or_forged"
    source_url = receipt.get("source_url", "")
    if not source_url.startswith("antiek://document/"):
        return "external_receipt_not_admissible_v1"
    document_id = receipt.get("document_id", "")
    chunk_id = receipt.get("source_id", "")
    if (
        receipt.get("hash_scope") != "retrieval_excerpt"
        or re.fullmatch(r"[0-9a-f]{64}", receipt.get("content_hash", "")) is None
        or source_url != f"antiek://document/{document_id}#chunk={chunk_id}"
    ):
        return "receipt_malformed_or_forged"
    return None


def verify_claim_admission(
    *,
    job_id: str,
    step_evidence: tuple[MidnightOilStepEvidence, ...],
    acceptance_policy: ResearchAcceptancePolicy | None,
) -> ClaimAdmissionResult:
    """Classify durable claims without opening or mutating DuckDB."""

    reasons: set[GraphAdmissionReason] = set()
    covered: list[MidnightOilClaimEvidence] = []
    unverified: list[MidnightOilClaimEvidence] = []
    invalid: list[MidnightOilClaimEvidence] = []
    exploratory: list[MidnightOilClaimEvidence] = []
    if acceptance_policy != ResearchAcceptancePolicy():
        reasons.add("policy_authority_drift")
    for evidence in step_evidence:
        if evidence.claim_evidence_schema_version is None:
            reasons.add("legacy_unverified")
            continue
        try:
            validate_step_claim_evidence(job_id, evidence)
        except (TypeError, ValueError):
            invalid.extend(evidence.claim_evidence)
            reasons.add("receipt_malformed_or_forged")
            continue
        receipts = {
            source_receipt_id(receipt): receipt for receipt in evidence.source_receipts
        }
        for claim in evidence.claim_evidence:
            if claim.status == "exploratory":
                exploratory.append(claim)
                continue
            if claim.status == "unverified":
                unverified.append(claim)
                reasons.add("claim_coverage_missing")
                continue
            claim_reasons = {
                reason
                for receipt_id in claim.source_receipt_ids
                if (reason := _receipt_reason(receipts[receipt_id])) is not None
            }
            if claim_reasons:
                invalid.append(claim)
                reasons.update(claim_reasons)
            else:
                covered.append(claim)
    return ClaimAdmissionResult(
        covered=tuple(covered),
        unverified=tuple(unverified),
        invalid=tuple(invalid),
        exploratory=tuple(exploratory),
        reason_codes=_ordered_reasons(reasons),
    )


__all__ = [
    "ClaimAdmissionResult",
    "REFUSED_GRAPH_ADMISSION_REASONS",
    "RETRYABLE_GRAPH_ADMISSION_REASONS",
    "verify_claim_admission",
]
