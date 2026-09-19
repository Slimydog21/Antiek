"""Canonical-rooted projection of completed effective-claim research rounds."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from substrate.engagement_spine.store import EngagementStore
from substrate.floating_session.store import SessionStore

from .authority import ArtifactAuthority
from .claim_review import ClaimReviewCandidate, resolve_claim_review_candidate
from .effective_context_compensation import validate_effective_context_proposal
from .effective_context_review import (
    EffectiveContextCompensationProposal,
    EffectiveContextReviewAcceptance,
    build_effective_context_review_preview,
    read_effective_context_proposal,
    read_effective_context_review,
)
from .schema import ArtifactOwnerClaimProposalCompensation, ResearchArtifactBody


class EffectiveClaimIterationConflict(ValueError):
    """Canonical and immutable iteration state cannot be projected exactly."""


@dataclass(frozen=True)
class EffectiveClaimIteration:
    ordinal: int
    prior_body: ResearchArtifactBody
    result_body: ResearchArtifactBody
    candidate: ClaimReviewCandidate
    review: EffectiveContextReviewAcceptance
    proposal: EffectiveContextCompensationProposal
    compensation: ArtifactOwnerClaimProposalCompensation
    question: str

    def public_dict(self) -> dict[str, object]:
        challenge = self.candidate.challenge
        return {
            "ordinal": self.ordinal,
            "prior_artifact_content_hash": self.prior_body.content_hash(),
            "result_artifact_content_hash": self.result_body.content_hash(),
            "claim_index": self.compensation.claim_index,
            "archived_claim": challenge.archived_claim,
            "prior_effective_claim": self.compensation.prior_effective_claim,
            "candidate_text": self.candidate.candidate_text,
            "candidate_sha256": self.candidate.candidate_sha256,
            "review_rationale": self.review.rationale,
            "proposed_claim": self.proposal.proposed_claim,
            "replacement_claim": self.compensation.replacement_claim,
            "context_receipt_sha256": self.compensation.source_context_receipt_sha256,
            "review_receipt_sha256": self.compensation.source_review_receipt_sha256,
            "proposal_receipt_sha256": self.compensation.source_proposal_receipt_sha256,
            "transition_sha256": self.compensation.transition_sha256,
            "session_id": self.review.session_id,
            "spawn_id": self.review.spawn_id,
            "question": self.question,
            "purpose": challenge.purpose,
            "model_id": challenge.model_id,
            "research_tier": challenge.research_tier,
            "archive_grounded": False,
            "grants_authority": False,
            "permits_graph_admission": False,
            "permits_write": False,
            "permits_benchmark_feedback": False,
            "permits_publication": False,
            "permits_provider_call": False,
            "permits_spend": False,
        }


def _strict_session(session_id: str, store: SessionStore) -> dict[str, Any]:
    strict = getattr(store, "get_session_strict", None)
    row = strict(session_id) if callable(strict) else store.get_session(session_id)
    if row is None:
        raise EffectiveClaimIterationConflict("iteration session is unavailable")
    return row


def _strict_spawn(spawn_id: str, store: EngagementStore) -> dict[str, Any]:
    strict = getattr(store, "get_spawn_strict", None)
    row = strict(spawn_id) if callable(strict) else store.get_spawn(spawn_id)
    if row is None:
        raise EffectiveClaimIterationConflict("iteration spawn is unavailable")
    return row


def _prefix_body(
    body: ResearchArtifactBody, *, count: int, expected_hash: str | None = None
) -> ResearchArtifactBody:
    prefix = [
        item.model_dump(mode="json")
        for item in body.owner_claim_compensations[:count]
    ]
    candidates: list[dict[str, object]] = []
    base = body.model_dump(mode="json")
    if prefix:
        candidates.append({**base, "schema_version": 4, "owner_claim_compensations": prefix})
    else:
        v3 = {**base, "schema_version": 3}
        v3.pop("owner_claim_compensations", None)
        candidates.extend((v3, {**base, "schema_version": 4, "owner_claim_compensations": []}))
    matches = []
    for payload in candidates:
        candidate = ResearchArtifactBody.model_validate(payload)
        if expected_hash is None or candidate.content_hash() == expected_hash:
            matches.append(candidate)
    if len(matches) != 1:
        raise EffectiveClaimIterationConflict("iteration artifact prefix is ambiguous")
    return matches[0]


def project_effective_claim_iterations(
    *,
    body: ResearchArtifactBody,
    claim_index: int,
    authority: ArtifactAuthority,
    owner_account_digest: str,
    engagement_store: EngagementStore,
    session_store: SessionStore,
) -> tuple[EffectiveClaimIteration, ...]:
    if body.investigation_id != authority.investigation_id or not 0 <= claim_index < len(
        body.claim_support
    ):
        raise EffectiveClaimIterationConflict("iteration claim is unavailable")
    rounds: list[EffectiveClaimIteration] = []
    seen_contexts: set[str] = set()
    for index, compensation in enumerate(body.owner_claim_compensations):
        if not isinstance(compensation, ArtifactOwnerClaimProposalCompensation):
            continue
        if compensation.source_context_receipt_sha256 in seen_contexts:
            raise EffectiveClaimIterationConflict("iteration context is duplicated")
        seen_contexts.add(compensation.source_context_receipt_sha256)
        if compensation.claim_index != claim_index:
            continue
        prior = _prefix_body(
            body,
            count=index,
            expected_hash=compensation.prior_artifact_content_hash,
        )
        result = _prefix_body(body, count=index + 1)
        review = read_effective_context_review(
            compensation.source_context_receipt_sha256, store=engagement_store
        )
        if review is None or review.receipt_sha256 != compensation.source_review_receipt_sha256:
            raise EffectiveClaimIterationConflict("iteration review is unavailable")
        proposal = read_effective_context_proposal(
            review.receipt_sha256, store=engagement_store
        )
        if proposal is None or proposal.receipt_sha256 != compensation.source_proposal_receipt_sha256:
            raise EffectiveClaimIterationConflict("iteration proposal is unavailable")
        validate_effective_context_proposal(
            proposal=proposal,
            review=review,
            authority=authority,
            owner_account_digest=owner_account_digest,
        )
        session = _strict_session(review.session_id, session_store)
        spawn = _strict_spawn(review.spawn_id, engagement_store)
        try:
            candidate = resolve_claim_review_candidate(
                session_row=session,
                spawn_row=spawn,
                owner_account_digest=owner_account_digest,
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            raise EffectiveClaimIterationConflict("iteration candidate is corrupt") from exc
        session_goal = session.get("goal")
        if not isinstance(session_goal, str) or "\nQuestion: " not in session_goal:
            raise EffectiveClaimIterationConflict("iteration question is unavailable")
        question = session_goal.rsplit("\nQuestion: ", 1)[1]
        if (
            hashlib.sha256(session_goal.encode("utf-8")).hexdigest()
            != candidate.challenge.goal_sha256
            or hashlib.sha256(question.encode("utf-8")).hexdigest()
            != candidate.challenge.question_sha256
        ):
            raise EffectiveClaimIterationConflict("iteration question digest is stale")
        preview = build_effective_context_review_preview(
            candidate,
            artifact=prior,
            owner_account_digest=owner_account_digest,
            artifact_account_digest=authority.account_digest,
            artifact_investigation_digest=authority.investigation_digest,
            disposition="propose_compensation",
            rationale=review.rationale,
            proposed_claim=proposal.proposed_claim,
        )
        if (
            preview.preview_sha256 != review.preview_sha256
            or candidate.session_id != review.session_id
            or candidate.spawn_id != review.spawn_id
            or candidate.candidate_sha256 != review.candidate_sha256
            or candidate.candidate_text != review.candidate_text
            or compensation.prior_effective_claim != candidate.challenge.effective_claim
            or compensation.replacement_claim != proposal.proposed_claim
            or compensation.rationale != proposal.rationale
            or result.effective_owner_claim(claim_index)
            != (compensation.replacement_claim, compensation.transition_sha256)
        ):
            raise EffectiveClaimIterationConflict("iteration lineage is inconsistent")
        rounds.append(
            EffectiveClaimIteration(
                ordinal=len(rounds) + 1,
                prior_body=prior,
                result_body=result,
                candidate=candidate,
                review=review,
                proposal=proposal,
                compensation=compensation,
                question=question,
            )
        )
    return tuple(rounds)
