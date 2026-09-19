"""Atomic acceptance of one exact reconsideration proposal into artifact v3."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass

from .authority import ArtifactAuthority
from .claim_reconsideration import ClaimReconsiderationProposal
from .claim_review import ClaimReviewProjection
from .render import render_html
from .schema import ArtifactOwnerClaimRevision, ResearchArtifactBody
from .storage import FilesystemArtifactStore


class ClaimRevisionConflict(ValueError):
    """The proposed artifact transition is stale or already differs."""


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ClaimRevisionPreview:
    prior_body: ResearchArtifactBody
    prospective_body: ResearchArtifactBody
    prospective_html: str
    preview_sha256: str
    transition_sha256: str

    def public_dict(self) -> dict[str, object]:
        revision = self.prospective_body.owner_claim_revisions[-1]
        return {
            "status": "candidate",
            "prior_artifact_content_hash": self.prior_body.content_hash(),
            "prospective_artifact_content_hash": self.prospective_body.content_hash(),
            "proposal_receipt_sha256": revision.proposal_receipt_sha256,
            "claim_index": revision.claim_index,
            "original_claim": revision.original_claim,
            "revised_claim": revision.revised_claim,
            "rationale": revision.rationale,
            "transition_sha256": self.transition_sha256,
            "preview_sha256": self.preview_sha256,
            "html": (
                '<section class="claim-revision-preview"><h3>Archived terminal claim</h3><p>'
                + html.escape(revision.original_claim, quote=True)
                + "</p><h3>Prospective owner revision</h3><p>"
                + html.escape(revision.revised_claim, quote=True)
                + "</p><p>Owner-authored revision only — not archive-grounded or model-verified.</p></section>"
            ),
        }


def _build_claim_revision_preview(
    *,
    authority: ArtifactAuthority,
    owner_account_digest: str,
    prior_body: ResearchArtifactBody,
    proposal: ClaimReconsiderationProposal,
    mutation_key: str,
) -> ClaimRevisionPreview:
    if not mutation_key or not mutation_key.strip() or len(mutation_key.encode()) > 512:
        raise ValueError("claim revision mutation key is invalid")
    prior_hash = prior_body.content_hash()
    if (
        proposal.owner_account_digest != owner_account_digest
        or proposal.artifact_account_digest != authority.account_digest
        or proposal.artifact_investigation_digest != authority.investigation_digest
        or proposal.source_asset_id != authority.investigation_id
        or proposal.artifact_content_hash != prior_hash
        or not 0 <= proposal.claim_index < len(prior_body.claim_support)
    ):
        raise ValueError("claim revision proposal identity is stale")
    if any(
        revision.claim_index == proposal.claim_index
        for revision in prior_body.owner_claim_revisions
    ):
        raise ClaimRevisionConflict("claim already has an owner revision")
    original = prior_body.claim_support[proposal.claim_index].claim
    claim_id = f"artifact-v2:{prior_hash}:{proposal.claim_index}"
    if (
        proposal.claim_id != claim_id
        or proposal.original_claim != original
        or proposal.claim_sha256 != _sha(original)
    ):
        raise ValueError("claim revision proposal claim lineage is stale")
    transition_payload = {
        "schema_version": 1,
        "status": "owner_accepted_claim_revision",
        "owner_account_digest": owner_account_digest,
        "artifact_account_digest": authority.account_digest,
        "artifact_investigation_digest": authority.investigation_digest,
        "prior_artifact_content_hash": prior_hash,
        "claim_index": proposal.claim_index,
        "claim_id": proposal.claim_id,
        "original_claim_sha256": proposal.claim_sha256,
        "original_claim": original,
        "revised_claim": proposal.proposed_claim,
        "rationale": proposal.rationale,
        "proposal_receipt_sha256": proposal.receipt_sha256,
        "selected_acceptance_receipt_sha256s": tuple(
            item.acceptance_receipt_sha256 for item in proposal.selected_reviews
        ),
        "mutation_key_sha256": _sha(mutation_key),
        "archive_grounded": False,
        "grants_authority": False,
    }
    transition_sha256 = _digest(transition_payload)
    revision = ArtifactOwnerClaimRevision(
        **transition_payload, transition_sha256=transition_sha256
    )
    prospective_body = ResearchArtifactBody.model_validate(
        {
            **prior_body.model_dump(mode="json"),
            "schema_version": 3,
            "owner_claim_revisions": [
                *[
                    item.model_dump(mode="json")
                    for item in prior_body.owner_claim_revisions
                ],
                revision.model_dump(mode="json"),
            ],
        }
    )
    prospective_html = render_html(prospective_body)
    preview_payload = {
        "prior_artifact_content_hash": prior_hash,
        "prospective_artifact_content_hash": prospective_body.content_hash(),
        "proposal_receipt_sha256": proposal.receipt_sha256,
        "transition_sha256": transition_sha256,
        "prospective_html_sha256": _sha(prospective_html),
    }
    return ClaimRevisionPreview(
        prior_body=prior_body,
        prospective_body=prospective_body,
        prospective_html=prospective_html,
        preview_sha256=_digest(preview_payload),
        transition_sha256=transition_sha256,
    )


def build_claim_revision_preview(
    *,
    authority: ArtifactAuthority,
    owner_account_digest: str,
    prior_body: ResearchArtifactBody,
    proposal: ClaimReconsiderationProposal,
    reviews: tuple[ClaimReviewProjection, ...],
    mutation_key: str,
) -> ClaimRevisionPreview:
    from .claim_reconsideration import project_claim_reconsideration_proposal

    if not 0 <= proposal.claim_index < len(prior_body.claim_support):
        raise ValueError("claim revision proposal index is stale")
    current = project_claim_reconsideration_proposal(
        proposal=proposal,
        owner_account_digest=owner_account_digest,
        artifact_account_digest=authority.account_digest,
        artifact_investigation_digest=authority.investigation_digest,
        claim_id=f"artifact-v2:{prior_body.content_hash()}:{proposal.claim_index}",
        original_claim=prior_body.claim_support[proposal.claim_index].claim,
        reviews=reviews,
    )
    if current is None:
        raise ClaimRevisionConflict("claim revision proposal inputs are no longer accepted")
    return _build_claim_revision_preview(
        authority=authority,
        owner_account_digest=owner_account_digest,
        prior_body=prior_body,
        proposal=current,
        mutation_key=mutation_key,
    )


def rebuild_claim_revision_preview_for_replay(
    *,
    authority: ArtifactAuthority,
    owner_account_digest: str,
    prior_body: ResearchArtifactBody,
    proposal: ClaimReconsiderationProposal,
    mutation_key: str,
) -> ClaimRevisionPreview:
    """Reconstruct an already-accepted transition from immutable inputs."""
    return _build_claim_revision_preview(
        authority=authority,
        owner_account_digest=owner_account_digest,
        prior_body=prior_body,
        proposal=proposal,
        mutation_key=mutation_key,
    )


def accept_claim_revision(
    *,
    authority: ArtifactAuthority,
    owner_account_digest: str,
    proposal: ClaimReconsiderationProposal,
    reviews: tuple[ClaimReviewProjection, ...],
    mutation_key: str,
    expected_proposal_receipt_sha256: str,
    expected_preview_sha256: str,
    expected_transition_sha256: str,
    store: FilesystemArtifactStore,
) -> dict[str, object]:
    if proposal.receipt_sha256 != expected_proposal_receipt_sha256:
        raise ClaimRevisionConflict("claim revision preview is stale")
    from .import_notes import parse_body_from_html

    with store.mutation_lock(authority):
        current_html = store.read(authority)
        current_body = parse_body_from_html(current_html)
        try:
            preview = build_claim_revision_preview(
                authority=authority,
                owner_account_digest=owner_account_digest,
                prior_body=current_body,
                proposal=proposal,
                reviews=reviews,
                mutation_key=mutation_key,
            )
        except ClaimRevisionConflict:
            raise
        except (ValueError, RuntimeError) as exc:
            raise ClaimRevisionConflict("canonical artifact changed after preview") from exc
        if (
            preview.preview_sha256 != expected_preview_sha256
            or preview.transition_sha256 != expected_transition_sha256
        ):
            raise ClaimRevisionConflict("claim revision preview is stale")
        store.claim_history(
            authority,
            body_content_hash=preview.prior_body.content_hash(),
            html=current_html,
        )
        store.write(authority, preview.prospective_html)
    revision = preview.prospective_body.owner_claim_revisions[-1]
    return {
        "status": "accepted",
        "prior_artifact_content_hash": preview.prior_body.content_hash(),
        "artifact_content_hash": preview.prospective_body.content_hash(),
        "proposal_receipt_sha256": revision.proposal_receipt_sha256,
        "transition_sha256": revision.transition_sha256,
        "history_content_hash": preview.prior_body.content_hash(),
        "archive_grounded": False,
        "grants_authority": False,
    }


def replay_claim_revision(
    *,
    body: ResearchArtifactBody,
    prior_artifact_content_hash: str,
    proposal_receipt_sha256: str,
    mutation_key: str,
    claim_index: int,
) -> dict[str, object] | None:
    mutation_hash = _sha(mutation_key)
    matches = [
        revision
        for revision in body.owner_claim_revisions
        if revision.prior_artifact_content_hash == prior_artifact_content_hash
        and revision.proposal_receipt_sha256 == proposal_receipt_sha256
        and revision.claim_index == claim_index
    ]
    if not matches:
        return None
    if len(matches) != 1 or matches[0].mutation_key_sha256 != mutation_hash:
        raise ClaimRevisionConflict("claim revision already exists with another command")
    revision = matches[0]
    return {
        "status": "accepted",
        "prior_artifact_content_hash": prior_artifact_content_hash,
        "artifact_content_hash": body.content_hash(),
        "proposal_receipt_sha256": proposal_receipt_sha256,
        "transition_sha256": revision.transition_sha256,
        "history_content_hash": prior_artifact_content_hash,
        "archive_grounded": False,
        "grants_authority": False,
    }
