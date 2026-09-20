from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.multimedia_research_intent_routes import (
    ResearchIntentRouteRuntime,
    get_multimedia_research_intent_runtime,
    multimedia_research_intent_router,
)
from interfaces.research.api.multimedia_routes import _resolve_research_audio_authority
from substrate.multimedia.research_intent import ResearchIntentLedger
from substrate.multimedia.verified_audio_playback import (
    AudioEvidenceSourceMetadata,
    AudioLearnedClaimMetadata,
    AudioPlaybackMetadata,
)


def _metadata(status: str = "verified_exact") -> AudioPlaybackMetadata:
    text = "Exact claim."
    source = AudioEvidenceSourceMetadata(
        "chunk-1", "doc-1", None, "canonical_graph", "a" * 64,
        0, len(text), "b" * 64, text,
    )
    claim = AudioLearnedClaimMetadata(
        "chapter-1", text, 1, "Investigate this claim.", "chapter-1-line-0",
        (source,) if status == "verified_exact" else (), ("chunk-1",), status,
    )
    return AudioPlaybackMetadata(
        "asset-1", "rev-1", "c" * 64, "d" * 64, 12, 1.0,
        ("chapter-1",), 1, 1, 1, (claim,), (),
    )


def _client(tmp_path, status: str = "verified_exact") -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.auth_method = "antiek_session_cookie"
        request.state.user_id = request.headers.get("x-owner", "owner-1")
        return await call_next(request)

    app.include_router(multimedia_research_intent_router, prefix="/multimedia")
    runtime = ResearchIntentRouteRuntime(
        ResearchIntentLedger(tmp_path),
        lambda owner: ("a" if owner == "owner-1" else "b") * 64,
        lambda asset, revision, owner: _metadata(status),
    )
    app.dependency_overrides[get_multimedia_research_intent_runtime] = lambda: runtime
    return TestClient(app)


def test_create_replay_get_owner_opacity_and_no_store(tmp_path) -> None:
    client = _client(tmp_path)
    body = {
        "expected_revision_id": "rev-1", "line_id": "chapter-1-line-0",
        "question": "Why is this exact?", "idempotency_key": "request-123456789",
    }
    created = client.post("/multimedia/assets/asset-1/research-intents", json=body)
    replay = client.post("/multimedia/assets/asset-1/research-intents", json=body)
    assert created.status_code == 201 and replay.status_code == 200
    assert created.json() == replay.json()
    assert created.headers["cache-control"] == "private, no-store"
    intent_id = created.json()["intent_id"]
    assert client.get(f"/multimedia/research-intents/{intent_id}").status_code == 200
    foreign = client.get(f"/multimedia/research-intents/{intent_id}", headers={"x-owner": "owner-2"})
    assert foreign.status_code == 404 and foreign.headers["cache-control"] == "private, no-store"


def test_legacy_unknown_and_schema_rejection_are_non_cacheable(tmp_path) -> None:
    client = _client(tmp_path, "unavailable_legacy")
    body = {
        "expected_revision_id": "rev-1", "line_id": "chapter-1-line-0",
        "question": "Why is this exact?", "idempotency_key": "request-123456789",
    }
    legacy = client.post("/multimedia/assets/asset-1/research-intents", json=body)
    unknown = client.post(
        "/multimedia/assets/asset-1/research-intents", json={**body, "line_id": "missing"}
    )
    malformed = client.post(
        "/multimedia/assets/asset-1/research-intents", json={**body, "claim_text": "forged"}
    )
    assert legacy.status_code == 409
    assert unknown.status_code == 404
    assert malformed.status_code == 422
    assert all(row.headers["cache-control"] == "private, no-store" for row in (legacy, unknown, malformed))


def test_authority_identity_substitution_is_a_private_conflict(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_intent_runtime]()
    client.app.dependency_overrides[get_multimedia_research_intent_runtime] = lambda: ResearchIntentRouteRuntime(
        runtime.ledger,
        runtime.owner_digest_resolver,
        lambda asset, revision, owner: replace(_metadata(), asset_id="substituted"),
    )
    response = client.post("/multimedia/assets/asset-1/research-intents", json={
        "expected_revision_id": "rev-1", "line_id": "chapter-1-line-0",
        "question": "Why is this exact?", "idempotency_key": "request-123456789",
    })
    assert response.status_code == 409
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(("route_policy", "expected_backend"), [("cheapest", "local"), ("balanced", "paid")])
def test_registered_authority_routes_by_policy_and_cross_binds_link(
    route_policy: str, expected_backend: str
) -> None:
    metadata = _metadata()
    link = SimpleNamespace(
        asset_id=metadata.asset_id, revision_id=metadata.revision_id,
        receipt_sha256=metadata.receipt_sha256, audio_sha256=metadata.audio_sha256,
        audio_size_bytes=metadata.audio_size_bytes, duration_seconds=metadata.duration_seconds,
        chapter_ids=metadata.chapter_ids, retention_marker_count=metadata.retention_marker_count,
        learned_claim_count=metadata.learned_claim_count, source_count=metadata.source_count,
        owner_identity_digest="a" * 64,
    )
    record = SimpleNamespace(
        asset=SimpleNamespace(revision_id="rev-1", route_policy=route_policy),
        audio_production_link=link,
        plan=object(),
    )
    store = Mock()
    store.get.return_value = record
    local_playback = Mock()
    paid_playback = Mock()
    local_playback.metadata.return_value = metadata
    paid_playback.metadata.return_value = metadata
    result = _resolve_research_audio_authority(
        store=store,
        local_audible_runtime=SimpleNamespace(playback=local_playback),
        production_worker_runtime=SimpleNamespace(audio_playback=paid_playback),
        asset_id="asset-1", revision_id="rev-1", operator_id="owner-1",
    )
    assert result == metadata
    store.get.assert_called_once_with("asset-1", owner_id="owner-1")
    assert local_playback.metadata.call_count == (1 if expected_backend == "local" else 0)
    assert paid_playback.metadata.call_count == (1 if expected_backend == "paid" else 0)


def test_registered_authority_rejects_stale_revision_and_link_drift() -> None:
    metadata = _metadata()
    record = SimpleNamespace(
        asset=SimpleNamespace(revision_id="rev-2", route_policy="cheapest"),
        audio_production_link=None,
        plan=object(),
    )
    store = Mock()
    store.get.return_value = record
    with pytest.raises(ValueError, match="revision is not current"):
        _resolve_research_audio_authority(
            store=store, local_audible_runtime=None, production_worker_runtime=None,
            asset_id="asset-1", revision_id="rev-1", operator_id="owner-1",
        )
    record.asset.revision_id = "rev-1"
    record.audio_production_link = SimpleNamespace(
        asset_id="asset-1", revision_id="rev-1", owner_identity_digest="a" * 64,
        receipt_sha256="f" * 64, audio_sha256=metadata.audio_sha256,
        audio_size_bytes=metadata.audio_size_bytes, duration_seconds=metadata.duration_seconds,
        chapter_ids=metadata.chapter_ids, retention_marker_count=metadata.retention_marker_count,
        learned_claim_count=metadata.learned_claim_count, source_count=metadata.source_count,
    )
    playback = Mock()
    playback.metadata.return_value = metadata
    with pytest.raises(ValueError, match="registration conflicts"):
        _resolve_research_audio_authority(
            store=store, local_audible_runtime=SimpleNamespace(playback=playback),
            production_worker_runtime=None, asset_id="asset-1", revision_id="rev-1",
            operator_id="owner-1",
        )
