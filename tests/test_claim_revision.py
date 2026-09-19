import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.research_artifact.authority import ArtifactAuthority
from substrate.research_artifact.claim_reconsideration import (
    build_claim_reconsideration_preview,
    create_claim_reconsideration_proposal,
)
from substrate.research_artifact.claim_review import ClaimReviewProjection
from substrate.research_artifact.claim_revision import (
    ClaimRevisionConflict,
    accept_claim_revision,
    build_claim_revision_preview,
    replay_claim_revision,
)
from substrate.research_artifact.import_notes import parse_body_from_html
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody
from substrate.research_artifact.storage import FilesystemArtifactStore, UnsafeArtifactState

OWNER = "a" * 64


def _review() -> ClaimReviewProjection:
    return ClaimReviewProjection(
        status="later_owner_accepted_counter_analysis",
        challenge_receipt_sha256="1" * 64,
        acceptance_receipt_sha256="2" * 64,
        session_id="session",
        spawn_id="spawn",
        candidate_sha256="3" * 64,
        candidate_text="Counter-analysis.",
        evaluation_event_id="evaluation",
        evidence_receipt_sha256s=("4" * 64,),
    )


def _fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))
    authority = ArtifactAuthority("alice", "revision")
    body = ResearchArtifactBody(
        investigation_id="revision",
        problem_question="What remains warranted?",
        synthesis_event_id="synthesis-original",
        claim_support=[
            {
                "claim": "Original archived terminal claim.",
                "supporting_chunk_ids": ["chunk-original"],
                "supporting_path_indices": [1],
            }
        ],
    )
    review = _review()
    reconsideration_preview = build_claim_reconsideration_preview(
        owner_account_digest=OWNER,
        artifact_account_digest=authority.account_digest,
        artifact_investigation_digest=authority.investigation_digest,
        source_asset_id="revision",
        artifact_content_hash=body.content_hash(),
        claim_index=0,
        claim_id=f"artifact-v2:{body.content_hash()}:0",
        original_claim=body.claim_support[0].claim,
        reviews=(review,),
        acceptance_receipt_sha256s=(review.acceptance_receipt_sha256,),
        proposed_claim="Revised owner claim <script>kept inert</script>.  ",
        rationale="Accepted counter-analysis narrows the warranted conclusion.  ",
    )
    proposal = create_claim_reconsideration_proposal(
        preview=reconsideration_preview,
        expected_preview_sha256=reconsideration_preview["preview_sha256"],
        mutation_key="proposal",
        store=InMemoryEngagementStore(),
    )
    store = FilesystemArtifactStore(tmp_path)
    prior_html = render_html(body)
    store.write(authority, prior_html)
    preview = build_claim_revision_preview(
        authority=authority,
        owner_account_digest=OWNER,
        prior_body=body,
        proposal=proposal,
        reviews=(review,),
        mutation_key="accept-revision",
    )
    return authority, body, proposal, store, prior_html, preview


def test_preview_is_additive_exact_escaped_and_zero_write(tmp_path, monkeypatch):
    authority, body, proposal, store, prior_html, preview = _fixture(
        tmp_path, monkeypatch
    )
    public = preview.public_dict()
    assert public["prior_artifact_content_hash"] == body.content_hash()
    assert public["prospective_artifact_content_hash"] != body.content_hash()
    assert "<script>" not in public["html"]
    assert "&lt;script&gt;" in public["html"]
    prospective = preview.prospective_body
    assert prospective.schema_version == 3
    assert prospective.claim_support == body.claim_support
    assert prospective.synthesis_event_id == body.synthesis_event_id
    revision = prospective.owner_claim_revisions[0]
    assert revision.revised_claim == proposal.proposed_claim
    assert revision.archive_grounded is False
    assert revision.grants_authority is False
    assert store.read(authority) == prior_html
    assert not (authority.account_dir(tmp_path) / "artifact-history").exists()


