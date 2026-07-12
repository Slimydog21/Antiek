from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes as multimedia_routes_module
from interfaces.research.api.multimedia_reconciliation_routes import (
    authenticated_multimedia_operator,
)
from interfaces.research.api.multimedia_visual_authorization_routes import (
    MultimediaVisualAuthorizationRuntime,
)
from interfaces.research.api.multimedia_visual_candidate_routes import (
    MultimediaVisualCandidateRuntime,
    get_multimedia_visual_candidate_runtime,
    multimedia_visual_candidate_router,
    multimedia_visual_candidate_runtime_from_environment,
)
from interfaces.research.api.multimedia_visual_generation_routes import (
    MultimediaVisualGenerationRuntime,
)
from tests.test_multimedia_visual_authorization import KEY, _terms
from tests.test_multimedia_visual_authorization_routes import _config
from tests.test_multimedia_visual_candidate_materialization import (
    NOW,
    Resolver,
    Transport,
    _succeeded,
)


def _client(runtime) -> TestClient:
    app = FastAPI()
    app.include_router(multimedia_visual_candidate_router, prefix="/multimedia")
    app.dependency_overrides[authenticated_multimedia_operator] = lambda: "owner-1"
    app.dependency_overrides[get_multimedia_visual_candidate_runtime] = lambda: runtime
    return TestClient(app)


def test_route_returns_safe_quarantine_metadata_and_exact_replay(tmp_path: Path) -> None:
    store, ready, registry, db, client, execution_id, quarantine = _succeeded(tmp_path)
    authority = MultimediaVisualAuthorizationRuntime(
        store=store, registry=registry, terms=_terms(),
        db_path=str(tmp_path / "authority.duckdb"), signing_key=KEY,
    )
    generation = MultimediaVisualGenerationRuntime(authority, client, db, lambda: NOW)
    transport = Transport()
    runtime = MultimediaVisualCandidateRuntime(
        generation, Resolver(), transport, frozenset({"assets.example"}),
        str(quarantine), lambda: NOW,
    )
    api = _client(runtime)
    route = f"/multimedia/assets/{ready.asset.asset_id}/visual-generations/{execution_id}/materialize"
    body = {
        "authority_request_id": "visual-request-1",
        "expected_revision_id": ready.asset.revision_id,
    }
    first = api.post(route, json=body)
    replay = api.post(route, json=body)
    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json() and transport.calls == 2
    assert set(first.json()) == {"execution_id", "candidates"}
    assert set(first.json()["candidates"][0]) == {
        "candidate_id", "artifact_receipt_id", "media_type", "byte_count"
    }
    lowered = first.text.lower()
    assert "https://" not in lowered and "/private/" not in lowered and "sha256" not in lowered


def test_environment_is_all_or_nothing_and_binds_private_quarantine(tmp_path: Path) -> None:
    store, _ready_record = __import__(
        "tests.test_multimedia_visual_authorization", fromlist=["_ready"]
    )._ready(tmp_path / "store")
    assert multimedia_visual_candidate_runtime_from_environment(store=store, environ={}) is None
    config = _config(tmp_path / "runtime")
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_TOKEN"] = "account-id:secret"
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_ACCOUNT_IDENTITY_DIGEST"] = hashlib.sha256(
        b"account-id"
    ).hexdigest()
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_DB_PATH"] = str(
        tmp_path / "runtime" / "execution.duckdb"
    )
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir(mode=0o700)
    config["ANTIEK_MULTIMEDIA_VISUAL_CANDIDATE_ALLOWED_HOSTS"] = "assets.example"
    config["ANTIEK_MULTIMEDIA_VISUAL_CANDIDATE_QUARANTINE_DIR"] = str(quarantine)
    runtime = multimedia_visual_candidate_runtime_from_environment(
        store=store, environ=config, resolver=Resolver(), transport=Transport()
    )
    assert runtime is not None and "secret" not in repr(runtime)


def test_multimedia_registration_installs_candidate_runtime(tmp_path: Path, monkeypatch) -> None:
    store, _ = __import__(
        "tests.test_multimedia_visual_authorization", fromlist=["_ready"]
    )._ready(tmp_path / "store")
    config = _config(tmp_path / "runtime")
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_TOKEN"] = "account-id:secret"
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_ACCOUNT_IDENTITY_DIGEST"] = hashlib.sha256(
        b"account-id"
    ).hexdigest()
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_DB_PATH"] = str(
        tmp_path / "runtime" / "execution.duckdb"
    )
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir(mode=0o700)
    config["ANTIEK_MULTIMEDIA_VISUAL_CANDIDATE_ALLOWED_HOSTS"] = "assets.example"
    config["ANTIEK_MULTIMEDIA_VISUAL_CANDIDATE_QUARANTINE_DIR"] = str(quarantine)
    runtime = multimedia_visual_candidate_runtime_from_environment(
        store=store, environ=config, resolver=Resolver(), transport=Transport()
    )
    assert runtime is not None
    monkeypatch.setattr(multimedia_routes_module, "_STORE", store)
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_reconciliation_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_knowledge_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_playback_runtime_from_environment", lambda: None
    )
    for name in (
        "multimedia_narration_authorization_runtime_from_environment",
        "multimedia_reviewed_visual_runtime_from_environment",
        "multimedia_production_worker_runtime_from_environment",
        "multimedia_visual_authorization_runtime_from_environment",
        "multimedia_visual_generation_runtime_from_environment",
    ):
        monkeypatch.setattr(multimedia_routes_module, name, lambda *, store: None)
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_tts_gateway_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_visual_candidate_runtime_from_environment", lambda *, store: runtime,
    )
    app = FastAPI()
    multimedia_routes_module.register_multimedia_routes(app)
    assert app.dependency_overrides[get_multimedia_visual_candidate_runtime]() is runtime
