from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from substrate.engagement_spine import InMemoryEngagementStore
from substrate.engagement_spine.authority import EngagementAuthority
from substrate.engagement_spine.spawn import complete_spawn
from substrate.engagement_spine.store import authorized_store
from substrate.floating_session.store import InMemorySessionStore
from substrate.research_artifact.claim_challenge import build_claim_challenge_receipt
from substrate.research_artifact.claim_review import (
    ClaimReviewConflict,
    accept_claim_review,
    build_claim_review_preview,
    project_claim_reviews,
    read_claim_review,
    resolve_claim_review_candidate,
    reverse_claim_review,
    review_document_id,
)

OWNER = "d" * 64


def _challenge():
    return build_claim_challenge_receipt(
        owner_account_digest=OWNER,
        source_asset_id="inv-review",
        artifact_content_hash="a" * 64,
        synthesis_event_id="synth-review",
        claim_index=1,
        claim_id="artifact-v2:review:1",
        claim="A terminal claim.",
        evaluation_event_id="ground-review",
        scorer_id="groundedness-nli-v1",
        relation="contradicted",
        score=0.1,
        evidence_receipt_sha256s=("b" * 64,),
        model_id="review-model",
        research_tier="deep",
        goal="Challenge this claim.",
    )


def _candidate():
    challenge = _challenge().model_dump(mode="json")
    return resolve_claim_review_candidate(
        session_row={
            "session_id": "session-review",
            "spawn_id": "spawn-review",
            "parent_asset_id": "inv-review",
            "status": "complete",
            "claim_challenge": challenge,
        },
        spawn_row={
            "spawn_id": "spawn-review",
            "parent_asset_id": "inv-review",
            "status": "complete",
            "output_text": "Counter-analysis <script>alert(1)</script>",
            "claim_challenge": challenge,
        },
        owner_account_digest=OWNER,
    )


def test_preview_is_deterministic_escaped_and_zero_write():
    store = InMemoryEngagementStore()
    preview = build_claim_review_preview(
        _candidate(),
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
    )
    assert "<script>" not in preview["html"]
    assert "&lt;script&gt;" in preview["html"]
    assert preview == build_claim_review_preview(
        _candidate(),
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
    )
    assert store._docs == {}


def test_candidate_hash_preserves_exact_completed_output_bytes():
    challenge = _challenge().model_dump(mode="json")
    candidate = resolve_claim_review_candidate(
        session_row={
            "session_id": "session-review",
            "spawn_id": "spawn-review",
            "parent_asset_id": "inv-review",
            "status": "complete",
            "claim_challenge": challenge,
        },
        spawn_row={
            "spawn_id": "spawn-review",
            "parent_asset_id": "inv-review",
            "status": "complete",
            "output_text": "\nExact candidate bytes.\n",
            "claim_challenge": challenge,
        },
        owner_account_digest=OWNER,
    )
    assert candidate.candidate_text == "\nExact candidate bytes.\n"


def test_accept_replay_conflict_reverse_and_history_remain_immutable():
    store = InMemoryEngagementStore()
    candidate = _candidate()
    preview = build_claim_review_preview(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
    )
    accepted = accept_claim_review(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
        expected_preview_sha256=preview["preview_sha256"],
        mutation_key="accept-one",
        store=store,
    )
    replay = accept_claim_review(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
        expected_preview_sha256=preview["preview_sha256"],
        mutation_key="accept-one",
        store=store,
    )
    assert replay == accepted
    with pytest.raises(ClaimReviewConflict, match="another command"):
        accept_claim_review(
            candidate,
            artifact_account_digest="e" * 64,
            artifact_investigation_digest="f" * 64,
            expected_preview_sha256=preview["preview_sha256"],
            mutation_key="accept-two",
            store=store,
        )
    reversed_review = reverse_claim_review(
        accepted,
        acceptance_receipt_sha256=accepted.receipt_sha256,
        rationale="New evidence requires another review.",
        mutation_key="reverse-one",
        store=store,
    )
    assert read_claim_review(_challenge().receipt_sha256, store=store) == (
        accepted,
        reversed_review,
    )
    # Acceptance, its immutable spawn-identity fence, and reversal are append-only.
    assert len(store._docs) == 3
    accepted_preview = build_claim_review_preview(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
        review_state="accepted",
    )
    reversed_preview = build_claim_review_preview(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
        review_state="reversed",
    )
    assert len({preview["preview_sha256"], accepted_preview["preview_sha256"], reversed_preview["preview_sha256"]}) == 3
    with pytest.raises(ClaimReviewConflict, match="another command"):
        reverse_claim_review(
            accepted,
            acceptance_receipt_sha256=accepted.receipt_sha256,
            rationale="Different rationale.",
            mutation_key="reverse-two",
            store=store,
        )


