from concurrent.futures import ThreadPoolExecutor

import pytest

from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.research_artifact.claim_reconsideration import (
    ClaimReconsiderationConflict,
    build_claim_reconsideration_preview,
    create_claim_reconsideration_proposal,
    project_claim_reconsideration_proposal,
    read_claim_reconsideration_proposal,
)
from substrate.research_artifact.claim_review import ClaimReviewProjection

OWNER = "a" * 64
ACCOUNT = "b" * 64
INVESTIGATION = "c" * 64
CONTENT = "d" * 64


def _review(*, accepted: bool = True, suffix: str = "1") -> ClaimReviewProjection:
    return ClaimReviewProjection(
        status=(
            "later_owner_accepted_counter_analysis"
            if accepted
            else "later_owner_reversed_counter_analysis"
        ),
        challenge_receipt_sha256=suffix * 64,
        acceptance_receipt_sha256=("e" if suffix == "1" else "f") * 64,
        reversal_receipt_sha256=None if accepted else "9" * 64,
        session_id=f"session-{suffix}",
        spawn_id=f"spawn-{suffix}",
        candidate_sha256=("7" if suffix == "1" else "8") * 64,
        candidate_text=f"Counter-analysis {suffix}.",
        evaluation_event_id="evaluation-one",
        evidence_receipt_sha256s=("6" * 64,),
    )


def _preview(reviews=None, receipts=("e" * 64,)):
    if reviews is None:
        reviews = (_review(),)
    return build_claim_reconsideration_preview(
        owner_account_digest=OWNER,
        artifact_account_digest=ACCOUNT,
        artifact_investigation_digest=INVESTIGATION,
        source_asset_id="artifact-one",
        artifact_content_hash=CONTENT,
        claim_index=0,
        claim_id=f"artifact-v2:{CONTENT}:0",
        original_claim="Original terminal claim.",
        reviews=reviews,
        acceptance_receipt_sha256s=receipts,
        proposed_claim="Proposed <script>claim</script>.  ",
        rationale="Owner rationale with exact trailing bytes.  ",
    )


def test_preview_preserves_exact_bytes_escapes_html_and_writes_nothing():
    store = InMemoryEngagementStore()
    preview = _preview()
    assert preview["proposed_claim"] == "Proposed <script>claim</script>.  "
    assert preview["rationale"].endswith("  ")
    assert "<script>" not in preview["html"]
    assert "&lt;script&gt;" in preview["html"]
    assert store._docs == {}
    assert preview == _preview()


def test_create_is_immutable_replayable_and_first_writer_wins():
    store = InMemoryEngagementStore()
    preview = _preview()

    def create(key: str):
        return create_claim_reconsideration_proposal(
            preview=preview,
            expected_preview_sha256=preview["preview_sha256"],
            mutation_key=key,
            store=store,
        )

    proposal = create("proposal-one")
    assert create("proposal-one") == proposal
    assert proposal.grants_authority is False
    with pytest.raises(ClaimReconsiderationConflict, match="another command"):
        create("proposal-two")
    assert read_claim_reconsideration_proposal(
        source_asset_id="artifact-one",
        artifact_content_hash=CONTENT,
        claim_index=0,
        store=store,
    ) == proposal

    concurrent_store = InMemoryEngagementStore()

    def race(key: str):
        try:
            return create_claim_reconsideration_proposal(
                preview=preview,
                expected_preview_sha256=preview["preview_sha256"],
                mutation_key=key,
                store=concurrent_store,
            ).mutation_key_sha256
        except ClaimReconsiderationConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, ("left", "right")))
    assert results.count("conflict") == 1


def test_create_recomputes_preview_hash_instead_of_trusting_caller_dictionary():
    store = InMemoryEngagementStore()
    preview = _preview()
    forged = dict(preview)
    forged["proposed_claim"] = "Forged after preview."
    with pytest.raises(ClaimReconsiderationConflict, match="stale"):
        create_claim_reconsideration_proposal(
            preview=forged,
            expected_preview_sha256=preview["preview_sha256"],
            mutation_key="forged",
            store=store,
        )
    assert store._docs == {}


def test_selection_requires_unique_current_accepted_reviews():
    with pytest.raises(ValueError, match="duplicates"):
        _preview(receipts=("e" * 64, "e" * 64))
    with pytest.raises(ValueError, match="currently accepted"):
        _preview(reviews=(_review(accepted=False),))
    with pytest.raises(ValueError, match="currently accepted"):
        _preview(receipts=("f" * 64,))


def test_projection_revalidates_current_acceptance_and_exact_lineage():
    store = InMemoryEngagementStore()
    preview = _preview()
    proposal = create_claim_reconsideration_proposal(
        preview=preview,
        expected_preview_sha256=preview["preview_sha256"],
        mutation_key="projection",
        store=store,
    )
    kwargs = dict(
        proposal=proposal,
        owner_account_digest=OWNER,
        artifact_account_digest=ACCOUNT,
        artifact_investigation_digest=INVESTIGATION,
        claim_id=f"artifact-v2:{CONTENT}:0",
        original_claim="Original terminal claim.",
        reviews=(_review(),),
    )
    assert project_claim_reconsideration_proposal(**kwargs) == proposal
    assert project_claim_reconsideration_proposal(
        **{**kwargs, "reviews": (_review(accepted=False),)}
    ) is None
    with pytest.raises(RuntimeError, match="lineage"):
        project_claim_reconsideration_proposal(
            **{**kwargs, "original_claim": "Substituted terminal claim."}
        )


def test_strict_read_rejects_outer_kind_and_self_hash_corruption():
    store = InMemoryEngagementStore()
    preview = _preview()
    proposal = create_claim_reconsideration_proposal(
        preview=preview,
        expected_preview_sha256=preview["preview_sha256"],
        mutation_key="corrupt",
        store=store,
    )
    document_id = next(iter(store._docs))
    store._docs[document_id]["kind"] = "other"
    with pytest.raises(RuntimeError, match="corrupt"):
        read_claim_reconsideration_proposal(
            source_asset_id=proposal.source_asset_id,
            artifact_content_hash=proposal.artifact_content_hash,
            claim_index=proposal.claim_index,
            store=store,
        )
