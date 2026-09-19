"""Explicit canonical consumption of one reviewed effective-context proposal."""

from __future__ import annotations

import hashlib

from substrate.research_artifact.authority import ArtifactAuthority

from .claim_revision_compensation import (
    ClaimRevisionCompensationConflict,
    ClaimRevisionCompensationPreview,
    build_claim_revision_compensation_preview,
    compensation_acceptance,
)
from .effective_context_review import (
    EffectiveContextCompensationProposal,
    EffectiveContextReviewAcceptance,
)
from .schema import ArtifactOwnerClaimProposalCompensation, ResearchArtifactBody


def validate_effective_context_proposal(
    *,
    proposal: EffectiveContextCompensationProposal,
    review: EffectiveContextReviewAcceptance,
    authority: ArtifactAuthority,
    owner_account_digest: str,
) -> None:
    if (
        review.disposition != "propose_compensation"
        or proposal.review_receipt_sha256 != review.receipt_sha256
        or proposal.context_receipt_sha256 != review.context_receipt_sha256
        or proposal.owner_account_digest != owner_account_digest
        or review.owner_account_digest != owner_account_digest
        or proposal.artifact_account_digest != authority.account_digest
        or review.artifact_account_digest != authority.account_digest
        or proposal.artifact_investigation_digest != authority.investigation_digest
        or review.artifact_investigation_digest != authority.investigation_digest
        or proposal.artifact_content_hash != review.artifact_content_hash
        or proposal.claim_index != review.claim_index
        or proposal.head_transition_sha256 != review.head_transition_sha256
        or proposal.rationale != review.rationale
    ):
        raise ClaimRevisionCompensationConflict(
            "effective context proposal lineage is invalid"
        )


def build_effective_context_compensation_preview(
    *,
    proposal: EffectiveContextCompensationProposal,
    review: EffectiveContextReviewAcceptance,
    authority: ArtifactAuthority,
    owner_account_digest: str,
    prior_body: ResearchArtifactBody,
    mutation_key: str,
) -> ClaimRevisionCompensationPreview:
    validate_effective_context_proposal(
        proposal=proposal,
        review=review,
        authority=authority,
        owner_account_digest=owner_account_digest,
    )
    if prior_body.content_hash() != proposal.artifact_content_hash:
        raise ClaimRevisionCompensationConflict(
            "effective context proposal artifact is stale"
        )
    return build_claim_revision_compensation_preview(
        authority=authority,
        owner_account_digest=owner_account_digest,
        prior_body=prior_body,
        claim_index=proposal.claim_index,
        supersedes_transition_sha256=proposal.head_transition_sha256,
        operation="supersede_owner_revision",
        replacement_claim=proposal.proposed_claim,
        rationale=proposal.rationale,
        mutation_key=mutation_key,
        source_context_receipt_sha256=proposal.context_receipt_sha256,
        source_review_receipt_sha256=proposal.review_receipt_sha256,
        source_proposal_receipt_sha256=proposal.receipt_sha256,
    )


def replay_effective_context_compensation(
    *,
    body: ResearchArtifactBody,
    proposal: EffectiveContextCompensationProposal,
    mutation_key: str,
) -> dict[str, object] | None:
    matches = [
        item
        for item in body.owner_claim_compensations
        if isinstance(item, ArtifactOwnerClaimProposalCompensation)
        and item.source_proposal_receipt_sha256 == proposal.receipt_sha256
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ClaimRevisionCompensationConflict(
            "effective context proposal consumption is ambiguous"
        )
    compensation = matches[0]
    if (
        compensation.source_context_receipt_sha256
        != proposal.context_receipt_sha256
        or compensation.source_review_receipt_sha256
        != proposal.review_receipt_sha256
        or compensation.claim_index != proposal.claim_index
        or compensation.supersedes_transition_sha256
        != proposal.head_transition_sha256
        or compensation.replacement_claim != proposal.proposed_claim
        or compensation.rationale != proposal.rationale
        or compensation.mutation_key_sha256
        != hashlib.sha256(mutation_key.encode("utf-8")).hexdigest()
    ):
        raise ClaimRevisionCompensationConflict(
            "effective context proposal is already consumed by another command"
        )
    index = body.owner_claim_compensations.index(compensation)
    historical_result = ResearchArtifactBody.model_validate(
        {
            **body.model_dump(mode="json"),
            "schema_version": 4,
            "owner_claim_compensations": [
                item.model_dump(mode="json")
                for item in body.owner_claim_compensations[: index + 1]
            ],
        }
    )
    return compensation_acceptance(historical_result, compensation)