def test_candidate_rejects_incomplete_and_foreign_embedded_owner():
    challenge = _challenge().model_dump(mode="json")
    session = {
        "session_id": "session-review",
        "spawn_id": "spawn-review",
        "parent_asset_id": "inv-review",
        "status": "reserved",
        "claim_challenge": challenge,
    }
    spawn = {
        "spawn_id": "spawn-review",
        "parent_asset_id": "inv-review",
        "status": "reserved",
        "output_text": "Candidate",
        "claim_challenge": challenge,
    }
    with pytest.raises(ClaimReviewConflict, match="not complete"):
        resolve_claim_review_candidate(
            session_row=session, spawn_row=spawn, owner_account_digest=OWNER
        )
    with pytest.raises(ValueError, match="owner mismatch"):
        resolve_claim_review_candidate(
            session_row={**session, "status": "complete"},
            spawn_row={**spawn, "status": "complete"},
            owner_account_digest="e" * 64,
        )


def test_authorized_store_refuses_overwrite_of_immutable_review_document():
    base = InMemoryEngagementStore()
    store = authorized_store(base, EngagementAuthority("review-owner"))
    assert store.claim_document(
        "review-one",
        {"kind": "claim_challenge_acceptance", "acceptance": {"receipt": "fixed"}},
    )
    with pytest.raises(ValueError, match="cannot be overwritten"):
        store.put_document("review-one", {"kind": "ordinary", "body": "replacement"})
    assert store.get_document("review-one")["acceptance"] == {"receipt": "fixed"}


def test_review_read_rejects_valid_receipt_misplaced_under_another_challenge():
    store = InMemoryEngagementStore()
    candidate = _candidate()
    preview = build_claim_review_preview(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
    )
    accept_claim_review(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
        expected_preview_sha256=preview["preview_sha256"],
        mutation_key="accept-misplaced",
        store=store,
    )
    original_id = review_document_id(candidate.challenge.receipt_sha256)
    store._docs[review_document_id("f" * 64)] = store._docs.pop(original_id)
    with pytest.raises(RuntimeError, match="lineage is corrupt"):
        read_claim_review("f" * 64, store=store)


def test_concurrent_changed_commands_claim_exactly_one_acceptance():
    store = InMemoryEngagementStore()
    candidate = _candidate()
    preview = build_claim_review_preview(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
    )

    def attempt(key: str):
        try:
            return accept_claim_review(
                candidate,
                artifact_account_digest="e" * 64,
                artifact_investigation_digest="f" * 64,
                expected_preview_sha256=preview["preview_sha256"],
                mutation_key=key,
                store=store,
            )
        except ClaimReviewConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("race-one", "race-two")))
    assert sum(result is not None for result in results) == 1


def test_acceptance_replay_rejects_mismatched_outer_kind():
    store = InMemoryEngagementStore()
    candidate = _candidate()
    preview = build_claim_review_preview(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
    )
    accepted = accept_claim_review(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
        expected_preview_sha256=preview["preview_sha256"],
        mutation_key="accept-envelope",
        store=store,
    )
    row = store._docs[review_document_id(candidate.challenge.receipt_sha256)]
    row["kind"] = "ordinary"
    with pytest.raises(RuntimeError, match="acceptance is corrupt"):
        accept_claim_review(
            candidate,
            artifact_account_digest="e" * 64,
            artifact_investigation_digest="f" * 64,
            expected_preview_sha256=accepted.preview_sha256,
            mutation_key="accept-envelope",
            store=store,
        )


