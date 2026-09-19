"""Immutable owner-authored reconsideration proposal for one exact artifact claim."""

from __future__ import annotations

import hashlib
import html
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.engagement_spine.store import EngagementStore

from .claim_review import ClaimReviewProjection

MAX_PROPOSED_CLAIM_BYTES = 20_000
MAX_RATIONALE_BYTES = 20_000
MAX_SELECTED_REVIEWS = 64


class ClaimReconsiderationConflict(ValueError):
    """A proposal already exists for this immutable claim version."""


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _exact_text(value: str, *, field: str, max_bytes: int) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field} is required")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{field} is too large")
    return value


class SelectedClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acceptance_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    challenge_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClaimReconsiderationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    kind: Literal["claim_reconsideration_proposal"] = "claim_reconsideration_proposal"
    status: Literal["owner_authored_reconsideration_proposal"] = (
        "owner_authored_reconsideration_proposal"
    )
    owner_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_investigation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_asset_id: str = Field(min_length=1, max_length=512)
    artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_index: int = Field(ge=0, le=100_000)
    claim_id: str = Field(min_length=1, max_length=1024)
    claim_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_claim: str = Field(min_length=1)
    selected_reviews: tuple[SelectedClaimReview, ...] = Field(
        min_length=1, max_length=MAX_SELECTED_REVIEWS
    )
    proposed_claim: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mutation_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def validate_self_hashes(self) -> ClaimReconsiderationProposal:
        _exact_text(
            self.original_claim,
            field="original claim",
            max_bytes=MAX_PROPOSED_CLAIM_BYTES,
        )
        _exact_text(
            self.proposed_claim,
            field="proposed claim",
            max_bytes=MAX_PROPOSED_CLAIM_BYTES,
        )
        _exact_text(self.rationale, field="rationale", max_bytes=MAX_RATIONALE_BYTES)
        if _sha(self.original_claim) != self.claim_sha256:
            raise ValueError("reconsideration original claim digest mismatch")
        receipts = [item.acceptance_receipt_sha256 for item in self.selected_reviews]
        if len(receipts) != len(set(receipts)):
            raise ValueError("reconsideration selected reviews contain duplicates")
        if self.receipt_sha256 != _digest(self.model_dump(exclude={"receipt_sha256"})):
            raise ValueError("reconsideration proposal digest mismatch")
        return self


def proposal_document_id(
    *, source_asset_id: str, artifact_content_hash: str, claim_index: int
) -> str:
    return "claim-reconsideration:" + _digest(
        {
            "source_asset_id": source_asset_id,
            "artifact_content_hash": artifact_content_hash,
            "claim_index": claim_index,
        }
    )


def _strict_document(store: EngagementStore, document_id: str) -> dict | None:
    strict = getattr(store, "get_document_strict", None)
    return strict(document_id) if callable(strict) else store.get_document(document_id)


def _select_reviews(
    reviews: tuple[ClaimReviewProjection, ...],
    acceptance_receipt_sha256s: tuple[str, ...],
) -> tuple[SelectedClaimReview, ...]:
    if not acceptance_receipt_sha256s:
        raise ValueError("at least one accepted review is required")
    if len(acceptance_receipt_sha256s) > MAX_SELECTED_REVIEWS:
        raise ValueError("too many selected reviews")
    if len(set(acceptance_receipt_sha256s)) != len(acceptance_receipt_sha256s):
        raise ValueError("selected reviews contain duplicates")
    by_receipt = {
        review.acceptance_receipt_sha256: review
        for review in reviews
        if review.status == "later_owner_accepted_counter_analysis"
    }
    selected: list[SelectedClaimReview] = []
    for receipt in acceptance_receipt_sha256s:
        review = by_receipt.get(receipt)
        if review is None:
            raise ValueError("selected review is not currently accepted for this claim")
        selected.append(
            SelectedClaimReview(
                acceptance_receipt_sha256=review.acceptance_receipt_sha256,
                challenge_receipt_sha256=review.challenge_receipt_sha256,
                candidate_sha256=review.candidate_sha256,
            )
        )
    return tuple(selected)


def build_claim_reconsideration_preview(
    *,
    owner_account_digest: str,
    artifact_account_digest: str,
    artifact_investigation_digest: str,
    source_asset_id: str,
    artifact_content_hash: str,
    claim_index: int,
    claim_id: str,
    original_claim: str,
    reviews: tuple[ClaimReviewProjection, ...],
    acceptance_receipt_sha256s: tuple[str, ...],
    proposed_claim: str,
    rationale: str,
) -> dict[str, object]:
    original = _exact_text(
        original_claim, field="original claim", max_bytes=MAX_PROPOSED_CLAIM_BYTES
    )
    proposed = _exact_text(
        proposed_claim, field="proposed claim", max_bytes=MAX_PROPOSED_CLAIM_BYTES
    )
    reason = _exact_text(rationale, field="rationale", max_bytes=MAX_RATIONALE_BYTES)
    selected = _select_reviews(reviews, acceptance_receipt_sha256s)
    payload = {
        "state": "candidate",
        "owner_account_digest": owner_account_digest,
        "artifact_account_digest": artifact_account_digest,
        "artifact_investigation_digest": artifact_investigation_digest,
        "source_asset_id": source_asset_id,
        "artifact_content_hash": artifact_content_hash,
        "claim_index": claim_index,
        "claim_id": claim_id,
        "claim_sha256": _sha(original),
        "original_claim": original,
        "selected_reviews": [item.model_dump(mode="json") for item in selected],
        "proposed_claim": proposed,
        "rationale": reason,
    }
    return {
        **payload,
        "preview_sha256": _digest(payload),
        "html": (
            '<section class="claim-reconsideration-preview"><h3>Proposed claim</h3><p>'
            + html.escape(proposed, quote=True)
            + "</p><h3>Owner rationale</h3><p>"
            + html.escape(reason, quote=True)
            + "</p><p>Proposal only — not terminal truth, provenance, or authority.</p></section>"
        ),
    }


