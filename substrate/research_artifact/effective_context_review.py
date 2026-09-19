"""Immutable three-channel owner review for effective-claim research output."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.engagement_spine.store import EngagementStore

from .claim_review import ClaimReviewCandidate
from .schema import ResearchArtifactBody


class EffectiveContextReviewConflict(ValueError):
    """The review command no longer matches immutable or canonical state."""


class EffectiveContextReviewAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    kind: Literal["effective_owner_context_review"] = "effective_owner_context_review"
    owner_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_investigation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_index: int = Field(ge=0, le=100_000)
    context_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    head_transition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: str = Field(min_length=1, max_length=512)
    spawn_id: str = Field(min_length=1, max_length=512)
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_text: str = Field(min_length=1, max_length=200_000)
    disposition: Literal["retain_current", "propose_compensation"]
    rationale: str = Field(min_length=1, max_length=4_000)
    preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mutation_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False
    permits_canonical_append: Literal[False] = False
    permits_graph_admission: Literal[False] = False
    permits_write: Literal[False] = False
    permits_benchmark_feedback: Literal[False] = False
    permits_publication: Literal[False] = False
    permits_provider_call: Literal[False] = False
    permits_spend: Literal[False] = False
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> EffectiveContextReviewAcceptance:
        if _sha(self.candidate_text) != self.candidate_sha256:
            raise ValueError("effective context review candidate digest mismatch")
        if self.receipt_sha256 != _digest(self.model_dump(exclude={"receipt_sha256"})):
            raise ValueError("effective context review digest mismatch")
        return self


class EffectiveContextCompensationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    kind: Literal["effective_context_compensation_proposal"] = (
        "effective_context_compensation_proposal"
    )
    owner_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_investigation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_index: int = Field(ge=0, le=100_000)
    context_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    head_transition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_claim: str = Field(min_length=1, max_length=20_000)
    rationale: str = Field(min_length=1, max_length=4_000)
    permits_canonical_append: Literal[False] = False
    grants_authority: Literal[False] = False
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> EffectiveContextCompensationProposal:
        if self.receipt_sha256 != _digest(self.model_dump(exclude={"receipt_sha256"})):
            raise ValueError("effective context proposal digest mismatch")
        return self


@dataclass(frozen=True)
class EffectiveContextReviewPreview:
    candidate: ClaimReviewCandidate
    artifact: ResearchArtifactBody
    disposition: Literal["retain_current", "propose_compensation"]
    rationale: str
    proposed_claim: str | None
    preview_sha256: str
    html: str

    def public_dict(self) -> dict[str, object]:
        challenge = self.candidate.challenge
        return {
            "status": "candidate",
            "artifact_content_hash": self.artifact.content_hash(),
            "claim_index": challenge.claim_index,
            "context_receipt_sha256": challenge.receipt_sha256,
            "head_transition_sha256": challenge.head_transition_sha256,
            "archived_claim": challenge.archived_claim,
            "effective_claim": challenge.effective_claim,
            "candidate_sha256": self.candidate.candidate_sha256,
            "candidate_text": self.candidate.candidate_text,
            "archived_evaluation": {
                "event_id": challenge.archived_evaluation_event_id,
                "scorer_id": challenge.archived_scorer_id,
                "relation": challenge.archived_relation,
                "score": challenge.archived_score,
            },
            "archived_direct_evidence_receipt_sha256s": list(
                challenge.archived_evidence_receipt_sha256s
            ),
            "archived_inherited_support": [
                item.model_dump(mode="json")
                for item in challenge.archived_inherited_support
            ],
            "disposition": self.disposition,
            "rationale": self.rationale,
            "proposed_claim": self.proposed_claim,
            "preview_sha256": self.preview_sha256,
            "html": self.html,
            "archive_grounded": False,
            "grants_authority": False,
            "permits_canonical_append": False,
        }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _exact(value: str, *, field: str, max_bytes: int) -> str:
    if (
        not value
        or not value.strip()
        or len(value.encode("utf-8")) > max_bytes
        or any(ord(char) < 0x20 and char not in "\n\t" for char in value)
    ):
        raise ValueError(f"{field} is invalid")
    return value


def review_document_id(context_receipt_sha256: str) -> str:
    return "effective-context-review:" + context_receipt_sha256


def proposal_document_id(review_receipt_sha256: str) -> str:
    return "effective-context-proposal:" + review_receipt_sha256


def review_spawn_lock_document_id(spawn_id: str) -> str:
    return "effective-context-review-spawn-lock:" + _sha(spawn_id)


def read_effective_context_review_by_spawn(
    spawn_id: str, *, store: EngagementStore
) -> EffectiveContextReviewAcceptance | None:
    strict = getattr(store, "get_document_strict", None)
    row = (
        strict(review_spawn_lock_document_id(spawn_id))
        if callable(strict)
        else store.get_document(review_spawn_lock_document_id(spawn_id))
    )
    if row is None:
        return None
    try:
        if row.get("kind") != "effective_owner_context_review":
            raise ValueError("effective context review spawn lock kind mismatch")
        review = EffectiveContextReviewAcceptance.model_validate(row.get("review"))
        if review.spawn_id != spawn_id:
            raise ValueError("effective context review spawn lock mismatch")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stored effective context review spawn lock is corrupt") from exc
    return review


def read_effective_context_proposal(
    review_receipt_sha256: str, *, store: EngagementStore
) -> EffectiveContextCompensationProposal | None:
    strict = getattr(store, "get_document_strict", None)
    row = (
        strict(proposal_document_id(review_receipt_sha256))
        if callable(strict)
        else store.get_document(proposal_document_id(review_receipt_sha256))
    )
    if row is None:
        return None
    try:
        if row.get("kind") != "effective_context_compensation_proposal":
            raise ValueError("effective context proposal kind mismatch")
        proposal = EffectiveContextCompensationProposal.model_validate(
            row.get("proposal")
        )
        if proposal.review_receipt_sha256 != review_receipt_sha256:
            raise ValueError("effective context proposal lineage mismatch")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stored effective context proposal is corrupt") from exc
    return proposal


def read_effective_context_review(
    context_receipt_sha256: str, *, store: EngagementStore
) -> EffectiveContextReviewAcceptance | None:
    strict = getattr(store, "get_document_strict", None)
    row = (
        strict(review_document_id(context_receipt_sha256))
        if callable(strict)
        else store.get_document(review_document_id(context_receipt_sha256))
    )
    if row is None:
        return None
    try:
        if row.get("kind") != "effective_owner_context_review":
            raise ValueError("effective context review kind mismatch")
        review = EffectiveContextReviewAcceptance.model_validate(row.get("review"))
        if review.context_receipt_sha256 != context_receipt_sha256:
            raise ValueError("effective context review lineage mismatch")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stored effective context review is corrupt") from exc
    return review


def build_effective_context_review_preview(
    candidate: ClaimReviewCandidate,
    *,
    artifact: ResearchArtifactBody,
    owner_account_digest: str,
    artifact_account_digest: str,
    artifact_investigation_digest: str,
    disposition: Literal["retain_current", "propose_compensation"],
    rationale: str,
    proposed_claim: str | None,
    review_state: Literal["candidate", "accepted"] = "candidate",
) -> EffectiveContextReviewPreview:
    challenge = candidate.challenge
    if challenge.schema_version not in (2, 3) or challenge.selection_kind != "effective_owner_claim":
        raise ValueError("effective context review requires a version-2 receipt")
    if (
        challenge.owner_account_digest != owner_account_digest
        or challenge.artifact_investigation_digest != artifact_investigation_digest
        or challenge.artifact_content_hash != artifact.content_hash()
        or not 0 <= challenge.claim_index < len(artifact.claim_support)
    ):
        raise EffectiveContextReviewConflict("effective context review artifact is stale")
    effective = artifact.effective_owner_claim(challenge.claim_index)
    if (
        effective is None
        or effective[0] != challenge.effective_claim
        or effective[1] != challenge.head_transition_sha256
        or artifact.claim_support[challenge.claim_index].claim != challenge.archived_claim
    ):
        raise EffectiveContextReviewConflict("effective context review head is stale")
    exact_rationale = _exact(rationale, field="review rationale", max_bytes=4_000)
    exact_proposal = (
        _exact(proposed_claim or "", field="proposed claim", max_bytes=20_000)
        if disposition == "propose_compensation"
        else None
    )
    identity = {
        "schema_version": 1,
        "owner_account_digest": owner_account_digest,
        "artifact_account_digest": artifact_account_digest,
        "artifact_investigation_digest": artifact_investigation_digest,
        "artifact_content_hash": artifact.content_hash(),
        "claim_index": challenge.claim_index,
        "context_receipt_sha256": challenge.receipt_sha256,
        "head_transition_sha256": challenge.head_transition_sha256,
        "session_id": candidate.session_id,
        "spawn_id": candidate.spawn_id,
        "candidate_sha256": candidate.candidate_sha256,
        "disposition": disposition,
        "rationale_sha256": _sha(exact_rationale),
        "proposed_claim_sha256": _sha(exact_proposal) if exact_proposal else None,
        "review_state": review_state,
    }
    preview_sha256 = _digest(identity)
    preview_html = (
        '<article data-effective-context-review="candidate">'
        "<h1>Effective owner context review</h1>"
        f"<h2>Archived evidence baseline</h2><p>{html.escape(challenge.archived_claim or '', quote=True)}</p>"
        f"<p>Archived evaluation: {html.escape(str(challenge.archived_relation), quote=True)} · {html.escape(str(challenge.archived_score), quote=True)} · {html.escape(str(challenge.archived_scorer_id), quote=True)}</p>"
        f"<p>Direct evidence receipts: {html.escape(', '.join(challenge.archived_evidence_receipt_sha256s) or 'none', quote=True)}</p>"
        f"<p>Inherited support: {html.escape(json.dumps([item.model_dump(mode='json') for item in challenge.archived_inherited_support], sort_keys=True, ensure_ascii=False), quote=True)}</p>"
        f"<h2>Owner-authored current wording</h2><p>{html.escape(challenge.effective_claim or '', quote=True)}</p>"
        f"<h2>Research candidate</h2><pre>{html.escape(candidate.candidate_text, quote=True)}</pre>"
        "<p>Review only — no canonical append or downstream authority.</p></article>"
    )
    return EffectiveContextReviewPreview(
        candidate=candidate,
        artifact=artifact,
        disposition=disposition,
        rationale=exact_rationale,
        proposed_claim=exact_proposal,
        preview_sha256=preview_sha256,
        html=preview_html,
    )


def accept_effective_context_review(
    preview: EffectiveContextReviewPreview,
    *,
    owner_account_digest: str,
    artifact_account_digest: str,
    artifact_investigation_digest: str,
    expected_preview_sha256: str,
    mutation_key: str,
    store: EngagementStore,
) -> tuple[EffectiveContextReviewAcceptance, EffectiveContextCompensationProposal | None]:
    if preview.preview_sha256 != expected_preview_sha256:
        raise EffectiveContextReviewConflict("effective context review preview is stale")
    key = _exact(mutation_key, field="mutation key", max_bytes=512)
    challenge = preview.candidate.challenge
    request = {
        "preview_sha256": expected_preview_sha256,
        "mutation_key_sha256": _sha(key),
        "context_receipt_sha256": challenge.receipt_sha256,
        "candidate_sha256": preview.candidate.candidate_sha256,
        "disposition": preview.disposition,
        "rationale_sha256": _sha(preview.rationale),
        "proposed_claim_sha256": _sha(preview.proposed_claim) if preview.proposed_claim else None,
    }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "effective_owner_context_review",
        "owner_account_digest": owner_account_digest,
        "artifact_account_digest": artifact_account_digest,
        "artifact_investigation_digest": artifact_investigation_digest,
        "artifact_content_hash": preview.artifact.content_hash(),
        "claim_index": challenge.claim_index,
        "context_receipt_sha256": challenge.receipt_sha256,
        "head_transition_sha256": challenge.head_transition_sha256,
        "session_id": preview.candidate.session_id,
        "spawn_id": preview.candidate.spawn_id,
        "candidate_sha256": preview.candidate.candidate_sha256,
        "candidate_text": preview.candidate.candidate_text,
        "disposition": preview.disposition,
        "rationale": preview.rationale,
        "preview_sha256": expected_preview_sha256,
        "mutation_key_sha256": request["mutation_key_sha256"],
        "request_sha256": _digest(request),
        "archive_grounded": False,
        "grants_authority": False,
        "permits_canonical_append": False,
        "permits_graph_admission": False,
        "permits_write": False,
        "permits_benchmark_feedback": False,
        "permits_publication": False,
        "permits_provider_call": False,
        "permits_spend": False,
    }
    review = EffectiveContextReviewAcceptance(
        **payload, receipt_sha256=_digest(payload)
    )
    # A proposal is claimed first. A crash can leave only a harmless,
    # unprojected proposal, but never an observable accepted review whose
    # required proposal is missing. Retry deterministically completes review.
    proposal: EffectiveContextCompensationProposal | None = None
    if preview.disposition == "propose_compensation":
        proposal_payload = {
            "schema_version": 1,
            "kind": "effective_context_compensation_proposal",
            "owner_account_digest": owner_account_digest,
            "artifact_account_digest": artifact_account_digest,
            "artifact_investigation_digest": artifact_investigation_digest,
            "artifact_content_hash": preview.artifact.content_hash(),
            "claim_index": challenge.claim_index,
            "context_receipt_sha256": challenge.receipt_sha256,
            "review_receipt_sha256": review.receipt_sha256,
            "head_transition_sha256": challenge.head_transition_sha256,
            "proposed_claim": preview.proposed_claim,
            "rationale": preview.rationale,
            "permits_canonical_append": False,
            "grants_authority": False,
        }
        proposal = EffectiveContextCompensationProposal(
            **proposal_payload, receipt_sha256=_digest(proposal_payload)
        )
        proposal_row = {
            "kind": "effective_context_compensation_proposal",
            "proposal": proposal.model_dump(mode="json"),
        }
        if not store.claim_document(
            proposal_document_id(review.receipt_sha256), proposal_row
        ):
            existing_proposal = read_effective_context_proposal(
                review.receipt_sha256, store=store
            )
            if existing_proposal != proposal:
                raise EffectiveContextReviewConflict(
                    "effective context proposal exists with another command"
                )
            proposal = existing_proposal
    row = {"kind": "effective_owner_context_review", "review": review.model_dump(mode="json")}
    lock_id = review_spawn_lock_document_id(review.spawn_id)
    if not store.claim_document(lock_id, row):
        locked = read_effective_context_review_by_spawn(review.spawn_id, store=store)
        if locked != review:
            raise EffectiveContextReviewConflict(
                "effective context review spawn is locked by another command"
            )
    document_id = review_document_id(challenge.receipt_sha256)
    if store.claim_document(document_id, row):
        persisted = review
    else:
        existing = read_effective_context_review(challenge.receipt_sha256, store=store)
        if existing != review or existing.request_sha256 != review.request_sha256:
            raise EffectiveContextReviewConflict(
                "effective context review exists with another command"
            )
        persisted = existing
    return persisted, proposal