def test_schema_v2_content_hash_remains_stable_without_new_default_field():
    historical = {
        "schema_version": 2,
        "investigation_id": "historical",
        "problem_question": "q",
        "insights": [],
        "open_questions": [],
        "synthesis_excerpt": None,
        "synthesis_withheld": False,
        "synthesis_event_id": None,
        "source_event_ids": [],
        "source_coverage": None,
        "inherited_reuse": None,
        "claim_support": [],
        "agent_notes": [],
    }
    expected = hashlib.sha256(
        json.dumps(historical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert ResearchArtifactBody.model_validate(historical).content_hash() == expected


def test_accept_preserves_history_publishes_v3_and_replays(tmp_path, monkeypatch):
    authority, body, proposal, store, prior_html, preview = _fixture(
        tmp_path, monkeypatch
    )
    result = accept_claim_revision(
        authority=authority,
        owner_account_digest=OWNER,
        proposal=proposal,
        reviews=(_review(),),
        mutation_key="accept-revision",
        expected_proposal_receipt_sha256=proposal.receipt_sha256,
        expected_preview_sha256=preview.preview_sha256,
        expected_transition_sha256=preview.transition_sha256,
        store=store,
    )
    current_html = store.read(authority)
    current = parse_body_from_html(current_html)
    assert current.content_hash() == result["artifact_content_hash"]
    assert current.claim_support == body.claim_support
    assert store.read_history(
        authority, body_content_hash=body.content_hash()
    ) == prior_html
    assert replay_claim_revision(
        body=current,
        prior_artifact_content_hash=body.content_hash(),
        proposal_receipt_sha256=proposal.receipt_sha256,
        mutation_key="accept-revision",
        claim_index=0,
    ) == result
    with pytest.raises(ClaimRevisionConflict, match="another command"):
        replay_claim_revision(
            body=current,
            prior_artifact_content_hash=body.content_hash(),
            proposal_receipt_sha256=proposal.receipt_sha256,
            mutation_key="changed",
            claim_index=0,
        )


def test_stale_preview_and_concurrent_accept_have_one_winner(tmp_path, monkeypatch):
    authority, _, proposal, store, _, preview = _fixture(tmp_path, monkeypatch)
    reversed_review = _review().model_copy(
        update={
            "status": "later_owner_reversed_counter_analysis",
            "reversal_receipt_sha256": "9" * 64,
        }
    )
    with pytest.raises(ClaimRevisionConflict, match="no longer accepted"):
        accept_claim_revision(
            authority=authority,
            owner_account_digest=OWNER,
            proposal=proposal,
            reviews=(reversed_review,),
            mutation_key="accept-revision",
            expected_proposal_receipt_sha256=proposal.receipt_sha256,
            expected_preview_sha256=preview.preview_sha256,
            expected_transition_sha256=preview.transition_sha256,
            store=store,
        )

    def accept():
        try:
            return accept_claim_revision(
                authority=authority,
                owner_account_digest=OWNER,
                proposal=proposal,
                reviews=(_review(),),
                mutation_key="accept-revision",
                expected_proposal_receipt_sha256=proposal.receipt_sha256,
                expected_preview_sha256=preview.preview_sha256,
                expected_transition_sha256=preview.transition_sha256,
                store=store,
            )["status"]
        except ClaimRevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: accept(), range(2)))
    assert results.count("accepted") == 1
    assert results.count("conflict") == 1


def test_failed_publish_leaves_current_bytes_and_harmless_history(
    tmp_path, monkeypatch
):
    authority, body, proposal, store, prior_html, preview = _fixture(tmp_path, monkeypatch)
    original_write = store.write

    def fail_write(*args, **kwargs):
        raise OSError("simulated publish failure")

    monkeypatch.setattr(store, "write", fail_write)
    with pytest.raises(OSError, match="publish failure"):
        accept_claim_revision(
            authority=authority,
            owner_account_digest=OWNER,
            proposal=proposal,
            reviews=(_review(),),
            mutation_key="accept-revision",
            expected_proposal_receipt_sha256=proposal.receipt_sha256,
            expected_preview_sha256=preview.preview_sha256,
            expected_transition_sha256=preview.transition_sha256,
            store=store,
        )
    monkeypatch.setattr(store, "write", original_write)
    assert store.read(authority) == prior_html
    assert store.read_history(
        authority, body_content_hash=body.content_hash()
    ) == prior_html


def test_history_is_owner_bound_immutable_bounded_and_tamper_evident(
    tmp_path, monkeypatch
):
    authority, body, _, store, prior_html, _ = _fixture(tmp_path, monkeypatch)
    history_path = store.claim_history(
        authority, body_content_hash=body.content_hash(), html=prior_html
    )
    assert store.claim_history(
        authority, body_content_hash=body.content_hash(), html=prior_html
    ).is_file()
    with pytest.raises(UnsafeArtifactState, match="read bound"):
        store.read_history(
            authority, body_content_hash=body.content_hash(), max_bytes=1
        )
    bob = ArtifactAuthority("bob", "revision")
    with pytest.raises(UnsafeArtifactState):
        store.read_history(bob, body_content_hash=body.content_hash())
    history_path.write_text("{}", encoding="utf-8")
    with pytest.raises(UnsafeArtifactState, match="collision"):
        store.claim_history(
            authority, body_content_hash=body.content_hash(), html=prior_html
        )