def create_claim_reconsideration_proposal(
    *,
    preview: dict[str, object],
    expected_preview_sha256: str,
    mutation_key: str,
    store: EngagementStore,
) -> ClaimReconsiderationProposal:
    preview_keys = (
        "state",
        "owner_account_digest",
        "artifact_account_digest",
        "artifact_investigation_digest",
        "source_asset_id",
        "artifact_content_hash",
        "claim_index",
        "claim_id",
        "claim_sha256",
        "original_claim",
        "selected_reviews",
        "proposed_claim",
        "rationale",
    )
    try:
        preview_payload = {key: preview[key] for key in preview_keys}
    except KeyError as exc:
        raise ClaimReconsiderationConflict("reconsideration preview is malformed") from exc
    recomputed_preview_sha256 = _digest(preview_payload)
    if (
        preview.get("preview_sha256") != recomputed_preview_sha256
        or recomputed_preview_sha256 != expected_preview_sha256
    ):
        raise ClaimReconsiderationConflict("reconsideration preview is stale")
    cleaned_key = _exact_text(mutation_key, field="mutation key", max_bytes=512)
    payload = {
        "schema_version": 1,
        "kind": "claim_reconsideration_proposal",
        "status": "owner_authored_reconsideration_proposal",
        **{key: preview[key] for key in (
            "owner_account_digest", "artifact_account_digest",
            "artifact_investigation_digest", "source_asset_id",
            "artifact_content_hash", "claim_index", "claim_id", "claim_sha256",
            "original_claim", "selected_reviews", "proposed_claim", "rationale",
            "preview_sha256",
        )},
        "mutation_key_sha256": _sha(cleaned_key),
    }
    payload["request_sha256"] = _digest(payload)
    payload["grants_authority"] = False
    proposal = ClaimReconsiderationProposal(
        **payload, receipt_sha256=_digest(payload)
    )
    document_id = proposal_document_id(
        source_asset_id=proposal.source_asset_id,
        artifact_content_hash=proposal.artifact_content_hash,
        claim_index=proposal.claim_index,
    )
    row = {"kind": "claim_reconsideration_proposal", "proposal": proposal.model_dump()}
    if store.claim_document(document_id, row):
        return proposal
    existing = read_claim_reconsideration_proposal(
        source_asset_id=proposal.source_asset_id,
        artifact_content_hash=proposal.artifact_content_hash,
        claim_index=proposal.claim_index,
        store=store,
    )
    if existing != proposal:
        raise ClaimReconsiderationConflict(
            "claim reconsideration proposal already exists with another command"
        )
    return existing


def read_claim_reconsideration_proposal(
    *, source_asset_id: str, artifact_content_hash: str, claim_index: int,
    store: EngagementStore,
) -> ClaimReconsiderationProposal | None:
    row = _strict_document(
        store,
        proposal_document_id(
            source_asset_id=source_asset_id,
            artifact_content_hash=artifact_content_hash,
            claim_index=claim_index,
        ),
    )
    if row is None:
        return None
    try:
        if row.get("kind") != "claim_reconsideration_proposal":
            raise ValueError("reconsideration outer kind mismatch")
        proposal = ClaimReconsiderationProposal.model_validate(row.get("proposal"))
        if (
            proposal.source_asset_id != source_asset_id
            or proposal.artifact_content_hash != artifact_content_hash
            or proposal.claim_index != claim_index
        ):
            raise ValueError("reconsideration lookup lineage mismatch")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stored claim reconsideration proposal is corrupt") from exc
    return proposal


def project_claim_reconsideration_proposal(
    *, proposal: ClaimReconsiderationProposal | None,
    owner_account_digest: str, artifact_account_digest: str,
    artifact_investigation_digest: str, claim_id: str, original_claim: str,
    reviews: tuple[ClaimReviewProjection, ...],
) -> ClaimReconsiderationProposal | None:
    if proposal is None:
        return None
    current = {
        review.acceptance_receipt_sha256: review
        for review in reviews
        if review.status == "later_owner_accepted_counter_analysis"
    }
    if (
        proposal.owner_account_digest != owner_account_digest
        or proposal.artifact_account_digest != artifact_account_digest
        or proposal.artifact_investigation_digest != artifact_investigation_digest
        or proposal.claim_id != claim_id
        or proposal.original_claim != original_claim
        or proposal.claim_sha256 != _sha(original_claim)
    ):
        raise RuntimeError("claim reconsideration proposal lineage is corrupt")
    for selected in proposal.selected_reviews:
        review = current.get(selected.acceptance_receipt_sha256)
        if review is None:
            return None
        if (
            review.challenge_receipt_sha256 != selected.challenge_receipt_sha256
            or review.candidate_sha256 != selected.candidate_sha256
        ):
            raise RuntimeError("claim reconsideration selected review lineage is corrupt")
    return proposal
