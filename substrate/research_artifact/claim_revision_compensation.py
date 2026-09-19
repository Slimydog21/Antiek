"""Append-only compensation for canonical owner claim revision truth."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from typing import Literal

from .authority import ArtifactAuthority
from .render import render_html
from .schema import (
    ArtifactOwnerClaimCompensation,
    ArtifactOwnerClaimCompensationRecord,
    ArtifactOwnerClaimProposalCompensation,
    ResearchArtifactBody,
)
from .storage import FilesystemArtifactStore

CompensationOperation = Literal[
    "restore_archived_terminal", "supersede_owner_revision"
]


class ClaimRevisionCompensationConflict(ValueError):
    """The requested compensation no longer names the current chain head."""


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def _exact_text(value: str, *, field: str, max_bytes: int = 20_000) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field} is required")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{field} is too large")
    return value


@dataclass(frozen=True)
class ClaimRevisionCompensationPreview:
    prior_body: ResearchArtifactBody
    prospective_body: ResearchArtifactBody
    prospective_html: str
    compensation: ArtifactOwnerClaimCompensationRecord
    preview_sha256: str

    def public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "status": "candidate",
            "operation": self.compensation.operation,
            "prior_artifact_content_hash": self.prior_body.content_hash(),
            "prospective_artifact_content_hash": self.prospective_body.content_hash(),
            "supersedes_transition_sha256": self.compensation.supersedes_transition_sha256,
            "prior_effective_claim": self.compensation.prior_effective_claim,
            "replacement_claim": self.compensation.replacement_claim,
            "rationale": self.compensation.rationale,
            "transition_sha256": self.compensation.transition_sha256,
            "preview_sha256": self.preview_sha256,
            "html": (
                '<section class="claim-revision-compensation-preview"><h3>Current owner claim</h3><p>'
                + html.escape(self.compensation.prior_effective_claim, quote=True)
                + "</p><h3>Prospective replacement</h3><p>"
                + html.escape(self.compensation.replacement_claim, quote=True)
                + "</p><p>Append-only compensation — no prior transition is deleted.</p></section>"
            ),
        }
        if isinstance(self.compensation, ArtifactOwnerClaimProposalCompensation):
            result.update(
                source_context_receipt_sha256=(
                    self.compensation.source_context_receipt_sha256
                ),
                source_review_receipt_sha256=(
                    self.compensation.source_review_receipt_sha256
                ),
                source_proposal_receipt_sha256=(
                    self.compensation.source_proposal_receipt_sha256
                ),
            )
        return result


def build_claim_revision_compensation_preview(
    *,
    authority: ArtifactAuthority,
    owner_account_digest: str,
    prior_body: ResearchArtifactBody,
    claim_index: int,
    supersedes_transition_sha256: str,
    operation: CompensationOperation,
    replacement_claim: str | None,
    rationale: str,
    mutation_key: str,
    source_context_receipt_sha256: str | None = None,
    source_review_receipt_sha256: str | None = None,
    source_proposal_receipt_sha256: str | None = None,
) -> ClaimRevisionCompensationPreview:
    if not 0 <= claim_index < len(prior_body.claim_support):
        raise ValueError("claim compensation index is unavailable")
    roots = [
        revision
        for revision in prior_body.owner_claim_revisions
        if revision.claim_index == claim_index
    ]
    if len(roots) != 1:
        raise ValueError("claim compensation root revision is unavailable")
    root = roots[0]
    if (
        root.owner_account_digest != owner_account_digest
        or root.artifact_account_digest != authority.account_digest
        or root.artifact_investigation_digest != authority.investigation_digest
    ):
        raise ValueError("claim compensation owner lineage is stale")
    effective = prior_body.effective_owner_claim(claim_index)
    if effective is None or effective[1] != supersedes_transition_sha256:
        raise ClaimRevisionCompensationConflict("claim compensation head is stale")
    reason = _exact_text(rationale, field="compensation rationale")
    key = _exact_text(mutation_key, field="mutation key", max_bytes=512)
    if operation == "restore_archived_terminal":
        replacement = root.original_claim
        if replacement_claim not in (None, "", replacement):
            raise ValueError("restoration wording is server-authored")
    elif operation == "supersede_owner_revision":
        replacement = _exact_text(
            replacement_claim or "", field="replacement claim"
        )
    else:
        raise ValueError("claim compensation operation is invalid")
    sources = (
        source_context_receipt_sha256,
        source_review_receipt_sha256,
        source_proposal_receipt_sha256,
    )
    if any(sources) and not all(sources):
        raise ValueError("proposal compensation lineage is incomplete")
    payload: dict[str, object] = {
        "schema_version": 2 if all(sources) else 1,
        "status": "owner_claim_revision_compensation",
        "operation": operation,
        "owner_account_digest": owner_account_digest,
        "artifact_account_digest": authority.account_digest,
        "artifact_investigation_digest": authority.investigation_digest,
        "prior_artifact_content_hash": prior_body.content_hash(),
        "claim_index": claim_index,
        "supersedes_transition_sha256": effective[1],
        "prior_effective_claim_sha256": _sha(effective[0]),
        "prior_effective_claim": effective[0],
        "replacement_claim": replacement,
        "rationale": reason,
        "mutation_key_sha256": _sha(key),
        "archive_grounded": False,
        "grants_authority": False,
    }
    if all(sources):
        payload.update(
            source_context_receipt_sha256=source_context_receipt_sha256,
            source_review_receipt_sha256=source_review_receipt_sha256,
            source_proposal_receipt_sha256=source_proposal_receipt_sha256,
        )
        compensation: ArtifactOwnerClaimCompensationRecord = (
            ArtifactOwnerClaimProposalCompensation(
                **payload, transition_sha256=_digest(payload)
            )
        )
    else:
        compensation = ArtifactOwnerClaimCompensation(
            **payload, transition_sha256=_digest(payload)
        )
    prospective = ResearchArtifactBody.model_validate(
        {
            **prior_body.model_dump(mode="json"),
            "schema_version": 4,
            "owner_claim_compensations": [
                *[
                    item.model_dump(mode="json")
                    for item in prior_body.owner_claim_compensations
                ],
                compensation.model_dump(mode="json"),
            ],
        }
    )
    prospective_html = render_html(prospective)
    preview_sha256 = _digest(
        {
            "prior_artifact_content_hash": prior_body.content_hash(),
            "prospective_artifact_content_hash": prospective.content_hash(),
            "transition_sha256": compensation.transition_sha256,
            "prospective_html_sha256": _sha(prospective_html),
        }
    )
    return ClaimRevisionCompensationPreview(
        prior_body=prior_body,
        prospective_body=prospective,
        prospective_html=prospective_html,
        compensation=compensation,
        preview_sha256=preview_sha256,
    )


def accept_claim_revision_compensation(
    *,
    authority: ArtifactAuthority,
    owner_account_digest: str,
    claim_index: int,
    supersedes_transition_sha256: str,
    operation: CompensationOperation,
    replacement_claim: str | None,
    rationale: str,
    mutation_key: str,
    expected_preview_sha256: str,
    expected_transition_sha256: str,
    store: FilesystemArtifactStore,
    source_context_receipt_sha256: str | None = None,
    source_review_receipt_sha256: str | None = None,
    source_proposal_receipt_sha256: str | None = None,
) -> dict[str, object]:
    from .import_notes import parse_body_from_html

    with store.mutation_lock(authority):
        current_html = store.read(authority)
        current_body = parse_body_from_html(current_html)
        preview = build_claim_revision_compensation_preview(
            authority=authority,
            owner_account_digest=owner_account_digest,
            prior_body=current_body,
            claim_index=claim_index,
            supersedes_transition_sha256=supersedes_transition_sha256,
            operation=operation,
            replacement_claim=replacement_claim,
            rationale=rationale,
            mutation_key=mutation_key,
            source_context_receipt_sha256=source_context_receipt_sha256,
            source_review_receipt_sha256=source_review_receipt_sha256,
            source_proposal_receipt_sha256=source_proposal_receipt_sha256,
        )
        if (
            preview.preview_sha256 != expected_preview_sha256
            or preview.compensation.transition_sha256
            != expected_transition_sha256
        ):
            raise ClaimRevisionCompensationConflict(
                "claim compensation preview is stale"
            )
        store.claim_history(
            authority,
            body_content_hash=current_body.content_hash(),
            html=current_html,
        )
        store.write(authority, preview.prospective_html)
    return compensation_acceptance(preview.prospective_body, preview.compensation)


def compensation_acceptance(
    body: ResearchArtifactBody, compensation: ArtifactOwnerClaimCompensationRecord
) -> dict[str, object]:
    acceptance: dict[str, object] = {
        "status": "accepted",
        "operation": compensation.operation,
        "prior_artifact_content_hash": compensation.prior_artifact_content_hash,
        "artifact_content_hash": body.content_hash(),
        "supersedes_transition_sha256": compensation.supersedes_transition_sha256,
        "transition_sha256": compensation.transition_sha256,
        "history_content_hash": compensation.prior_artifact_content_hash,
        "effective_owner_claim": compensation.replacement_claim,
        "archive_grounded": False,
        "grants_authority": False,
    }
    if isinstance(compensation, ArtifactOwnerClaimProposalCompensation):
        acceptance.update(
            source_context_receipt_sha256=compensation.source_context_receipt_sha256,
            source_review_receipt_sha256=compensation.source_review_receipt_sha256,
            source_proposal_receipt_sha256=compensation.source_proposal_receipt_sha256,
        )
    return acceptance


def replay_claim_revision_compensation(
    *,
    body: ResearchArtifactBody,
    prior_artifact_content_hash: str,
    claim_index: int,
    supersedes_transition_sha256: str,
    operation: CompensationOperation,
    replacement_claim: str | None,
    rationale: str,
    mutation_key: str,
) -> dict[str, object] | None:
    if not 0 <= claim_index < len(body.claim_support):
        raise ClaimRevisionCompensationConflict("claim compensation index is unavailable")
    matches = [
        item
        for item in body.owner_claim_compensations
        if item.prior_artifact_content_hash == prior_artifact_content_hash
        and item.claim_index == claim_index
        and item.supersedes_transition_sha256 == supersedes_transition_sha256
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ClaimRevisionCompensationConflict(
            "claim compensation replay is ambiguous"
        )
    compensation = matches[0]
    expected_replacement = (
        body.claim_support[claim_index].claim
        if operation == "restore_archived_terminal"
        else replacement_claim
    )
    if (
        compensation.operation != operation
        or compensation.replacement_claim != expected_replacement
        or compensation.rationale != rationale
        or compensation.mutation_key_sha256 != _sha(mutation_key)
    ):
        raise ClaimRevisionCompensationConflict(
            "claim compensation already exists with another command"
        )
    match_index = body.owner_claim_compensations.index(compensation)
    historical_result = ResearchArtifactBody.model_validate(
        {
            **body.model_dump(mode="json"),
            "schema_version": 4,
            "owner_claim_compensations": [
                item.model_dump(mode="json")
                for item in body.owner_claim_compensations[: match_index + 1]
            ],
        }
    )
    return compensation_acceptance(historical_result, compensation)
