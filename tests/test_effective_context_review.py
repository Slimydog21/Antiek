import hashlib
import json

import pytest

from substrate.engagement_spine import InMemoryEngagementStore
from substrate.engagement_spine.spawn import complete_spawn
from substrate.research_artifact.claim_challenge import (
    build_effective_owner_claim_context_receipt,
)
from substrate.research_artifact.claim_review import ClaimReviewCandidate
from substrate.research_artifact.effective_context_review import (
    EffectiveContextReviewConflict,
    accept_effective_context_review,
    build_effective_context_review_preview,
    read_effective_context_proposal,
    read_effective_context_review,
)
from substrate.research_artifact.schema import (
    ArtifactOwnerClaimRevision,
    ResearchArtifactBody,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _fixture():
    base = ResearchArtifactBody(
        investigation_id="context-review",
        problem_question="q",
        synthesis_event_id="synth",
        claim_support=[{"claim": "Archived wording."}],
    )
    root_payload = {
        "schema_version": 1,
        "status": "owner_accepted_claim_revision",
        "owner_account_digest": "a" * 64,
        "artifact_account_digest": "b" * 64,
        "artifact_investigation_digest": "c" * 64,
        "prior_artifact_content_hash": base.content_hash(),
        "claim_index": 0,
        "claim_id": f"artifact-v2:{base.content_hash()}:0",
        "original_claim_sha256": hashlib.sha256(b"Archived wording.").hexdigest(),
        "original_claim": "Archived wording.",
        "revised_claim": "Current owner wording.",
        "rationale": "Owner judgment.",
        "proposal_receipt_sha256": "d" * 64,
        "selected_acceptance_receipt_sha256s": ("e" * 64,),
        "mutation_key_sha256": "f" * 64,
        "archive_grounded": False,
        "grants_authority": False,
    }
    root = ArtifactOwnerClaimRevision(
        **root_payload, transition_sha256=_digest(root_payload)
    )
    artifact = ResearchArtifactBody.model_validate({
        **base.model_dump(mode="json"),
        "schema_version": 3,
        "owner_claim_revisions": [root.model_dump(mode="json")],
    })
    receipt = build_effective_owner_claim_context_receipt(
        owner_account_digest="a" * 64,
        source_asset_id="context-review",
        artifact_investigation_digest="c" * 64,
        artifact_content_hash=artifact.content_hash(),
        synthesis_event_id="synth",
        claim_index=0,
        claim_id=f"artifact-v2:{artifact.content_hash()}:0",
        archived_claim="Archived wording.",
        effective_claim="Current owner wording.",
        root_transition_sha256=root.transition_sha256,
        revision_transition_sha256s=(root.transition_sha256,),
        evaluation_event_id="eval",
        scorer_id="nli",
        relation="entailed",
        score=0.8,
        evidence_receipt_sha256s=(),
        archived_inherited_support=(),
        model_id=None,
        research_tier="deep",
        goal="Investigate.",
        question="What changed?",
        mutation_key="context-one",
    )
    candidate = ClaimReviewCandidate(
        challenge=receipt,
        session_id="session-one",
        spawn_id="spawn-one",
        candidate_text="Candidate analysis.  ",
        candidate_sha256=hashlib.sha256(b"Candidate analysis.  ").hexdigest(),
    )
    return artifact, root, candidate


def test_three_channel_preview_and_immutable_acceptance_are_non_executing():
    artifact, root, candidate = _fixture()
    store = InMemoryEngagementStore()
    preview = build_effective_context_review_preview(
        candidate,
        artifact=artifact,
        owner_account_digest="a" * 64,
        artifact_account_digest="b" * 64,
        artifact_investigation_digest="c" * 64,
        disposition="propose_compensation",
        rationale="Consider a narrower wording.",
        proposed_claim="Narrower owner wording.",
    )
    public = preview.public_dict()
    assert public["archived_claim"] == "Archived wording."
    assert public["effective_claim"] == "Current owner wording."
    assert public["candidate_text"] == "Candidate analysis.  "
    assert public["permits_canonical_append"] is False
    assert "<script>" not in public["html"]
    accepted, proposal = accept_effective_context_review(
        preview,
        owner_account_digest="a" * 64,
        artifact_account_digest="b" * 64,
        artifact_investigation_digest="c" * 64,
        expected_preview_sha256=preview.preview_sha256,
        mutation_key="review-one",
        store=store,
    )
    assert accepted.head_transition_sha256 == root.transition_sha256
    assert accepted.permits_canonical_append is False
    assert proposal is not None
    assert proposal.proposed_claim == "Narrower owner wording."
    assert proposal.review_receipt_sha256 == accepted.receipt_sha256
    assert proposal.permits_canonical_append is False
    assert read_effective_context_proposal(
        accepted.receipt_sha256, store=store
    ) == proposal
    store.put_spawn({"spawn_id": "spawn-one"})
    with pytest.raises(ValueError, match="output is immutable"):
        complete_spawn("spawn-one", store=store, output_text="Substituted output.")
    assert read_effective_context_review(
        candidate.challenge.receipt_sha256, store=store
    ) == accepted
    assert accept_effective_context_review(
        preview,
        owner_account_digest="a" * 64,
        artifact_account_digest="b" * 64,
        artifact_investigation_digest="c" * 64,
        expected_preview_sha256=preview.preview_sha256,
        mutation_key="review-one",
        store=store,
    ) == (accepted, proposal)


def test_changed_review_and_stale_head_fail_closed():
    artifact, _, candidate = _fixture()
    store = InMemoryEngagementStore()
    first = build_effective_context_review_preview(
        candidate,
        artifact=artifact,
        owner_account_digest="a" * 64,
        artifact_account_digest="b" * 64,
        artifact_investigation_digest="c" * 64,
        disposition="retain_current",
        rationale="Keep current wording.",
        proposed_claim=None,
    )
    accept_effective_context_review(
        first,
        owner_account_digest="a" * 64,
        artifact_account_digest="b" * 64,
        artifact_investigation_digest="c" * 64,
        expected_preview_sha256=first.preview_sha256,
        mutation_key="one",
        store=store,
    )
    changed = build_effective_context_review_preview(
        candidate,
        artifact=artifact,
        owner_account_digest="a" * 64,
        artifact_account_digest="b" * 64,
        artifact_investigation_digest="c" * 64,
        disposition="retain_current",
        rationale="Changed rationale.",
        proposed_claim=None,
    )
    with pytest.raises(EffectiveContextReviewConflict, match="another command"):
        accept_effective_context_review(
            changed,
            owner_account_digest="a" * 64,
            artifact_account_digest="b" * 64,
            artifact_investigation_digest="c" * 64,
            expected_preview_sha256=changed.preview_sha256,
            mutation_key="two",
            store=store,
        )
    stale = artifact.model_copy(update={"problem_question": "changed"})
    with pytest.raises(EffectiveContextReviewConflict, match="artifact is stale"):
        build_effective_context_review_preview(
            candidate,
            artifact=stale,
            owner_account_digest="a" * 64,
            artifact_account_digest="b" * 64,
            artifact_investigation_digest="c" * 64,
            disposition="retain_current",
            rationale="Keep.",
            proposed_claim=None,
        )


def test_proposal_is_claimed_before_review_and_retry_recovers_interruption():
    artifact, _, candidate = _fixture()

    class InterruptReviewStore(InMemoryEngagementStore):
        fail_review_once = True

        def claim_document(self, document_id, row):
            if document_id.startswith("effective-context-review:") and self.fail_review_once:
                self.fail_review_once = False
                raise RuntimeError("simulated interruption before review publication")
            return super().claim_document(document_id, row)

    store = InterruptReviewStore()
    preview = build_effective_context_review_preview(
        candidate,
        artifact=artifact,
        owner_account_digest="a" * 64,
        artifact_account_digest="b" * 64,
        artifact_investigation_digest="c" * 64,
        disposition="propose_compensation",
        rationale="Propose after review.",
        proposed_claim="Proposed wording.",
    )
    kwargs = dict(
        owner_account_digest="a" * 64,
        artifact_account_digest="b" * 64,
        artifact_investigation_digest="c" * 64,
        expected_preview_sha256=preview.preview_sha256,
        mutation_key="recoverable-review",
        store=store,
    )
    with pytest.raises(RuntimeError, match="simulated interruption"):
        accept_effective_context_review(preview, **kwargs)
    assert read_effective_context_review(
        candidate.challenge.receipt_sha256, store=store
    ) is None
    review, proposal = accept_effective_context_review(preview, **kwargs)
    assert proposal is not None
    assert proposal.review_receipt_sha256 == review.receipt_sha256
