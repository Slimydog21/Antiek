from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_production_worker_routes as routes_module
from interfaces.research.api.multimedia_production_worker_routes import (
    get_multimedia_production_worker_runtime,
    multimedia_production_worker_router,
)
from substrate.multimedia.execution_authorization import (
    ExecutionAuthorizationIntegrityError,
    issue_async_execution_authorization,
)
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
    MultimediaProductionLink,
)

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _setup(tmp_path, monkeypatch, *, owner="owner-1"):
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Production route",
            target_minutes=15,
            mode="video",
            route_policy="balanced",
            sources=("Evidence",),
            selected_arc_ids=("history",),
        ),
        owner_id="owner-1",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")
    chapter_ids = tuple(
        chapter.chapter_id
        for chapter in ready.plan.chapters
        if any(
            line.line_id.split("-line-", 1)[0] == chapter.chapter_id
            for line in ready.plan.script_lines
        )
    )
    captured = {}

    def produce(asset_id, request, *, owner_id, runtime):
        captured.update(
            asset_id=asset_id, request=request, owner_id=owner_id, runtime=runtime
        )
        link = MultimediaProductionLink(
            owner_identity_digest=ready.asset.owner_user_id,
            asset_id=asset_id,
            revision_id=ready.asset.revision_id,
            receipt_sha256="a" * 64,
            video_sha256="b" * 64,
            audio_sha256="c" * 64,
            duration_seconds=10,
            width_px=320,
            height_px=240,
            chapter_ids=chapter_ids,
        )
        return ready.model_copy(update={"production_link": link})

    monkeypatch.setattr(routes_module, "produce_authorized_multimedia", produce)
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.auth_method = "antiek_session_cookie"
        request.state.user_id = owner
        return await call_next(request)

    app.include_router(multimedia_production_worker_router, prefix="/api/multimedia")
    runtime = object()
    app.dependency_overrides[get_multimedia_production_worker_runtime] = lambda: runtime
    return TestClient(app), ready, chapter_ids, captured, runtime


def _body(ready, chapter_ids):
    rows = []
    for index, chapter_id in enumerate(chapter_ids):
        authority = issue_async_execution_authorization(
            signing_key=b"s" * 32,
            request_id=f"request-{index}",
            operator_id="owner-1",
            asset_id=ready.asset.asset_id,
            revision_id=f"tts-child-{index}",
            provider="trusted-tts",
            route_policy="balanced",
            model="voice-1",
            endpoint_capability="text-to-speech",
            catalog_version="catalog-1",
            catalog_digest="a" * 64,
            quote_id=f"quote-{index}",
            quote_expires_at=NOW + timedelta(hours=1),
            recovery_authority_id="recovery-1",
            recovery_verification_key_digest="b" * 64,
            approved_ceiling_microdollars=100_000,
            request_body_digest="c" * 64,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
        rows.append({"chapter_id": chapter_id, "authorization": asdict(authority)})
    return {
        "expected_revision_id": ready.asset.revision_id,
        "chapter_authorities": rows,
        "voice": "narrator",
        "speed": 1,
        "sample_rate_hz": 8000,
        "channels": 1,
    }


def test_authenticated_route_parses_exact_authority_set(tmp_path, monkeypatch) -> None:
    client, ready, chapter_ids, captured, runtime = _setup(tmp_path, monkeypatch)
    response = client.post(
        f"/api/multimedia/assets/{ready.asset.asset_id}/production",
        json=_body(ready, chapter_ids),
    )
    assert response.status_code == 200
    assert response.json()["production_link"]["revision_id"] == ready.asset.revision_id
    assert captured["owner_id"] == "owner-1"
    assert captured["runtime"] is runtime
    assert tuple(
        row.chapter_id for row in captured["request"].chapter_authorities
    ) == chapter_ids


def test_route_forbids_client_runtime_fields_and_requires_auth(tmp_path, monkeypatch) -> None:
    client, ready, chapter_ids, _captured, _runtime = _setup(tmp_path, monkeypatch)
    body = _body(ready, chapter_ids)
    body["ffmpeg_path"] = "/tmp/attacker"
    body["chapter_authorities"][0]["authorization"]["signing_key"] = "secret"
    response = client.post(
        f"/api/multimedia/assets/{ready.asset.asset_id}/production", json=body
    )
    assert response.status_code == 422

    app = FastAPI()
    app.include_router(multimedia_production_worker_router, prefix="/api/multimedia")
    app.dependency_overrides[get_multimedia_production_worker_runtime] = lambda: object()
    unauthenticated = TestClient(app)
    assert unauthenticated.post(
        f"/api/multimedia/assets/{ready.asset.asset_id}/production",
        json=_body(ready, chapter_ids),
    ).status_code == 401


def test_tampered_authority_is_a_conflict_not_runtime_outage(tmp_path, monkeypatch) -> None:
    client, ready, chapter_ids, _captured, _runtime = _setup(tmp_path, monkeypatch)

    def reject(*_args, **_kwargs):
        raise ExecutionAuthorizationIntegrityError("signature mismatch")

    monkeypatch.setattr(routes_module, "produce_authorized_multimedia", reject)
    response = client.post(
        f"/api/multimedia/assets/{ready.asset.asset_id}/production",
        json=_body(ready, chapter_ids),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "multimedia production authority conflicts"
