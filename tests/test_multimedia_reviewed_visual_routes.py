from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes as multimedia_routes_module
from interfaces.research.api.multimedia_reviewed_visual_routes import (
    MultimediaReviewedVisualRuntime,
    get_multimedia_reviewed_visual_runtime,
    multimedia_reviewed_visual_router,
    multimedia_reviewed_visual_runtime_from_environment,
)
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore
from substrate.multimedia.reviewed_visual_registry import ReviewedVisualRegistry
from substrate.multimedia.visual_selection import ReviewedVisualSelection

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _setup(tmp_path: Path, *, operator: str = "owner-1"):
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Reviewed visual route",
            target_minutes=15,
            mode="video",
            route_policy="balanced",
            sources=("Evidence",),
        ),
        owner_id="owner-1",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")
    root = tmp_path / "candidates"
    root.mkdir()

    def resolver(record, owner_id: str, chapter_id: str, candidate_id: str):
        assert owner_id == "owner-1"
        chapter = next(row for row in record.plan.chapters if row.chapter_id == chapter_id)
        path = root / f"{candidate_id}.ppm"
        path.write_bytes(f"P6\n1 1\n255\n{candidate_id}".encode())
        scene = next(row for row in record.plan.scenes if row.chapter_id == chapter_id)
        return ReviewedVisualSelection(
            scene_id=scene.scene_id,
            path=str(path),
            expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            visual_label="generated",
            source_chunk_ids=chapter.source_chunk_ids,
            execution_receipt_id=f"exec-{candidate_id}",
            artifact_receipt_id=f"artifact-{candidate_id}",
        )

    runtime = MultimediaReviewedVisualRuntime(
        store=store,
        registry=ReviewedVisualRegistry(
            db_path=str(tmp_path / "visuals.duckdb"), integrity_key=b"v" * 32
        ),
        candidate_resolver=resolver,
        clock=lambda: NOW,
    )
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.auth_method = "antiek_session_cookie"
        request.state.user_id = operator
        return await call_next(request)

    app.include_router(multimedia_reviewed_visual_router, prefix="/api/multimedia")
    app.dependency_overrides[get_multimedia_reviewed_visual_runtime] = lambda: runtime
    spoken = tuple(
        chapter
        for chapter in ready.plan.chapters
        if any(
            line.line_id.split("-line-", 1)[0] == chapter.chapter_id
            for line in ready.plan.script_lines
        )
    )
    return TestClient(app), ready, spoken


def _body(record, spoken):
    return {
        "request_id": "request-1",
        "expected_revision_id": record.asset.revision_id,
        "bindings": [
            {"chapter_id": chapter.chapter_id, "candidate_id": f"candidate-{index}"}
            for index, chapter in enumerate(spoken)
        ],
    }


def test_post_and_get_return_only_safe_reviewed_set_projection(tmp_path: Path) -> None:
    client, ready, spoken = _setup(tmp_path)
    url = f"/api/multimedia/assets/{ready.asset.asset_id}/reviewed-visuals"
    response = client.post(url, json=_body(ready, spoken))
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == ready.asset.asset_id
    assert payload["chapter_ids"] == [row.chapter_id for row in spoken]
    serialized = response.text
    for forbidden in (
        '"path"',
        "expected_sha256",
        "execution_receipt_id",
        "artifact_receipt_id",
        "source_locator_digest",
        "rights_review_id",
        "registry_mac",
    ):
        assert forbidden not in serialized
    assert client.post(url, json=_body(ready, spoken)).json() == payload
    fetched = client.get(url, params={"revision_id": ready.asset.revision_id})
    assert fetched.status_code == 200
    assert fetched.json() == payload


def test_foreign_owner_is_opaque_and_client_authority_fields_are_forbidden(
    tmp_path: Path,
) -> None:
    foreign, ready, spoken = _setup(tmp_path, operator="owner-2")
    url = f"/api/multimedia/assets/{ready.asset.asset_id}/reviewed-visuals"
    assert foreign.post(url, json=_body(ready, spoken)).status_code == 404

    owner, ready, spoken = _setup(tmp_path / "owner")
    body = _body(ready, spoken)
    body["bindings"][0]["path"] = "/tmp/attacker.ppm"
    body["bindings"][0]["expected_sha256"] = "0" * 64
    assert owner.post(
        f"/api/multimedia/assets/{ready.asset.asset_id}/reviewed-visuals", json=body
    ).status_code == 422


def test_stale_incomplete_and_changed_replay_fail(tmp_path: Path) -> None:
    client, ready, spoken = _setup(tmp_path)
    url = f"/api/multimedia/assets/{ready.asset.asset_id}/reviewed-visuals"
    body = _body(ready, spoken)
    assert client.post(url, json={**body, "expected_revision_id": "rev-old"}).status_code == 409
    assert client.post(url, json={**body, "bindings": body["bindings"][:-1]}).status_code == 409
    assert client.post(url, json=body).status_code == 200
    changed = _body(ready, spoken)
    changed["bindings"][0]["candidate_id"] = "candidate-changed"
    assert client.post(url, json=changed).status_code == 409


def test_environment_authorities_are_all_or_nothing(tmp_path: Path) -> None:
    _client, _ready, _spoken = _setup(tmp_path)
    values = {
        "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_ENABLED": "true",
        "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_DB_PATH": str(tmp_path / "env.duckdb"),
        "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_INTEGRITY_KEY_HEX": "11" * 32,
        "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_AUTHORITY_DB_PATH": str(tmp_path / "auth.duckdb"),
        "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_AUTHORITY_SIGNING_KEY_HEX": "22" * 32,
        "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_EXECUTION_DB_PATH": str(tmp_path / "exec.duckdb"),
        "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_EXECUTION_SIGNING_KEY_HEX": "33" * 32,
        "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_OPERATOR_VERIFY_KEY_HEX": "44" * 32,
        "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_EVIDENCE_AUTHORITY_KEY_HEX": "55" * 32,
        "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_AUTHORIZED_REVIEWER_IDS": "owner-1",
    }
    runtime = multimedia_reviewed_visual_runtime_from_environment(
        store=_client.app.dependency_overrides[get_multimedia_reviewed_visual_runtime]().store,
        environ=values,
    )
    assert runtime is not None
    assert multimedia_reviewed_visual_runtime_from_environment(
        store=runtime.store, environ={}
    ) is None
    values.pop("ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_AUTHORITY_DB_PATH")
    try:
        multimedia_reviewed_visual_runtime_from_environment(store=runtime.store, environ=values)
    except RuntimeError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("partial reviewed visual configuration must fail")

    values["ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_AUTHORITY_DB_PATH"] = str(
        tmp_path / "auth.duckdb"
    )
    values["ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_AUTHORIZED_REVIEWER_IDS"] = " , "
    with pytest.raises(RuntimeError, match="invalid"):
        multimedia_reviewed_visual_runtime_from_environment(store=runtime.store, environ=values)


def test_app_registration_composes_reviewed_visual_runtime(tmp_path: Path, monkeypatch) -> None:
    client, _ready, _spoken = _setup(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_reviewed_visual_runtime]()
    monkeypatch.setattr(multimedia_routes_module, "_STORE", runtime.store)
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_reconciliation_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_knowledge_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_playback_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_narration_authorization_runtime_from_environment",
        lambda *, store: None,
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_reviewed_visual_runtime_from_environment",
        lambda *, store: runtime,
    )
    app = FastAPI()
    multimedia_routes_module.register_multimedia_routes(app)
    configured = app.dependency_overrides[get_multimedia_reviewed_visual_runtime]()
    assert configured is runtime
