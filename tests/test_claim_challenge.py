from __future__ import annotations

import pytest
from pydantic import ValidationError

from substrate.engagement_spine import HighlightSelection, InMemoryEngagementStore
from substrate.floating_session import open_from_highlight_with_references
from substrate.floating_session.store import InMemorySessionStore
from substrate.research_artifact.claim_challenge import (
    ArchivedInheritedSupport,
    build_claim_challenge_receipt,
    build_effective_owner_claim_context_receipt,
    parse_claim_challenge_receipt,
)


def _receipt(*, goal: str = "Find counterevidence"):
    return build_claim_challenge_receipt(
        owner_account_digest="d" * 64,
        source_asset_id="inv-exact",
        artifact_content_hash="a" * 64,
        synthesis_event_id="synth-exact",
        claim_index=2,
        claim_id=f"artifact-v2:{'a' * 64}:2",
        claim="The exact claim.",
        evaluation_event_id="ground-exact",
        scorer_id="groundedness-nli-v1",
        relation="contradicted",
        score=0.08,
        evidence_receipt_sha256s=("b" * 64, "c" * 64),
        model_id="test-model",
        research_tier="deep",
        goal=goal,
    )


def test_challenge_receipt_is_exact_and_tamper_evident():
    receipt = _receipt()
    assert parse_claim_challenge_receipt(receipt.model_dump()) == receipt
    changed = receipt.model_dump()
    changed["score"] = 0.9
    with pytest.raises(ValidationError, match="digest mismatch"):
        parse_claim_challenge_receipt(changed)
    assert _receipt(goal="Different question").receipt_sha256 != receipt.receipt_sha256
    with pytest.raises(ValueError, match="owner mismatch"):
        parse_claim_challenge_receipt(
            receipt.model_dump(), expected_owner_account_digest="e" * 64
        )


def test_challenge_survives_spawn_session_and_replay_without_auto_completion():
    engagement = InMemoryEngagementStore()
    sessions = InMemorySessionStore()
    receipt = _receipt()
    selection = HighlightSelection(
        asset_id="inv-exact",
        selection_text="The exact claim.",
        region_id=f"claim-challenge:{receipt.receipt_sha256}",
        goal_hint="Challenge this exact terminal claim: Find counterevidence",
        claim_challenge=receipt.model_dump(mode="json"),
    )
    first = open_from_highlight_with_references(
        selection, engagement_store=engagement, session_store=sessions
    )
    replay = open_from_highlight_with_references(
        selection, engagement_store=engagement, session_store=sessions
    )
    assert replay.session_id == first.session_id
    assert replay.claim_challenge == receipt.model_dump(mode="json")
    assert replay.status == "reserved"
    spawn = engagement.get_spawn(first.spawn_id)
    assert spawn is not None
    assert spawn["output_text"] is None
    assert spawn["claim_challenge"] == receipt.model_dump(mode="json")


def test_challenge_session_refuses_corrupt_persisted_receipt():
    engagement = InMemoryEngagementStore()
    sessions = InMemorySessionStore()
    receipt = _receipt()
    selection = HighlightSelection(
        asset_id="inv-exact",
        selection_text="The exact claim.",
        region_id=f"claim-challenge:{receipt.receipt_sha256}",
        claim_challenge=receipt.model_dump(mode="json"),
    )
    session = open_from_highlight_with_references(
        selection, engagement_store=engagement, session_store=sessions
    )
    row = sessions.get_session(session.session_id)
    assert row is not None
    row["claim_challenge"]["claim_index"] = 9
    sessions.put_session(row)
    with pytest.raises(ValidationError, match="digest mismatch"):
        open_from_highlight_with_references(
            selection, engagement_store=engagement, session_store=sessions
        )


def test_effective_owner_context_receipt_binds_complete_chain_and_no_authority():
    receipt = build_effective_owner_claim_context_receipt(
        owner_account_digest="d" * 64,
        source_asset_id="inv-exact",
        artifact_investigation_digest="9" * 64,
        artifact_content_hash="a" * 64,
        synthesis_event_id="synth-exact",
        claim_index=2,
        claim_id=f"artifact-v2:{'a' * 64}:2",
        archived_claim="Archived claim.",
        effective_claim="Current owner claim.",
        root_transition_sha256="1" * 64,
        revision_transition_sha256s=("1" * 64, "2" * 64),
        evaluation_event_id="ground-exact",
        scorer_id="groundedness-nli-v1",
        relation="contradicted",
        score=0.08,
        evidence_receipt_sha256s=("b" * 64,),
        archived_inherited_support=(ArchivedInheritedSupport(
            unit_id="unit-prior",
            qualification_state="legacy_unqualified",
            source_investigation_id=None,
            supporting_leaf_investigation_id="leaf-prior",
        ),),
        model_id="test-model",
        research_tier="deep",
        goal="Investigate owner truth separately.",
        question="What changed?",
        mutation_key="select-owner-context",
    )
    assert parse_claim_challenge_receipt(receipt.model_dump()) == receipt
    assert receipt.schema_version == 2
    assert receipt.archived_claim == "Archived claim."
    assert receipt.claim_sha256 != receipt.archived_claim_sha256
    assert receipt.head_transition_sha256 == "2" * 64
    assert receipt.archive_grounded is False
    assert receipt.grants_authority is False
    assert receipt.permits_provider_call is False
    assert receipt.permits_spend is False
    assert receipt.permits_graph_admission is False
    assert receipt.permits_write is False
    assert receipt.permits_benchmark_feedback is False
    assert receipt.permits_publication is False
    assert receipt.archived_inherited_support[0].unit_id == "unit-prior"
    changed = receipt.model_dump()
    changed["revision_transition_sha256s"] = ["1" * 64]
    with pytest.raises(ValidationError, match="revision chain"):
        parse_claim_challenge_receipt(changed)
