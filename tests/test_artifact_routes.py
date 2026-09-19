"""ANT-AHT — research artifact HTTP routes."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.artifact_routes import (
    _artifact_claim_evaluations,
    artifact_router,
)
from interfaces.research.api.engagement_routes import engagement_router
from interfaces.research.api.workspace_resume_routes import workspace_resume_router
from runtime.db_lock import connect_write
from substrate.engagement_spine.citation_evidence import parse_citation_evidence
from substrate.event_log import trajectory
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight, promote_insight_authorized
from substrate.graph.tenancy import GraphTenancyState, transition_graph_tenancy_state
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.multi_user.auth import UserClaims
from substrate.research_artifact.authority import ArtifactAuthority
from substrate.research_artifact.import_notes import parse_body_from_html
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody
from substrate.research_artifact.storage import FilesystemArtifactStore
from substrate.schemas.events import ActionType


@pytest.fixture
def api_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ra-api-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events, "arts": arts}


def _client():
    return TestClient(create_app(register_wrestling=False))


def test_post_export_artifact(api_env):
    promote_insight(
        text="API export insight.",
        investigation_id="inv-api",
        confidence="moderate",
        source_document_id="doc-1",
    )
    client = _client()
    resp = client.post("/research/inv-api/artifact/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["investigation_id"] == "inv-api"
    assert body["view_url"].endswith("/research/inv-api/artifact/view")
    assert body["content_hash"]
    assert body["size_bytes"] > 0


def test_get_artifact_blocks_empty(api_env):
    client = _client()
    assert client.post("/research/inv-empty/artifact/export").status_code == 200
    resp = client.get("/research/inv-empty/artifact/blocks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["investigation_id"] == "inv-empty"
    assert body["blocks"] == []


def test_get_artifact_blocks_after_insight(api_env):
    promote_insight(
        text="Outline block source.",
        investigation_id="inv-blocks",
        confidence="high",
        source_document_id="doc-2",
    )
    client = _client()
    assert client.post("/research/inv-blocks/artifact/export").status_code == 200
    resp = client.get("/research/inv-blocks/artifact/blocks")
    assert resp.status_code == 200
    blocks = resp.json()["blocks"]
    assert len(blocks) >= 1
    assert blocks[0]["investigation_id"] == "inv-blocks"
    assert blocks[0]["kind"] in ("insight", "question", "synthesis")


def test_claim_support_projection_is_hash_bound_and_private(api_env, monkeypatch):
    authority = ArtifactAuthority("alice", "claims")
    initialize_composite_stream(
        InvestigationAuthority("alice", "claims", root=Path(api_env["events"]))
    )
    body = ResearchArtifactBody(
        investigation_id="claims",
        problem_question="Which support is authoritative?",
        claim_support=[
            {
                "claim": "The attested terminal claim.",
                "supporting_chunk_ids": ["chunk-direct"],
                "supporting_path_indices": [3],
                "inherited_support": [
                    {
                        "unit_id": "unit-prior",
                        "qualification_state": "partial",
                        "source_investigation_id": "prior",
                        "supporting_leaf_investigation_id": "leaf-current",
                    }
                ],
            }
        ],
    )
    html = render_html(body)

    def read_claim_artifact(requested):
        if requested != authority:
            raise FileNotFoundError
        return html, None

    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.read_canonical_artifact",
        read_claim_artifact,
    )
    resolution_calls = []

    def resolve_groups(chunk_ids, *, owner_id, source_asset_id, claim_id):
        resolution_calls.append(claim_id)
        assert chunk_ids == ["chunk-direct"]
        assert owner_id == "alice"
        evidence = parse_citation_evidence(
            {
                "source_kind": "synthesis_claim",
                "source_asset_id": source_asset_id,
                "claim_id": claim_id,
                "chunk_ids": chunk_ids,
                "document_id": "document-direct",
            }
        )
        assert evidence is not None
        return (evidence,)

    monkeypatch.setattr(
        "interfaces.research.api.hosted_document_routes.resolve_citation_evidence_groups",
        resolve_groups,
    )
    client = _multi_owner_client()

    listing = client.get("/research/claims/artifact/claims", headers={"x-test-user": "alice"})
    assert listing.status_code == 200
    assert listing.headers["cache-control"] == "private, no-store"
    envelope = listing.json()
    assert envelope["content_hash"] == body.content_hash()
    assert envelope["claims"] == [
        {
            "claim_index": 0,
            "claim": "The attested terminal claim.",
            "supporting_chunk_ids": ["chunk-direct"],
            "supporting_path_indices": [3],
            "inherited_support": [
                {
                    "unit_id": "unit-prior",
                    "qualification_state": "partial",
                    "source_investigation_id": "prior",
                    "supporting_leaf_investigation_id": "leaf-current",
                }
            ],
            "direct_evidence": [
                {
                    **parse_citation_evidence(
                        {
                            "source_kind": "synthesis_claim",
                            "source_asset_id": "claims",
                            "claim_id": f"artifact-v2:{body.content_hash()}:0",
                            "chunk_ids": ["chunk-direct"],
                            "document_id": "document-direct",
                        }
                    ).to_dict(),
                }
            ],
            "evaluation": None,
            "reviews": [],
            "reconsiderations": [],
            "owner_revision": None,
        }
    ]

    exact = client.get(
        "/research/claims/artifact/claims/0",
        params={"content_hash": body.content_hash()},
        headers={"x-test-user": "alice"},
    )
    assert exact.status_code == 200
    assert exact.headers["cache-control"] == "private, no-store"
    assert exact.json() == envelope["claims"][0]
    assert len(resolution_calls) == 2

    for index, content_hash in [(-1, body.content_hash()), (1, body.content_hash()), (0, "0" * 64)]:
        refused = client.get(
            f"/research/claims/artifact/claims/{index}",
            params={"content_hash": content_hash},
            headers={"x-test-user": "alice"},
        )
        assert refused.status_code == 404
        assert refused.headers["cache-control"] == "private, no-store"
        assert "The attested terminal claim" not in refused.text
    assert len(resolution_calls) == 2

    foreign = client.get("/research/claims/artifact/claims", headers={"x-test-user": "bob"})
    assert foreign.status_code == 404
    assert foreign.headers["cache-control"] == "private, no-store"
    assert "The attested terminal claim" not in foreign.text


def test_claim_support_projection_rejects_unauthenticated_local(api_env):
    client = _client()
    listing = client.get("/research/local-only/artifact/claims")
    assert listing.status_code == 401
    assert listing.headers["cache-control"] == "private, no-store"
    exact = client.get(
        "/research/local-only/artifact/claims/0",
        params={"content_hash": "0" * 64},
    )
    assert exact.status_code == 401
    assert exact.headers["cache-control"] == "private, no-store"


def test_claim_evaluation_requires_exact_parent_claim_and_order(api_env, monkeypatch):
    authority = ArtifactAuthority("alice", "eval")
    body = ResearchArtifactBody(
        investigation_id="eval",
        problem_question="q",
        synthesis_event_id="synth-exact",
        source_event_ids=["other-event"],
        claim_support=[
            {
                "claim": "Exact terminal claim",
                "supporting_chunk_ids": ["chunk-a", "chunk-b"],
            }
        ],
    )
    rows = [
        {
            "event_id": "synth-exact",
            "action_type": ActionType.SYNTHESIZE_DELIVERED.value,
            "payload": {},
        },
        {
            "event_id": "ground-exact",
            "parent_event_id": "synth-exact",
            "action_type": ActionType.GROUNDEDNESS_SCORED.value,
            "payload": {
                "scorer_id": "groundedness-lexical-v1",
                "backend": "lexical",
                "supported_threshold": 0.5,
                "per_claim": [
                    {
                        "claim": "Exact terminal claim",
                        "score": 0.2,
                        "supported": False,
                        "relation": "contradicted",
                        "cited_chunk_ids": ["chunk-a", "chunk-b"],
                    }
                ],
            },
        },
    ]
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.trajectory_authorized",
        lambda _authority: rows,
    )
    evaluation = _artifact_claim_evaluations(authority, body)[0]
    assert evaluation.advisory is True
    assert evaluation.relation == "contradicted"

    rows[1]["payload"]["per_claim"][0]["cited_chunk_ids"] = ["chunk-b", "chunk-a"]
    with pytest.raises(ValueError, match="uniquely match"):
        _artifact_claim_evaluations(authority, body)


def test_claim_challenge_reserves_exact_server_claim_without_dispatch(
    api_env, monkeypatch, tmp_path
):
    from interfaces.research.api.engagement_routes import reset_engagement_stores

    reset_engagement_stores(root=tmp_path / "engagement")
    from tests.research_quote_support import configure_research_quote_authority

    configure_research_quote_authority(monkeypatch, tmp_path)
    authority = ArtifactAuthority("alice", "challenge")
    initialize_composite_stream(
        InvestigationAuthority("alice", "challenge", root=Path(api_env["events"]))
    )
    body = ResearchArtifactBody(
        investigation_id="challenge",
        problem_question="q",
        synthesis_event_id="synth-challenge",
        claim_support=[
            {
                "claim": "The server-authored terminal claim.",
                "supporting_path_indices": [0],
            }
        ],
    )
    html = render_html(body)

    def read_artifact(requested, **_kwargs):
        if requested != authority:
            raise FileNotFoundError
        return html, None

    rows = [
        {
            "event_id": "synth-challenge",
            "action_type": ActionType.SYNTHESIZE_DELIVERED.value,
            "payload": {},
        },
        {
            "event_id": "ground-challenge",
            "parent_event_id": "synth-challenge",
            "action_type": ActionType.GROUNDEDNESS_SCORED.value,
            "payload": {
                "scorer_id": "groundedness-nli-v1",
                "backend": "nli",
                "supported_threshold": 0.5,
                "per_claim": [
                    {
                        "claim": "The server-authored terminal claim.",
                        "score": 0.1,
                        "supported": False,
                        "relation": "contradicted",
                        "cited_chunk_ids": [],
                    }
                ],
            },
        },
    ]
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.read_canonical_artifact",
        read_artifact,
    )
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.trajectory_authorized",
        lambda _authority: rows,
    )
    FilesystemArtifactStore().write(authority, html)
    artifact_before = authority.artifact_path().read_bytes()
    client = _multi_owner_client(include_engagement=True)
    client.app.state.registered_providers = {"provider-test"}
    endpoint = "/research/challenge/artifact/claims/0/challenge"
    payload = {
        "content_hash": body.content_hash(),
        "goal": "Find decisive counterevidence.",
        "view_mode": "floating",
        "research_tier": "deep",
    }
    stale = client.post(endpoint, json={**payload, "content_hash": "0" * 64})
    assert stale.status_code == 404
    assert stale.headers["cache-control"] == "private, no-store"

    first = client.post(endpoint, json=payload)
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "private, no-store"
    result = first.json()
    assert result["selection_text"] == "The server-authored terminal claim."
    assert result["status"] == "reserved"
    assert result["claim_challenge"]["evaluation_event_id"] == "ground-challenge"
    assert result["claim_challenge"]["evidence_receipt_sha256s"] == []
    assert len(result["claim_challenge"]["owner_account_digest"]) == 64

    replay = client.post(endpoint, json=payload)
    assert replay.json()["session_id"] == result["session_id"]
    changed = client.post(endpoint, json={**payload, "goal": "Test another boundary."})
    assert changed.status_code == 200
    assert changed.json()["session_id"] != result["session_id"]
    changed_model = client.post(endpoint, json={**payload, "model_id": "another-model"})
    assert changed_model.status_code == 200
    assert changed_model.json()["session_id"] != result["session_id"]

    substituted = client.post(endpoint, json={**payload, "selection_text": "forged"})
    assert substituted.status_code == 422
    foreign = client.post(endpoint, json=payload, headers={"x-test-user": "bob"})
    assert foreign.status_code == 404
    assert "server-authored" not in foreign.text

    auto_promote = client.post(
        "/engagement/sessions/complete-flywheel",
        json={"session_id": result["session_id"], "output_text": "Candidate finding."},
    )
    assert auto_promote.status_code == 409
    candidate = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": result["session_id"],
            "output_text": "Candidate finding. <script>alert(1)</script>",
            "record_twins": False,
            "include_twin_promote": False,
        },
    )
    assert candidate.status_code == 200, candidate.text
    assert candidate.json()["status"] == "complete"
    assert candidate.json()["context"]["twin_count"] == 0
    assert candidate.json()["claim_challenge_candidate"] is True
    assert "usage_event" not in candidate.json()
    direct_merge = client.post(
        "/engagement/merge",
        json={
            "parent_asset_id": "challenge",
            "spawn_ids": [result["spawn_id"]],
            "mode": "draft_combined",
        },
    )
    assert direct_merge.status_code == 409
    auto_seed = client.post(
        "/engagement/progress/seed",
        json={"spawn_id": result["spawn_id"]},
    )
    assert auto_seed.status_code == 409

    review_base = f"/research/challenge/artifact/claim-challenges/{result['session_id']}/review"
    preview = client.post(f"{review_base}/preview", json={"content_hash": body.content_hash()})
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "candidate"
    assert preview.json()["preview"]["candidate_text"] == (
        "Candidate finding. <script>alert(1)</script>"
    )
    assert "Candidate finding." in preview.json()["preview"]["html"]
    accepted = client.post(
        f"{review_base}/accept",
        json={
            "content_hash": body.content_hash(),
            "preview_sha256": preview.json()["preview"]["preview_sha256"],
            "mutation_key": "accept-review-one",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    acceptance_receipt = accepted.json()["acceptance"]["receipt_sha256"]
    rewrite_accepted = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": result["session_id"],
            "output_text": "A silently substituted candidate.",
            "record_twins": False,
            "include_twin_promote": False,
        },
    )
    assert rewrite_accepted.status_code == 400
    assert "immutable" in rewrite_accepted.json()["detail"]
    exact_with_review = client.get(
        "/research/challenge/artifact/claims/0",
        params={"content_hash": body.content_hash()},
    )
    assert exact_with_review.status_code == 200, exact_with_review.text
    assert exact_with_review.json()["reviews"][0]["status"] == (
        "later_owner_accepted_counter_analysis"
    )
    assert exact_with_review.json()["reviews"][0]["grants_authority"] is False
    reconsideration_payload = {
        "content_hash": body.content_hash(),
        "acceptance_receipt_sha256s": [acceptance_receipt],
        "proposed_claim": "A reconsidered <script>terminal</script> claim.  ",
        "rationale": "The accepted counter-analysis changes the warranted scope.  ",
    }
    reconsideration_preview = client.post(
        "/research/challenge/artifact/claims/0/reconsideration/preview",
        json=reconsideration_payload,
    )
    assert reconsideration_preview.status_code == 200, reconsideration_preview.text
    assert reconsideration_preview.json()["status"] == "candidate"
    assert "<script>" not in reconsideration_preview.json()["preview"]["html"]
    reconsideration_created = client.post(
        "/research/challenge/artifact/claims/0/reconsideration/create",
        json={
            **reconsideration_payload,
            "preview_sha256": reconsideration_preview.json()["preview"]["preview_sha256"],
            "mutation_key": "create-reconsideration-one",
        },
    )
    assert reconsideration_created.status_code == 200, reconsideration_created.text
    assert reconsideration_created.json()["proposal"]["grants_authority"] is False
    proposal_receipt = reconsideration_created.json()["proposal"]["receipt_sha256"]
    reconsideration_replay = client.post(
        "/research/challenge/artifact/claims/0/reconsideration/create",
        json={
            **reconsideration_payload,
            "preview_sha256": reconsideration_preview.json()["preview"]["preview_sha256"],
            "mutation_key": "create-reconsideration-one",
        },
    )
    assert reconsideration_replay.json()["proposal"]["receipt_sha256"] == proposal_receipt
    reconsideration_changed = client.post(
        "/research/challenge/artifact/claims/0/reconsideration/create",
        json={
            **reconsideration_payload,
            "rationale": "A changed competing command.",
            "preview_sha256": reconsideration_preview.json()["preview"]["preview_sha256"],
            "mutation_key": "create-reconsideration-two",
        },
    )
    assert reconsideration_changed.status_code == 409
    foreign_reconsideration = client.post(
        "/research/challenge/artifact/claims/0/reconsideration/preview",
        headers={"x-test-user": "bob"},
        json=reconsideration_payload,
    )
    assert foreign_reconsideration.status_code == 404
    assert "reconsidered" not in foreign_reconsideration.text
    projected_proposal = client.get(
        "/research/challenge/artifact/claims/0",
        params={"content_hash": body.content_hash()},
    )
    assert projected_proposal.status_code == 200, projected_proposal.text
    assert projected_proposal.json()["reconsiderations"][0]["status"] == (
        "owner_authored_reconsideration_proposal"
    )
    assert projected_proposal.json()["reconsiderations"][0]["proposed_claim"].endswith("  ")
    reviewed_html = client.get(
        "/research/challenge/artifact/reviewed-view",
        params={"content_hash": body.content_hash()},
    )
    assert reviewed_html.status_code == 200, reviewed_html.text
    assert reviewed_html.headers["x-antiek-canonical-content-hash"] == body.content_hash()
    assert reviewed_html.headers["x-antiek-review-overlay"] == "separate-later-analysis"
    assert "Later owner reviews" in reviewed_html.text
    assert "Candidate finding." in reviewed_html.text
    assert "<script>alert(1)</script>" not in reviewed_html.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in reviewed_html.text
    assert reviewed_html.text.index("claim-review-0") < reviewed_html.text.index("Direct chunks:")
    stale_reviewed_html = client.get(
        "/research/challenge/artifact/reviewed-view",
        params={"content_hash": "0" * 64},
    )
    assert stale_reviewed_html.status_code == 404
    replay_accept = client.post(
        f"{review_base}/accept",
        json={
            "content_hash": body.content_hash(),
            "preview_sha256": preview.json()["preview"]["preview_sha256"],
            "mutation_key": "accept-review-one",
        },
    )
    assert replay_accept.json()["acceptance"]["receipt_sha256"] == acceptance_receipt
    changed_accept = client.post(
        f"{review_base}/accept",
        json={
            "content_hash": body.content_hash(),
            "preview_sha256": preview.json()["preview"]["preview_sha256"],
            "mutation_key": "accept-review-two",
        },
    )
    assert changed_accept.status_code == 409
    revision_command = {
        "content_hash": body.content_hash(),
        "proposal_receipt_sha256": proposal_receipt,
        "mutation_key": "accept-owner-revision-one",
    }
    revision_preview = client.post(
        "/research/challenge/artifact/claims/0/revision/preview",
        json=revision_command,
    )
    assert revision_preview.status_code == 200, revision_preview.text
    assert revision_preview.json()["status"] == "candidate"
    assert "<script>" not in revision_preview.json()["preview"]["html"]
    revision_accept = client.post(
        "/research/challenge/artifact/claims/0/revision/accept",
        json={
            **revision_command,
            "preview_sha256": revision_preview.json()["preview"]["preview_sha256"],
            "transition_sha256": revision_preview.json()["preview"]["transition_sha256"],
        },
    )
    assert revision_accept.status_code == 200, revision_accept.text
    assert revision_accept.json()["acceptance"]["archive_grounded"] is False
    assert revision_accept.json()["acceptance"]["grants_authority"] is False
    revision_replay = client.post(
        "/research/challenge/artifact/claims/0/revision/accept",
        json={
            **revision_command,
            "preview_sha256": revision_preview.json()["preview"]["preview_sha256"],
            "transition_sha256": revision_preview.json()["preview"]["transition_sha256"],
        },
    )
    assert revision_replay.json()["acceptance"] == revision_accept.json()["acceptance"]
    root_revision_html = FilesystemArtifactStore().read(authority)
    compensation_command = {
        "content_hash": revision_accept.json()["acceptance"]["artifact_content_hash"],
        "supersedes_transition_sha256": revision_accept.json()["acceptance"]["transition_sha256"],
        "operation": "restore_archived_terminal",
        "replacement_claim": None,
        "rationale": "Restore archived wording while retaining accepted history.",
        "mutation_key": "restore-owner-revision-one",
    }
    compensation_preview = client.post(
        "/research/challenge/artifact/claims/0/revision/compensation/preview",
        json=compensation_command,
    )
    assert compensation_preview.status_code == 200, compensation_preview.text
    assert compensation_preview.json()["preview"]["replacement_claim"] == (
        body.claim_support[0].claim
    )
    compensation_accept = client.post(
        "/research/challenge/artifact/claims/0/revision/compensation/accept",
        json={
            **compensation_command,
            "preview_sha256": compensation_preview.json()["preview"]["preview_sha256"],
            "transition_sha256": compensation_preview.json()["preview"]["transition_sha256"],
        },
    )
    assert compensation_accept.status_code == 200, compensation_accept.text
    assert compensation_accept.json()["acceptance"]["effective_owner_claim"] == (
        body.claim_support[0].claim
    )
    compensation_replay = client.post(
        "/research/challenge/artifact/claims/0/revision/compensation/accept",
        json={
            **compensation_command,
            "preview_sha256": compensation_preview.json()["preview"]["preview_sha256"],
            "transition_sha256": compensation_preview.json()["preview"]["transition_sha256"],
        },
    )
    assert compensation_replay.json()["acceptance"] == compensation_accept.json()["acceptance"]
    context_command = {
        "content_hash": compensation_accept.json()["acceptance"]["artifact_content_hash"],
        "goal": "Test the current owner wording against fresh evidence.",
        "mutation_key": "owner-context-one",
        "view_mode": "floating",
        "research_tier": "deep",
    }
    context_preview = client.post(
        "/research/challenge/artifact/claims/0/owner-context/preview",
        json=context_command,
    )
    assert context_preview.status_code == 200, context_preview.text
    preview_payload = context_preview.json()["preview"]
    assert preview_payload["archived_claim"] == body.claim_support[0].claim
    assert preview_payload["effective_claim"] == body.claim_support[0].claim
    assert preview_payload["revision_transition_sha256s"] == [
        revision_accept.json()["acceptance"]["transition_sha256"],
        compensation_accept.json()["acceptance"]["transition_sha256"],
    ]
    assert preview_payload["permits_provider_call"] is False
    context_accept = client.post(
        "/research/challenge/artifact/claims/0/owner-context/accept",
        json={
            **context_command,
            "preview_sha256": preview_payload["preview_sha256"],
            "receipt_sha256": preview_payload["receipt_sha256"],
        },
    )
    assert context_accept.status_code == 200, context_accept.text
    context_reservation = context_accept.json()["reservation"]
    assert context_reservation["selection_text"] == body.claim_support[0].claim
    assert context_reservation["status"] == "reserved"
    assert context_reservation["claim_challenge"]["schema_version"] == 2
    assert context_reservation["claim_challenge"]["selection_kind"] == ("effective_owner_claim")
    assert context_reservation["claim_challenge"]["archive_grounded"] is False
    context_candidate = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": context_reservation["session_id"],
            "output_text": "Fresh analysis of current owner wording.",
            "record_twins": False,
            "include_twin_promote": False,
        },
    )
    assert context_candidate.status_code == 200, context_candidate.text
    legacy_context_review = client.post(
        f"/research/challenge/artifact/claim-challenges/{context_reservation['session_id']}/review/preview",
        json={"content_hash": context_command["content_hash"]},
    )
    assert legacy_context_review.status_code in (404, 409)
    context_review_base = (
        f"/research/challenge/artifact/owner-contexts/{context_reservation['session_id']}/review"
    )
    context_review_command = {
        "content_hash": context_command["content_hash"],
        "disposition": "propose_compensation",
        "rationale": "The candidate supports a narrower owner wording.",
        "proposed_claim": "A narrower owner-authored wording.",
    }
    context_review_preview = client.post(
        f"{context_review_base}/preview", json=context_review_command
    )
    assert context_review_preview.status_code == 200, context_review_preview.text
    review_preview = context_review_preview.json()["preview"]
    assert review_preview["archived_claim"] == body.claim_support[0].claim
    assert review_preview["candidate_text"] == ("Fresh analysis of current owner wording.")
    assert review_preview["permits_canonical_append"] is False
    context_review_accept = client.post(
        f"{context_review_base}/accept",
        json={
            **context_review_command,
            "preview_sha256": review_preview["preview_sha256"],
            "mutation_key": "effective-context-review-one",
        },
    )
    assert context_review_accept.status_code == 200, context_review_accept.text
    assert context_review_accept.json()["acceptance"]["permits_canonical_append"] is False
    assert context_review_accept.json()["proposal"]["proposed_claim"] == (
        "A narrower owner-authored wording."
    )
    accepted_context_preview = client.post(
        f"{context_review_base}/preview", json=context_review_command
    )
    assert accepted_context_preview.status_code == 200
    assert accepted_context_preview.json()["status"] == "accepted"
    assert (
        accepted_context_preview.json()["preview"]["preview_sha256"]
        == (review_preview["preview_sha256"])
    )
    rewrite_context_candidate = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": context_reservation["session_id"],
            "output_text": "Silently changed context candidate.",
            "record_twins": False,
            "include_twin_promote": False,
        },
    )
    assert rewrite_context_candidate.status_code == 400
    assert "immutable" in rewrite_context_candidate.json()["detail"]
    context_review_read = client.get(context_review_base)
    assert context_review_read.status_code == 200, context_review_read.text
    assert context_review_read.headers["cache-control"] == "private, no-store"
    assert context_review_read.json()["proposal"]["permits_canonical_append"] is False
    changed_context_review = client.post(
        f"{context_review_base}/preview",
        json={
            **context_review_command,
            "rationale": "A conflicting later rationale.",
        },
    )
    assert changed_context_review.status_code == 409
    foreign_context_review = client.get(context_review_base, headers={"x-test-user": "bob"})
    assert foreign_context_review.status_code == 404
    assert "Fresh analysis" not in foreign_context_review.text
    context_replay = client.post(
        "/research/challenge/artifact/claims/0/owner-context/accept",
        json={
            **context_command,
            "preview_sha256": preview_payload["preview_sha256"],
            "receipt_sha256": preview_payload["receipt_sha256"],
        },
    )
    assert context_replay.json()["reservation"]["session_id"] == (context_reservation["session_id"])
    changed_context_preview = client.post(
        "/research/challenge/artifact/claims/0/owner-context/preview",
        json={**context_command, "goal": "A changed question under the same intent."},
    )
    assert changed_context_preview.status_code == 200
    changed_context = client.post(
        "/research/challenge/artifact/claims/0/owner-context/accept",
        json={
            **context_command,
            "goal": "A changed question under the same intent.",
            "preview_sha256": changed_context_preview.json()["preview"]["preview_sha256"],
            "receipt_sha256": changed_context_preview.json()["preview"]["receipt_sha256"],
        },
    )
    assert changed_context.status_code == 409
    proposal_receipt = context_review_accept.json()["proposal"]["receipt_sha256"]
    proposal_compensation_command = {
        "content_hash": context_command["content_hash"],
        "proposal_receipt_sha256": proposal_receipt,
        "mutation_key": "consume-effective-context-proposal-one",
    }
    proposal_compensation_preview = client.post(
        f"{context_review_base}/compensation/preview",
        json=proposal_compensation_command,
    )
    assert proposal_compensation_preview.status_code == 200, proposal_compensation_preview.text
    proposal_preview = proposal_compensation_preview.json()["preview"]
    assert proposal_preview["replacement_claim"] == ("A narrower owner-authored wording.")
    assert proposal_preview["source_proposal_receipt_sha256"] == proposal_receipt
    proposal_compensation_accept = client.post(
        f"{context_review_base}/compensation/accept",
        json={
            **proposal_compensation_command,
            "preview_sha256": proposal_preview["preview_sha256"],
            "transition_sha256": proposal_preview["transition_sha256"],
        },
    )
    assert proposal_compensation_accept.status_code == 200, proposal_compensation_accept.text
    proposal_acceptance = proposal_compensation_accept.json()["acceptance"]
    assert proposal_acceptance["source_proposal_receipt_sha256"] == proposal_receipt
    assert proposal_acceptance["effective_owner_claim"] == ("A narrower owner-authored wording.")
    proposal_compensation_replay = client.post(
        f"{context_review_base}/compensation/accept",
        json={
            **proposal_compensation_command,
            "preview_sha256": proposal_preview["preview_sha256"],
            "transition_sha256": proposal_preview["transition_sha256"],
        },
    )
    assert proposal_compensation_replay.json()["acceptance"] == proposal_acceptance
    consumed_review = client.get(context_review_base)
    assert consumed_review.status_code == 200, consumed_review.text
    assert consumed_review.json()["effective_claim"] == ("A narrower owner-authored wording.")
    assert consumed_review.json()["consumption"] == proposal_acceptance
    changed_proposal_consumption = client.post(
        f"{context_review_base}/compensation/accept",
        json={
            **proposal_compensation_command,
            "mutation_key": "changed-proposal-consumption",
            "preview_sha256": proposal_preview["preview_sha256"],
            "transition_sha256": proposal_preview["transition_sha256"],
        },
    )
    assert changed_proposal_consumption.status_code == 409
    consumed_body = parse_body_from_html(FilesystemArtifactStore().read(authority))
    consumed = consumed_body.owner_claim_compensations[-1]
    assert consumed.schema_version == 2
    assert consumed.source_proposal_receipt_sha256 == proposal_receipt
    assert consumed_body.claim_support == body.claim_support
    consumed_html = FilesystemArtifactStore().read(authority)
    assert "Consumed reviewed proposal receipt" in consumed_html
    assert proposal_receipt in consumed_html
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.read_canonical_artifact",
        lambda requested, **_kwargs: (
            FilesystemArtifactStore().read(requested),
            None,
        ),
    )
    consumed_claim = client.get(
        "/research/challenge/artifact/claims/0",
        params={"content_hash": consumed_body.content_hash()},
    )
    assert consumed_claim.status_code == 200, consumed_claim.text
    assert (
        consumed_claim.json()["owner_revision"]["compensations"][-1][
            "source_proposal_receipt_sha256"
        ]
        == proposal_receipt
    )
    iterations = client.get("/research/challenge/artifact/claims/0/owner-iterations")
    assert iterations.status_code == 200, iterations.text
    assert iterations.headers["cache-control"] == "private, no-store"
    iteration_payload = iterations.json()
    assert iteration_payload["current_effective_claim"] == ("A narrower owner-authored wording.")
    assert iteration_payload["next_round_eligible"] is True
    assert len(iteration_payload["rounds"]) == 1
    assert iteration_payload["rounds"][0]["candidate_text"] == (
        "Fresh analysis of current owner wording."
    )
    assert iteration_payload["rounds"][0]["proposal_receipt_sha256"] == (proposal_receipt)
    assert iteration_payload["rounds"][0]["result_is_current"] is True
    first_result_url = iteration_payload["rounds"][0]["result_html_url"]
    first_result_html = client.get(first_result_url)
    assert first_result_html.status_code == 200, first_result_html.text
    assert first_result_html.headers["cache-control"] == "private, no-store"
    assert (
        first_result_html.headers["x-antiek-iteration-result-content-hash"]
        == (iteration_payload["rounds"][0]["result_artifact_content_hash"])
    )
    assert client.get(first_result_url, headers={"x-test-user": "bob"}).status_code == 404
    assert (
        client.get("/research/challenge/artifact/iteration-results/not-a-hash").status_code == 404
    )
    iteration_detail = client.get("/research/challenge/artifact/claims/0/owner-iterations/1")
    assert iteration_detail.status_code == 200, iteration_detail.text
    assert iteration_detail.headers["cache-control"] == "private, no-store"
    assert iteration_detail.json() == iteration_payload["rounds"][0]
    assert client.get("/research/challenge/artifact/claims/0/owner-iterations/2").status_code == 404

    # A second complete research round must reconstruct the first result as
    # history, then remain replayable after an unrelated manual compensation.
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.read_canonical_artifact",
        read_artifact,
    )
    second_context_command = {
        "content_hash": consumed_body.content_hash(),
        "goal": "Re-test the narrowed owner wording against contrary evidence.",
        "mutation_key": "owner-context-two",
        "view_mode": "floating",
        "research_tier": "deep",
    }
    second_context_preview = client.post(
        "/research/challenge/artifact/claims/0/owner-context/preview",
        json=second_context_command,
    )
    assert second_context_preview.status_code == 200, second_context_preview.text
    second_preview = second_context_preview.json()["preview"]
    assert second_preview["effective_claim"] == "A narrower owner-authored wording."
    second_context_accept = client.post(
        "/research/challenge/artifact/claims/0/owner-context/accept",
        json={
            **second_context_command,
            "preview_sha256": second_preview["preview_sha256"],
            "receipt_sha256": second_preview["receipt_sha256"],
        },
    )
    assert second_context_accept.status_code == 200, second_context_accept.text
    second_reservation = second_context_accept.json()["reservation"]
    second_candidate = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": second_reservation["session_id"],
            "output_text": "Second-round analysis identifies a residual uncertainty.",
            "record_twins": False,
            "include_twin_promote": False,
        },
    )
    assert second_candidate.status_code == 200, second_candidate.text
    second_review_base = (
        f"/research/challenge/artifact/owner-contexts/{second_reservation['session_id']}/review"
    )
    second_review_command = {
        "content_hash": second_context_command["content_hash"],
        "disposition": "propose_compensation",
        "rationale": "The residual uncertainty warrants a qualified wording.",
        "proposed_claim": "A qualified owner-authored wording.",
    }
    second_review_preview = client.post(f"{second_review_base}/preview", json=second_review_command)
    assert second_review_preview.status_code == 200, second_review_preview.text
    second_review_accept = client.post(
        f"{second_review_base}/accept",
        json={
            **second_review_command,
            "preview_sha256": second_review_preview.json()["preview"]["preview_sha256"],
            "mutation_key": "effective-context-review-two",
        },
    )
    assert second_review_accept.status_code == 200, second_review_accept.text
    second_proposal_receipt = second_review_accept.json()["proposal"]["receipt_sha256"]
    second_consumption_command = {
        "content_hash": second_context_command["content_hash"],
        "proposal_receipt_sha256": second_proposal_receipt,
        "mutation_key": "consume-effective-context-proposal-two",
    }
    second_consumption_preview = client.post(
        f"{second_review_base}/compensation/preview",
        json=second_consumption_command,
    )
    assert second_consumption_preview.status_code == 200, second_consumption_preview.text
    second_transition_preview = second_consumption_preview.json()["preview"]
    second_consumption_accept = client.post(
        f"{second_review_base}/compensation/accept",
        json={
            **second_consumption_command,
            "preview_sha256": second_transition_preview["preview_sha256"],
            "transition_sha256": second_transition_preview["transition_sha256"],
        },
    )
    assert second_consumption_accept.status_code == 200, second_consumption_accept.text
    second_acceptance = second_consumption_accept.json()["acceptance"]
    two_rounds = client.get("/research/challenge/artifact/claims/0/owner-iterations")
    assert two_rounds.status_code == 200, two_rounds.text
    two_round_payload = two_rounds.json()
    assert [row["ordinal"] for row in two_round_payload["rounds"]] == [1, 2]
    assert [row["prior_effective_claim"] for row in two_round_payload["rounds"]] == [
        body.claim_support[0].claim,
        "A narrower owner-authored wording.",
    ]
    assert two_round_payload["rounds"][0]["result_is_current"] is False
    assert "/artifact/iteration-results/" in (two_round_payload["rounds"][0]["result_html_url"])
    assert two_round_payload["rounds"][1]["result_is_current"] is True
    assert two_round_payload["rounds"][1]["candidate_text"] == (
        "Second-round analysis identifies a residual uncertainty."
    )

    recursive_command = {
        "content_hash": second_acceptance["artifact_content_hash"],
        "selected_round_ordinals": [1, 2],
        "follow_up_questions": [
            "Which uncertainty survives both completed rounds?",
            "What evidence would distinguish the competing explanations?",
        ],
        "mutation_key": "recursive-context-after-two-rounds",
        "view_mode": "floating",
        "research_tier": "deep",
    }
    recursive_preview_response = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/preview",
        json=recursive_command,
    )
    assert recursive_preview_response.status_code == 200, recursive_preview_response.text
    recursive_preview = recursive_preview_response.json()["preview"]
    assert recursive_preview["selected_round_ordinals"] == [1, 2]
    assert recursive_preview["selected_transition_sha256s"] == [
        row["transition_sha256"] for row in two_round_payload["rounds"]
    ]
    assert recursive_preview["pack_bytes"] > 0
    assert recursive_preview["permits_provider_call"] is False
    assert recursive_preview["permits_spend"] is False
    zero_round_preview = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/preview",
        json={
            **recursive_command,
            "selected_round_ordinals": [],
            "follow_up_questions": ["What remains uncertain now?"],
            "mutation_key": "recursive-context-zero-rounds",
        },
    )
    assert zero_round_preview.status_code == 200, zero_round_preview.text
    assert zero_round_preview.json()["preview"]["rows"] == []
    for invalid_ordinals in ([2, 1], [1, 1], [3]):
        invalid_recursive = client.post(
            "/research/challenge/artifact/claims/0/recursive-context/preview",
            json={**recursive_command, "selected_round_ordinals": invalid_ordinals},
        )
        assert invalid_recursive.status_code == 409
    recursive_accept = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/accept",
        json={
            **recursive_command,
            "preview_sha256": recursive_preview["preview_sha256"],
            "receipt_sha256": recursive_preview["receipt_sha256"],
        },
    )
    assert recursive_accept.status_code == 200, recursive_accept.text
    recursive_reservation = recursive_accept.json()["reservation"]
    recursive_receipt = recursive_reservation["claim_challenge"]
    assert recursive_receipt["schema_version"] == 3
    assert recursive_receipt["recursive_context_pack"]["selected_ordinals"] == [1, 2]
    assert (
        recursive_receipt["recursive_context_pack"]["pack_sha256"]
        == (recursive_preview["pack_sha256"])
    )
    from interfaces.research.api.engagement_routes import _sess
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.floating_session.store import authorized_session_store

    recursive_session_store = authorized_session_store(_sess(), EngagementAuthority("alice"))
    persisted_recursive_session = recursive_session_store.get_session(
        recursive_reservation["session_id"]
    )
    assert persisted_recursive_session is not None
    assert (
        recursive_receipt["recursive_context_pack"]["receipt_sha256"]
        in (persisted_recursive_session["goal"])
    )
    assert (
        "Second-round analysis identifies a residual uncertainty."
        in (persisted_recursive_session["goal"])
    )
    corrupt_recursive_session = json.loads(json.dumps(persisted_recursive_session))
    corrupt_recursive_session["research_tier"] = None
    recursive_session_store.put_session(corrupt_recursive_session)
    corrupt_recursive_replay = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/accept",
        json={
            **recursive_command,
            "preview_sha256": recursive_preview["preview_sha256"],
            "receipt_sha256": recursive_preview["receipt_sha256"],
        },
    )
    assert corrupt_recursive_replay.status_code == 409
    recursive_session_store.put_session(persisted_recursive_session)
    from substrate.research_artifact.claim_challenge import ClaimChallengeReceipt

    tampered_recursive_receipt = json.loads(json.dumps(recursive_receipt))
    tampered_recursive_receipt["recursive_context_pack"]["rows"][0]["candidate_text"] = (
        "substituted prior reasoning"
    )
    with pytest.raises(ValueError):
        ClaimChallengeReceipt.model_validate(tampered_recursive_receipt)
    recursive_replay = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/accept",
        json={
            **recursive_command,
            "preview_sha256": recursive_preview["preview_sha256"],
            "receipt_sha256": recursive_preview["receipt_sha256"],
        },
    )
    assert recursive_replay.status_code == 200, recursive_replay.text
    assert (
        recursive_replay.json()["reservation"]["session_id"]
        == (recursive_reservation["session_id"])
    )
    changed_recursive_preview = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/preview",
        json={
            **recursive_command,
            "follow_up_questions": ["A changed question under the same intent key?"],
        },
    )
    assert changed_recursive_preview.status_code == 200
    changed_recursive_accept = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/accept",
        json={
            **recursive_command,
            "follow_up_questions": ["A changed question under the same intent key?"],
            "preview_sha256": changed_recursive_preview.json()["preview"]["preview_sha256"],
            "receipt_sha256": changed_recursive_preview.json()["preview"]["receipt_sha256"],
        },
    )
    assert changed_recursive_accept.status_code == 409
    changed_mode_preview = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/preview",
        json={**recursive_command, "view_mode": "full"},
    )
    assert changed_mode_preview.status_code == 200, changed_mode_preview.text
    changed_mode_accept = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/accept",
        json={
            **recursive_command,
            "view_mode": "full",
            "preview_sha256": changed_mode_preview.json()["preview"]["preview_sha256"],
            "receipt_sha256": changed_mode_preview.json()["preview"]["receipt_sha256"],
        },
    )
    assert changed_mode_accept.status_code == 409
    foreign_recursive = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/preview",
        headers={"x-test-user": "bob"},
        json=recursive_command,
    )
    assert foreign_recursive.status_code == 404
    assert "uncertainty" not in foreign_recursive.text
    recursive_candidate = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": recursive_reservation["session_id"],
            "output_text": "Recursive analysis grounded in both selected reasoning rounds.",
            "record_twins": False,
            "include_twin_promote": False,
        },
    )
    assert recursive_candidate.status_code == 200, recursive_candidate.text
    recursive_review_preview = client.post(
        f"/research/challenge/artifact/owner-contexts/{recursive_reservation['session_id']}"
        "/review/preview",
        json={
            "content_hash": second_acceptance["artifact_content_hash"],
            "disposition": "propose_compensation",
            "rationale": "The combined ancestry warrants a recursively qualified wording.",
            "proposed_claim": "A recursively qualified owner-authored wording.",
        },
    )
    assert recursive_review_preview.status_code == 200, recursive_review_preview.text
    recursive_review_command = {
        "content_hash": second_acceptance["artifact_content_hash"],
        "disposition": "propose_compensation",
        "rationale": "The combined ancestry warrants a recursively qualified wording.",
        "proposed_claim": "A recursively qualified owner-authored wording.",
    }
    recursive_review_accept = client.post(
        f"/research/challenge/artifact/owner-contexts/{recursive_reservation['session_id']}"
        "/review/accept",
        json={
            **recursive_review_command,
            "preview_sha256": recursive_review_preview.json()["preview"]["preview_sha256"],
            "mutation_key": "recursive-context-review-three",
        },
    )
    assert recursive_review_accept.status_code == 200, recursive_review_accept.text
    recursive_proposal = recursive_review_accept.json()["proposal"]
    recursive_consumption_command = {
        "content_hash": second_acceptance["artifact_content_hash"],
        "proposal_receipt_sha256": recursive_proposal["receipt_sha256"],
        "mutation_key": "consume-recursive-context-proposal-three",
    }
    recursive_consumption_preview = client.post(
        f"/research/challenge/artifact/owner-contexts/{recursive_reservation['session_id']}"
        "/review/compensation/preview",
        json=recursive_consumption_command,
    )
    assert recursive_consumption_preview.status_code == 200, recursive_consumption_preview.text
    recursive_transition_preview = recursive_consumption_preview.json()["preview"]
    recursive_consumption_accept = client.post(
        f"/research/challenge/artifact/owner-contexts/{recursive_reservation['session_id']}"
        "/review/compensation/accept",
        json={
            **recursive_consumption_command,
            "preview_sha256": recursive_transition_preview["preview_sha256"],
            "transition_sha256": recursive_transition_preview["transition_sha256"],
        },
    )
    assert recursive_consumption_accept.status_code == 200, recursive_consumption_accept.text
    third_acceptance = recursive_consumption_accept.json()["acceptance"]
    ancestry = client.get("/research/challenge/artifact/claims/0/owner-ancestry")
    assert ancestry.status_code == 200, ancestry.text
    assert ancestry.headers["cache-control"] == "private, no-store"
    ancestry_payload = ancestry.json()
    assert [node["ordinal"] for node in ancestry_payload["nodes"]] == [1, 2, 3]
    assert ancestry_payload["nodes"][0]["child_ordinals"] == [3]
    assert ancestry_payload["nodes"][1]["child_ordinals"] == [3]
    assert ancestry_payload["nodes"][2]["parent_ordinals"] == [1, 2]
    assert ancestry_payload["nodes"][2]["depth"] == 1
    assert ancestry_payload["nodes"][2]["is_recombination"] is True
    assert (
        ancestry_payload["nodes"][2]["inherited_questions"]
        == (recursive_command["follow_up_questions"])
    )
    ancestry_detail = client.get("/research/challenge/artifact/claims/0/owner-ancestry/3")
    assert ancestry_detail.status_code == 200, ancestry_detail.text
    assert ancestry_detail.json() == ancestry_payload["nodes"][2]
    ancestry_path = client.get("/research/challenge/artifact/claims/0/owner-ancestry/3/path")
    assert ancestry_path.status_code == 200, ancestry_path.text
    assert [node["ordinal"] for node in ancestry_path.json()["nodes"]] == [1, 2, 3]
    assert ancestry_path.json()["graph_sha256"] == ancestry_payload["graph_sha256"]
    assert ancestry_path.json()["nodes"][2]["child_ordinals"] == []
    root_path = client.get("/research/challenge/artifact/claims/0/owner-ancestry/1/path")
    assert [node["ordinal"] for node in root_path.json()["nodes"]] == [1]
    assert root_path.json()["nodes"][0]["child_ordinals"] == []
    assert root_path.json()["graph_sha256"] != ancestry_payload["graph_sha256"]
    interrogation_command = {
        "content_hash": third_acceptance["artifact_content_hash"],
        "selected_terminal_ordinals": [3],
        "question": "Which conclusion survives the combined completed branches?",
        "mutation_key": "interrogate-reasoning-ancestry-three",
    }
    interrogation_preview = client.post(
        "/research/challenge/artifact/claims/0/ancestry-interrogation/preview",
        json=interrogation_command,
    )
    assert interrogation_preview.status_code == 200, interrogation_preview.text
    interrogation_candidate = interrogation_preview.json()
    assert interrogation_candidate["status"] == "candidate"
    assert interrogation_candidate["receipt"]["selected_terminal_ordinals"] == [3]
    assert interrogation_candidate["receipt"]["closure_ordinals"] == [1, 2, 3]
    assert interrogation_candidate["receipt"]["ordered_spawn_ids"] == [
        node["spawn_id"] for node in ancestry_payload["nodes"]
    ]
    assert interrogation_candidate["receipt"]["permits_provider_call"] is False
    assert interrogation_candidate["receipt"]["permits_spend"] is False
    interrogation_accept = client.post(
        "/research/challenge/artifact/claims/0/ancestry-interrogation/accept",
        json={
            **interrogation_command,
            "preview_sha256": interrogation_candidate["preview_sha256"],
            "receipt_sha256": interrogation_candidate["receipt"]["receipt_sha256"],
        },
    )
    assert interrogation_accept.status_code == 200, interrogation_accept.text
    assert interrogation_accept.json()["status"] == "accepted"
    assert (
        interrogation_accept.json()["manifest"]["manifest_id"]
        == (interrogation_candidate["receipt"]["manifest_id"])
    )
    interrogation_receipt_id = interrogation_accept.json()["receipt"]["receipt_id"]
    interrogation_read = client.get(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}"
    )
    assert interrogation_read.status_code == 200, interrogation_read.text
    assert interrogation_read.headers["cache-control"] == "private, no-store"
    assert interrogation_read.json()["stale"] is False
    assert interrogation_read.json()["receipt"] == interrogation_accept.json()["receipt"]
    continuation_options = client.get(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation-options"
    )
    assert continuation_options.status_code == 200, continuation_options.text
    continuation_payload = continuation_options.json()
    assert continuation_payload["action_authority"] is False
    assert (
        continuation_payload["receipt_sha256"]
        == interrogation_accept.json()["receipt"]["receipt_sha256"]
    )
    assert len(continuation_payload["context_sha256"]) == 64
    assert continuation_payload["whole_run_cost_projected"] is True
    assert continuation_payload["choices"] == [
        {
            **continuation_payload["choices"][0],
            "role": "synthesizer",
            "provider_id": "provider-test",
            "model_id": "model-test",
            "boot_ready": True,
            "available": True,
        }
    ]
    assert interrogation_accept.json()["receipt"]["question"] not in (continuation_options.text)
    assert "private completed reasoning" not in continuation_options.text
    choice = continuation_payload["choices"][0]
    envelope = choice["whole_run_envelope"]
    assert envelope["projection_kind"] == "admission_upper_bound"
    assert envelope["forecast_status"] == "not_measured"
    assert envelope["forecast_usd_low"] is None
    assert envelope["forecast_usd_high"] is None
    assert len(envelope["roles"]) == 6
    assert [row["max_calls"] for row in envelope["roles"]] == [2, 8, 1, 1, 6, 12]
    continuation_quote_body = {
        "expected_receipt_sha256": continuation_payload["receipt_sha256"],
        "provider_id": choice["provider_id"],
        "model_id": choice["model_id"],
        "pricing_fingerprint": choice["pricing_fingerprint"],
        "research_tier": "deep",
        "approved_run_ceiling_usd": 2.0,
    }
    continuation_quote = client.post(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation/quote",
        json=continuation_quote_body,
    )
    assert continuation_quote.status_code == 200, continuation_quote.text
    quote_payload = continuation_quote.json()
    assert quote_payload["spend_performed"] is False
    assert quote_payload["context_sha256"] == continuation_payload["context_sha256"]
    assert quote_payload["selected_driver_provider"] == "provider-test"
    assert quote_payload["selected_driver_model"] == "model-test"
    assert quote_payload["workload_plan_sha256"] == envelope["plan_sha256"]
    assert quote_payload["whole_run_maximum_usd"] == envelope["maximum_usd"]
    assert len(quote_payload["quote_token"]) >= 32
    subcent_quote = client.post(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation/quote",
        json={**continuation_quote_body, "approved_run_ceiling_usd": 0.014},
    )
    assert subcent_quote.status_code == 422
    assert interrogation_accept.json()["receipt"]["question"] not in (continuation_quote.text)
    stale_continuation_quote = client.post(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation/quote",
        json={**continuation_quote_body, "expected_receipt_sha256": "0" * 64},
    )
    assert stale_continuation_quote.status_code == 409
    assert stale_continuation_quote.headers["cache-control"] == "private, no-store"
    unquoted_driver = client.post(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation/quote",
        json={**continuation_quote_body, "pricing_fingerprint": "f" * 64},
    )
    assert unquoted_driver.status_code == 503
    assert unquoted_driver.headers["cache-control"] == "private, no-store"
    from interfaces.research.api.settings_budget import BudgetResponse

    with monkeypatch.context() as budget_patch:
        budget_patch.setenv("ANTIEK_OPERATOR_BUDGET_USD", "0.50")
        budget_patch.setattr(
            "interfaces.research.api.settings_budget.read_operator_budget",
            lambda: BudgetResponse(
                daily_cap_usd=1.0,
                spent_usd=0.5,
                remaining_usd=0.5,
                spent_status="known",
                cap_env="test",
            ),
        )
        over_budget_quote = client.post(
            f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation/quote",
            json=continuation_quote_body,
        )
        assert over_budget_quote.status_code == 409
        over_budget_launch = client.post(
            f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation",
            json={
                **continuation_quote_body,
                "research_quote_token": quote_payload["quote_token"],
            },
        )
        assert over_budget_launch.status_code == 409
    from interfaces.research.api.broadcast import EventBroadcaster

    broadcast_starts: list[str] = []
    broadcaster = EventBroadcaster()

    async def record_start(event):  # type: ignore[no-untyped-def]
        broadcast_starts.append(event.event_id)

    broadcaster.register_handler("investigation.start_requested", record_start)
    client.app.state.broadcaster = broadcaster
    continuation_launch = client.post(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation",
        json={
            **continuation_quote_body,
            "research_quote_token": quote_payload["quote_token"],
        },
    )
    assert continuation_launch.status_code == 202, continuation_launch.text
    launch_payload = continuation_launch.json()
    from substrate.dispatch.daily_research_budget import read_daily_research_budget

    daily_snapshot = read_daily_research_budget(account_id="alice", cap_usd="5.00")
    assert (daily_snapshot.held_cents, daily_snapshot.settled_cents) == (200, 0)
    assert launch_payload["parent_investigation_id"] == "challenge"
    assert launch_payload["ancestry_interrogation_receipt_id"] == (interrogation_receipt_id)
    assert launch_payload["selected_driver_model"] == "model-test"
    continuation_launch_replay = client.post(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation",
        json={
            **continuation_quote_body,
            "research_quote_token": quote_payload["quote_token"],
        },
    )
    assert continuation_launch_replay.status_code == 202
    assert continuation_launch_replay.json() == launch_payload
    assert broadcast_starts == [launch_payload["start_event_id"]]
    continuation_authority = InvestigationAuthority(
        "alice", launch_payload["investigation_id"], root=Path(api_env["events"])
    )
    from substrate.event_log import trajectory_authorized

    continuation_rows = trajectory_authorized(continuation_authority)
    assert sorted(row["action_type"] for row in continuation_rows) == [
        "investigation.spawned_from",
        "investigation.start_requested",
    ]
    continuation_start = next(
        row for row in continuation_rows if row["action_type"] == "investigation.start_requested"
    )
    assert (
        continuation_start["payload"]["question"]
        == (interrogation_accept.json()["receipt"]["question"])
    )
    assert continuation_start["payload"]["selected_driver_model"] == ("model-test")
    assert (
        continuation_start["payload"]["research_workload_plan_sha256"] == (envelope["plan_sha256"])
    )
    assert continuation_start["payload"]["research_projected_max_cost_usd"] == (
        float(envelope["maximum_usd"])
    )
    assert "research_quote_token" not in str(continuation_rows)
    tampered_continuation_launch = client.post(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation",
        json={
            **continuation_quote_body,
            "approved_run_ceiling_usd": 2.01,
            "research_quote_token": quote_payload["quote_token"],
        },
    )
    assert tampered_continuation_launch.status_code in (403, 409)

    recovery_quote = client.post(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation/quote",
        json=continuation_quote_body,
    )
    assert recovery_quote.status_code == 200
    recovery_quote_payload = recovery_quote.json()
    failing_broadcaster = EventBroadcaster()

    async def fail_before_execution_claim(_event):  # type: ignore[no-untyped-def]
        raise RuntimeError("fail before durable execution claim")

    failing_broadcaster.register_handler(
        "investigation.start_requested", fail_before_execution_claim
    )
    client.app.state.broadcaster = failing_broadcaster
    failed_delivery = client.post(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation",
        json={
            **continuation_quote_body,
            "research_quote_token": recovery_quote_payload["quote_token"],
        },
    )
    assert failed_delivery.status_code == 503

    import time as stdlib_time

    real_time_ns = stdlib_time.time_ns
    monkeypatch.setattr(
        stdlib_time,
        "time_ns",
        lambda: (recovery_quote_payload["expires_at_ms"] + 1) * 1_000_000,
    )
    recovered_starts: list[str] = []
    recovery_broadcaster = EventBroadcaster()

    async def recover_start(event):  # type: ignore[no-untyped-def]
        recovered_starts.append(event.event_id)

    recovery_broadcaster.register_handler("investigation.start_requested", recover_start)
    client.app.state.broadcaster = recovery_broadcaster
    recovered_delivery = client.post(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}/continuation",
        json={
            **continuation_quote_body,
            "research_quote_token": recovery_quote_payload["quote_token"],
        },
    )
    monkeypatch.setattr(stdlib_time, "time_ns", real_time_ns)
    assert recovered_delivery.status_code == 202, recovered_delivery.text
    assert recovered_starts == [recovered_delivery.json()["start_event_id"]]

    workspace_interrogation_entry = {
        "kind": "ancestry_interrogation",
        "investigation_id": "challenge",
        "manifest_id": interrogation_accept.json()["manifest"]["manifest_id"],
        "receipt_id": interrogation_receipt_id,
    }
    workspace_interrogation_put = client.put(
        "/account/workspace-resume",
        json={
            "schema_version": 1,
            "base_revision": 0,
            "entries": [workspace_interrogation_entry],
            "mutation_key": "persist-ancestry-interrogation",
        },
    )
    assert workspace_interrogation_put.status_code == 200, workspace_interrogation_put.text
    workspace_interrogation_get = client.get("/account/workspace-resume")
    assert workspace_interrogation_get.status_code == 200, workspace_interrogation_get.text
    assert workspace_interrogation_get.json()["entries"] == [workspace_interrogation_entry]
    interrogation_replay = client.post(
        "/research/challenge/artifact/claims/0/ancestry-interrogation/accept",
        json={
            **interrogation_command,
            "preview_sha256": interrogation_candidate["preview_sha256"],
            "receipt_sha256": interrogation_candidate["receipt"]["receipt_sha256"],
        },
    )
    assert interrogation_replay.json() == interrogation_accept.json()
    changed_interrogation = client.post(
        "/research/challenge/artifact/claims/0/ancestry-interrogation/preview",
        json={**interrogation_command, "question": "A changed question?"},
    )
    assert changed_interrogation.status_code == 200
    changed_interrogation_accept = client.post(
        "/research/challenge/artifact/claims/0/ancestry-interrogation/accept",
        json={
            **interrogation_command,
            "question": "A changed question?",
            "preview_sha256": changed_interrogation.json()["preview_sha256"],
            "receipt_sha256": changed_interrogation.json()["receipt"]["receipt_sha256"],
        },
    )
    assert changed_interrogation_accept.status_code == 409
    foreign_interrogation = client.post(
        "/research/challenge/artifact/claims/0/ancestry-interrogation/preview",
        headers={"x-test-user": "bob"},
        json=interrogation_command,
    )
    assert foreign_interrogation.status_code == 404
    assert "survives" not in foreign_interrogation.text
    pristine_ancestry_session = recursive_session_store.get_session(
        recursive_reservation["session_id"]
    )
    assert pristine_ancestry_session is not None
    corrupt_ancestry_session = json.loads(json.dumps(pristine_ancestry_session))
    corrupt_ancestry_session["claim_challenge"]["recursive_context_pack"]["rows"][0][
        "candidate_text"
    ] = "substituted ancestry reasoning"
    recursive_session_store.put_session(corrupt_ancestry_session)
    corrupt_ancestry = client.get("/research/challenge/artifact/claims/0/owner-ancestry")
    assert corrupt_ancestry.status_code == 404
    assert "substituted" not in corrupt_ancestry.text
    recursive_session_store.put_session(pristine_ancestry_session)
    foreign_ancestry = client.get(
        "/research/challenge/artifact/claims/0/owner-ancestry",
        headers={"x-test-user": "bob"},
    )
    assert foreign_ancestry.status_code == 404
    assert "recursive" not in foreign_ancestry.text

    later_manual_command = {
        "content_hash": third_acceptance["artifact_content_hash"],
        "supersedes_transition_sha256": third_acceptance["transition_sha256"],
        "operation": "restore_archived_terminal",
        "replacement_claim": None,
        "rationale": "Manual restoration after three research rounds.",
        "mutation_key": "manual-after-three-research-rounds",
    }
    later_manual_preview = client.post(
        "/research/challenge/artifact/claims/0/revision/compensation/preview",
        json=later_manual_command,
    )
    assert later_manual_preview.status_code == 200, later_manual_preview.text
    later_manual_accept = client.post(
        "/research/challenge/artifact/claims/0/revision/compensation/accept",
        json={
            **later_manual_command,
            "preview_sha256": later_manual_preview.json()["preview"]["preview_sha256"],
            "transition_sha256": later_manual_preview.json()["preview"]["transition_sha256"],
        },
    )
    assert later_manual_accept.status_code == 200, later_manual_accept.text
    historical_interrogation = client.get(
        f"/research/challenge/artifact/ancestry-interrogations/{interrogation_receipt_id}"
    )
    assert historical_interrogation.status_code == 200, historical_interrogation.text
    assert historical_interrogation.json()["stale"] is True
    historical_workspace_interrogation = client.get("/account/workspace-resume")
    assert historical_workspace_interrogation.status_code == 200, (
        historical_workspace_interrogation.text
    )
    assert historical_workspace_interrogation.json()["entries"] == [workspace_interrogation_entry]
    history_store = FilesystemArtifactStore()
    interrogation_history_path = history_store._history_path(
        authority,
        interrogation_accept.json()["receipt"]["artifact_content_hash"],
    )
    interrogation_history_bytes = interrogation_history_path.read_bytes()
    interrogation_history_path.unlink()
    try:
        unavailable_workspace_get = client.get("/account/workspace-resume")
        assert unavailable_workspace_get.status_code == 503
        assert unavailable_workspace_get.headers["cache-control"] == "no-store"
        unavailable_workspace_put = client.put(
            "/account/workspace-resume",
            json={
                "schema_version": 1,
                "base_revision": 1,
                "entries": [workspace_interrogation_entry],
                "mutation_key": "missing-ancestry-history",
            },
        )
        assert unavailable_workspace_put.status_code == 503
        assert unavailable_workspace_put.headers["cache-control"] == "no-store"
    finally:
        interrogation_history_path.write_bytes(interrogation_history_bytes)
        interrogation_history_path.chmod(0o600)
    stale_recursive = client.post(
        "/research/challenge/artifact/claims/0/recursive-context/preview",
        json=recursive_command,
    )
    assert stale_recursive.status_code == 409
    replayed_rounds = client.get("/research/challenge/artifact/claims/0/owner-iterations")
    assert replayed_rounds.status_code == 200, replayed_rounds.text
    replayed_payload = replayed_rounds.json()
    assert len(replayed_payload["rounds"]) == 3
    assert all(not row["result_is_current"] for row in replayed_payload["rounds"])
    assert [row["transition_sha256"] for row in replayed_payload["rounds"]] == [
        node["transition_sha256"] for node in ancestry_payload["nodes"]
    ]
    assert replayed_payload["current_effective_claim"] == body.claim_support[0].claim
    replayed_first_result = client.get(first_result_url)
    assert replayed_first_result.status_code == 200, replayed_first_result.text
    assert replayed_first_result.text == first_result_html.text
    foreign_iterations = client.get(
        "/research/challenge/artifact/claims/0/owner-iterations",
        headers={"x-test-user": "bob"},
    )
    assert foreign_iterations.status_code == 404
    assert "Fresh analysis" not in foreign_iterations.text
    monkeypatch.setattr(
        "interfaces.research.api.artifact_routes.read_canonical_artifact",
        read_artifact,
    )
    corrupt_payload = consumed_body.model_dump(mode="json")
    corrupt_transition = corrupt_payload["owner_claim_compensations"][-1]
    corrupt_transition["source_context_receipt_sha256"] = "9" * 64
    corrupt_transition["transition_sha256"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in corrupt_transition.items() if key != "transition_sha256"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    corrupt_body = ResearchArtifactBody.model_validate(corrupt_payload)
    FilesystemArtifactStore().write(authority, render_html(corrupt_body))
    corrupt_consumed_review = client.get(context_review_base)
    assert corrupt_consumed_review.status_code == 404
    assert "Fresh analysis" not in corrupt_consumed_review.text
    corrupt_iterations = client.get("/research/challenge/artifact/claims/0/owner-iterations")
    assert corrupt_iterations.status_code == 404
    assert "Fresh analysis" not in corrupt_iterations.text
    FilesystemArtifactStore().write(authority, consumed_html)
    root_history = client.get(
        f"/research/challenge/artifact/history/{compensation_command['content_hash']}"
    )
    assert root_history.status_code == 200, root_history.text
    assert root_history.text == root_revision_html
    historical = client.get(f"/research/challenge/artifact/history/{body.content_hash()}")
    assert historical.status_code == 200, historical.text
    assert historical.headers["cache-control"] == "private, no-store"
    assert historical.headers["x-antiek-historical-content-hash"] == body.content_hash()
    assert historical.text == html
    foreign_history = client.get(
        f"/research/challenge/artifact/history/{body.content_hash()}",
        headers={"x-test-user": "bob"},
    )
    assert foreign_history.status_code == 404
    assert "server-authored" not in foreign_history.text
    reversed_review = client.post(
        f"{review_base}/reverse",
        json={
            "content_hash": body.content_hash(),
            "acceptance_receipt_sha256": acceptance_receipt,
            "rationale": "A later owner review is required.",
            "mutation_key": "reverse-review-one",
        },
    )
    assert reversed_review.status_code == 200, reversed_review.text
    assert reversed_review.json()["status"] == "reversed"
    reversed_projection = client.get(
        "/research/challenge/artifact/claims/0",
        params={"content_hash": body.content_hash()},
    )
    assert reversed_projection.json()["reviews"][0]["status"] == (
        "later_owner_reversed_counter_analysis"
    )
    assert reversed_projection.json()["reconsiderations"] == []
    assert authority.artifact_path().read_bytes() != artifact_before
    revised_body = parse_body_from_html(FilesystemArtifactStore().read(authority))
    assert revised_body.claim_support == body.claim_support
    assert revised_body.synthesis_event_id == body.synthesis_event_id
    assert revised_body.owner_claim_revisions[0].revised_claim.startswith("A reconsidered")
    assert revised_body.schema_version == 4
    assert revised_body.owner_claim_compensations[0].operation == ("restore_archived_terminal")
    assert revised_body.owner_claim_compensations[1].schema_version == 2
    assert revised_body.effective_owner_claim(0)[0] == ("A narrower owner-authored wording.")
    foreign_review = client.post(
        f"{review_base}/preview",
        headers={"x-test-user": "bob"},
        json={"content_hash": body.content_hash()},
    )
    assert foreign_review.status_code == 404
    assert "Candidate finding" not in foreign_review.text


def test_http_import_rejects_arbitrary_server_path(api_env, tmp_path):
    secret = tmp_path / "secret.html"
    secret.write_text("private", encoding="utf-8")
    client = _client()
    response = client.post(
        "/research/inv-path/artifact/import-notes",
        json={"path": str(secret)},
    )
    assert response.status_code == 422
    assert secret.read_text(encoding="utf-8") == "private"


def _multi_owner_client(*, include_engagement: bool = False) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def test_identity(request, call_next):  # type: ignore[no-untyped-def]
        user_id = request.headers.get("x-test-user", "alice")
        claims = UserClaims(
            user_id=user_id,
            email=None,
            scopes=frozenset({"private_research"}),
            issued_at="2026-07-15T00:00:00Z",
        )
        request.state.user_claims = claims
        request.state.user_id = user_id
        request.state.scopes = claims.scopes
        request.state.auth_method = "test_authenticated"
        return await call_next(request)

    app.include_router(artifact_router)
    if include_engagement:
        app.include_router(engagement_router)
        app.include_router(workspace_resume_router)
    return TestClient(app)


def test_same_investigation_exports_are_owner_isolated(api_env):
    events = Path(api_env["events"])
    alice_authority = InvestigationAuthority("alice", "shared", root=events)
    bob_authority = InvestigationAuthority("bob", "shared", root=events)
    named_operator_authority = InvestigationAuthority("__operator__", "shared", root=events)
    initialize_composite_stream(alice_authority)
    initialize_composite_stream(bob_authority)
    initialize_composite_stream(named_operator_authority)
    promote_insight_authorized(alice_authority, text="Alice private artifact insight")
    promote_insight_authorized(bob_authority, text="Bob private artifact insight")
    promote_insight_authorized(
        named_operator_authority, text="Authenticated named-operator private insight"
    )
    with connect_write(api_env["db"], purpose="test-artifact-owner-shadow") as con:
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.UNSCOPED,
            desired=GraphTenancyState.COPYING,
        )
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.COPYING,
            desired=GraphTenancyState.SHADOW,
        )
    client = _multi_owner_client()
    alice = client.post("/research/shared/artifact/export", headers={"x-test-user": "alice"})
    bob = client.post("/research/shared/artifact/export", headers={"x-test-user": "bob"})
    assert alice.status_code == bob.status_code == 200
    assert (
        ArtifactAuthority("alice", "shared").artifact_path()
        != ArtifactAuthority("bob", "shared").artifact_path()
    )

    alice_html = client.get("/research/shared/artifact/view", headers={"x-test-user": "alice"}).text
    bob_html = client.get("/research/shared/artifact/view", headers={"x-test-user": "bob"}).text
    assert "Alice private artifact insight" in alice_html
    assert "Bob private artifact insight" not in alice_html
    assert "Bob private artifact insight" in bob_html
    assert "Alice private artifact insight" not in bob_html

    authenticated_named_operator = client.post(
        "/research/shared/artifact/export", headers={"x-test-user": "__operator__"}
    )
    assert authenticated_named_operator.status_code == 200
    authenticated_named_operator_html = client.get(
        "/research/shared/artifact/view", headers={"x-test-user": "__operator__"}
    ).text
    assert "Authenticated named-operator private insight" in authenticated_named_operator_html
    assert "Alice private artifact insight" not in authenticated_named_operator_html
    assert "Bob private artifact insight" not in authenticated_named_operator_html

    alice_blocks = client.get(
        "/research/shared/artifact/blocks", headers={"x-test-user": "alice"}
    ).json()["blocks"]
    bob_blocks = client.get(
        "/research/shared/artifact/blocks", headers={"x-test-user": "bob"}
    ).json()["blocks"]
    assert [row["label"] for row in alice_blocks] == ["Alice private artifact insight"]
    assert [row["label"] for row in bob_blocks] == ["Bob private artifact insight"]

    bob_artifact_authority = ArtifactAuthority("bob", "shared")
    bob_path = bob_artifact_authority.artifact_path()
    bob_sidecar = bob_artifact_authority.sidecar_path()
    bob_before = (
        bob_path.read_bytes(),
        bob_sidecar.read_bytes(),
        bob_path.stat().st_mtime_ns,
        hashlib.sha256(bob_path.read_bytes()).hexdigest(),
        trajectory(
            bob_artifact_authority.event_stream_id,
            events_dir=api_env["events"],
        ),
    )

    note = client.post(
        "/research/shared/artifact/append-note",
        headers={"x-test-user": "alice"},
        json={"note": "Alice private note"},
    )
    assert note.status_code == 200, note.text
    empty_note = client.post(
        "/research/shared/artifact/append-note",
        headers={"x-test-user": "alice"},
        json={"note": "  \n\t "},
    )
    assert empty_note.status_code == 422
    assert (
        "Alice private note"
        in client.get("/research/shared/artifact/view", headers={"x-test-user": "alice"}).text
    )
    assert (
        "Alice private note"
        not in client.get("/research/shared/artifact/view", headers={"x-test-user": "bob"}).text
    )
    imported = client.post(
        "/research/shared/artifact/import-notes",
        headers={"x-test-user": "alice"},
        json={},
    )
    assert imported.status_code == 200, imported.text
    assert (
        bob_path.read_bytes(),
        bob_sidecar.read_bytes(),
        bob_path.stat().st_mtime_ns,
        hashlib.sha256(bob_path.read_bytes()).hexdigest(),
        trajectory(
            bob_artifact_authority.event_stream_id,
            events_dir=api_env["events"],
        ),
    ) == bob_before

    # A third owner receives the same response for foreign and nonexistent IDs.
    foreign = client.post(
        "/research/shared/artifact/import-notes",
        headers={"x-test-user": "mallory"},
        json={},
    )
    missing = client.post(
        "/research/absent/artifact/import-notes",
        headers={"x-test-user": "mallory"},
        json={},
    )
    assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())
    assert foreign.status_code == 404
