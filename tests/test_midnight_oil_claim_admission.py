from __future__ import annotations

import hashlib

from substrate.midnight_oil.claim_admission import (
    REFUSED_GRAPH_ADMISSION_REASONS,
    RETRYABLE_GRAPH_ADMISSION_REASONS,
    verify_claim_admission,
)
from substrate.midnight_oil.contracts import ResearchAcceptancePolicy
from substrate.midnight_oil.job import MidnightOilStepEvidence, source_receipt_id
from substrate.midnight_oil.worker import (
    WorkerClaimSupport,
    WorkerStepResult,
    _step_evidence,
)


def _receipt(**changes: str) -> dict[str, str]:
    receipt = {
        "source_id": "chunk-1",
        "document_id": "document-1",
        "source_url": "antiek://document/document-1#chunk=chunk-1",
        "content_hash": hashlib.sha256(b"local evidence").hexdigest(),
        "hash_scope": "retrieval_excerpt",
        "title": "Local evidence",
    }
    receipt.update(changes)
    return receipt


def _evidence(
    *,
    receipt: dict[str, str] | None = None,
    support_output: bool = True,
    support_insight: bool = True,
) -> MidnightOilStepEvidence:
    source = _receipt() if receipt is None else receipt
    receipt_id = source_receipt_id(source)
    support = []
    if support_output:
        support.append(WorkerClaimSupport("output_paragraph", 0, (receipt_id,)))
    if support_insight:
        support.append(WorkerClaimSupport("insight", 0, (receipt_id,)))
    return _step_evidence(
        WorkerStepResult(
            spent_usd=0.0,
            output_text="Supported paragraph.",
            insights=("Supported insight.",),
            questions=("What remains exploratory?",),
            source_receipts=(source,),
            claim_support=tuple(support),
        ),
        job_id="job",
        step_key="step",
    )


def test_pure_preflight_classifies_covered_and_exploratory_claims() -> None:
    result = verify_claim_admission(
        job_id="job",
        step_evidence=(_evidence(),),
        acceptance_policy=ResearchAcceptancePolicy(),
    )

    assert result.admitted is True
    assert [claim.claim_class for claim in result.covered] == [
        "output_paragraph",
        "insight",
    ]
    assert [claim.claim_class for claim in result.exploratory] == [
        "exploratory_question"
    ]
    assert result.unverified == ()
    assert result.invalid == ()
    assert result.reason_codes == ()


def test_unmapped_required_claim_refuses_without_promoting_partial_coverage() -> None:
    result = verify_claim_admission(
        job_id="job",
        step_evidence=(_evidence(support_insight=False),),
        acceptance_policy=ResearchAcceptancePolicy(),
    )

    assert result.admitted is False
    assert [claim.claim_class for claim in result.covered] == ["output_paragraph"]
    assert [claim.claim_class for claim in result.unverified] == ["insight"]
    assert result.reason_codes == ("claim_coverage_missing",)


def test_legacy_policy_drift_external_and_malformed_receipts_have_closed_reasons() -> None:
    legacy = MidnightOilStepEvidence("legacy", None, "old prose", (), ())
    legacy_result = verify_claim_admission(
        job_id="job", step_evidence=(legacy,), acceptance_policy=ResearchAcceptancePolicy()
    )
    assert legacy_result.reason_codes == ("legacy_unverified",)

    policy_result = verify_claim_admission(
        job_id="job", step_evidence=(_evidence(),), acceptance_policy=None
    )
    assert policy_result.reason_codes == ("policy_authority_drift",)

    external = _receipt(source_url="https://example.test/source")
    external_result = verify_claim_admission(
        job_id="job",
        step_evidence=(_evidence(receipt=external),),
        acceptance_policy=ResearchAcceptancePolicy(),
    )
    assert external_result.reason_codes == ("external_receipt_not_admissible_v1",)
    assert len(external_result.invalid) == 2

    malformed = _receipt(source_url="antiek://document/wrong#chunk=chunk-1")
    malformed_result = verify_claim_admission(
        job_id="job",
        step_evidence=(_evidence(receipt=malformed),),
        acceptance_policy=ResearchAcceptancePolicy(),
    )
    assert malformed_result.reason_codes == ("receipt_malformed_or_forged",)
    assert len(malformed_result.invalid) == 2

    assert REFUSED_GRAPH_ADMISSION_REASONS.isdisjoint(
        RETRYABLE_GRAPH_ADMISSION_REASONS
    )
    assert len(REFUSED_GRAPH_ADMISSION_REASONS | RETRYABLE_GRAPH_ADMISSION_REASONS) == 9