def test_exact_claim_projection_and_reversal_keep_candidate_separate_and_frozen():
    store = InMemoryEngagementStore()
    sessions = InMemorySessionStore()
    challenge = _challenge()
    spawn = {
        "spawn_id": "spawn-review",
        "investigation_id": "child-review",
        "parent_asset_id": "inv-review",
        "goal": "Challenge this claim.",
        "selection_text": "A terminal claim.",
        "status": "complete",
        "output_text": "Counter-analysis <b>later</b>.",
        "claim_challenge": challenge.model_dump(mode="json"),
    }
    session = {
        "session_id": "session-review",
        "spawn_id": "spawn-review",
        "investigation_id": "child-review",
        "parent_asset_id": "inv-review",
        "status": "complete",
        "claim_challenge": challenge.model_dump(mode="json"),
    }
    store.put_spawn(spawn)
    sessions.put_session(session)
    candidate = resolve_claim_review_candidate(
        session_row=session, spawn_row=spawn, owner_account_digest=OWNER
    )
    preview = build_claim_review_preview(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
    )
    accepted = accept_claim_review(
        candidate,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
        expected_preview_sha256=preview["preview_sha256"],
        mutation_key="projection-accept",
        store=store,
    )

    def project():
        return project_claim_reviews(
            source_asset_id="inv-review",
            artifact_content_hash="a" * 64,
            artifact_account_digest="e" * 64,
            artifact_investigation_digest="f" * 64,
            claim_index=1,
            claim_id="artifact-v2:review:1",
            claim_sha256=challenge.claim_sha256,
            evaluation_event_id="ground-review",
            scorer_id="groundedness-nli-v1",
            relation="contradicted",
            score=0.1,
            evidence_receipt_sha256s=("b" * 64,),
            owner_account_digest=OWNER,
            engagement_store=store,
            session_store=sessions,
        )

    first = project()
    assert len(first) == 1
    assert first[0].status == "later_owner_accepted_counter_analysis"
    assert first[0].candidate_text == "Counter-analysis <b>later</b>."
    assert first[0].grants_authority is False
    with pytest.raises(ValueError, match="output is immutable"):
        complete_spawn(
            "spawn-review", store=store, output_text="Silently replaced candidate."
        )
    stripped_spawn = dict(store.get_spawn("spawn-review") or {})
    stripped_spawn.pop("claim_challenge", None)
    store.put_spawn(stripped_spawn)
    with pytest.raises(ValueError, match="output is immutable"):
        complete_spawn(
            "spawn-review", store=store, output_text="Bypass via stripped challenge."
        )
    stripped_spawn["claim_challenge"] = challenge.model_dump(mode="json")
    store.put_spawn(stripped_spawn)
    reversed_review = reverse_claim_review(
        accepted,
        acceptance_receipt_sha256=accepted.receipt_sha256,
        rationale="Retain but reverse this review.",
        mutation_key="projection-reverse",
        store=store,
    )
    second = project()
    assert second[0].status == "later_owner_reversed_counter_analysis"
    assert second[0].reversal_receipt_sha256 == reversed_review.receipt_sha256


def test_projection_ignores_stale_evidence_identity():
    store = InMemoryEngagementStore()
    sessions = InMemorySessionStore()
    challenge = _challenge()
    store.put_spawn(
        {
            "spawn_id": "unrelated-malformed",
            "parent_asset_id": "inv-review",
            "status": "complete",
            "claim_challenge": {
                "source_asset_id": "another-asset",
                "artifact_content_hash": "not-a-digest",
            },
        }
    )
    store.put_spawn(
        {
            "spawn_id": "unrelated-non-object",
            "parent_asset_id": "inv-review",
            "status": "complete",
            "claim_challenge": "invalid unrelated envelope",
        }
    )
    store.put_spawn(
        {
            "spawn_id": "spawn-review",
            "parent_asset_id": "inv-review",
            "status": "complete",
            "output_text": "Counter-analysis.",
            "claim_challenge": challenge.model_dump(mode="json"),
        }
    )
    assert project_claim_reviews(
        source_asset_id="inv-review",
        artifact_content_hash="a" * 64,
        artifact_account_digest="e" * 64,
        artifact_investigation_digest="f" * 64,
        claim_index=1,
        claim_id="artifact-v2:review:1",
        claim_sha256=challenge.claim_sha256,
        evaluation_event_id="ground-review",
        scorer_id="groundedness-nli-v1",
        relation="contradicted",
        score=0.1,
        evidence_receipt_sha256s=("c" * 64,),
        owner_account_digest=OWNER,
        engagement_store=store,
        session_store=sessions,
    ) == ()
