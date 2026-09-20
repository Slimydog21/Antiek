from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes as multimedia_routes_module
from interfaces.research.api.multimedia_reconciliation_routes import (
    authenticated_multimedia_operator,
)
from interfaces.research.api.multimedia_visual_authorization_routes import (
    MultimediaVisualAuthorizationRuntime,
    get_multimedia_visual_authorization_runtime,
    multimedia_visual_authorization_router,
    multimedia_visual_authorization_runtime_from_environment,
)
from substrate.multimedia.visual_authorization import (
    VisualAuthorizationRegistry,
    VisualAuthorizationTerms,
)
from tests.test_multimedia_visual_authorization import KEY, _ready, _request


def _client(runtime, *, owner: str = "owner-1") -> TestClient:
    app = FastAPI()
    app.include_router(multimedia_visual_authorization_router, prefix="/multimedia")
    app.dependency_overrides[authenticated_multimedia_operator] = lambda: owner
    app.dependency_overrides[get_multimedia_visual_authorization_runtime] = lambda: runtime
    return TestClient(app)


def test_route_returns_safe_exact_authority_and_replays(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path)
    runtime = MultimediaVisualAuthorizationRuntime(
        store=store,
        registry=VisualAuthorizationRegistry(db_path=str(tmp_path / "auth.duckdb"), signing_key=KEY),
        terms=VisualAuthorizationTerms("recovery-1", "b" * 64, 500_000, 600),
        db_path=str(tmp_path / "auth.duckdb"),
        signing_key=KEY,
    )
    body = _request(ready).__dict__
    route = f"/multimedia/assets/{ready.asset.asset_id}/visual-authorizations"
    first = _client(runtime).post(route, json=body)
    second = _client(runtime).post(route, json=body)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    payload = first.json()
    assert payload["authorization"]["provider"] == "krea"
    assert payload["quote"]["quote_id"] == payload["authorization"]["quote_id"]
    assert set(payload) == {
        "chapter_id", "scene_id", "width", "height", "seed",
        "request_body_digest", "quote", "authorization",
    }
    serialized = first.text.lower()
    assert "signing_key" not in serialized and "api_key" not in serialized and "/private/" not in serialized


def _config(root: Path) -> dict[str, str]:
    root.mkdir(mode=0o700)
    prefix = "ANTIEK_MULTIMEDIA_VISUAL_AUTH_"
    return {
        prefix + "ENABLED": "true", prefix + "DB_PATH": str(root / "auth.duckdb"),
        prefix + "SIGNING_KEY_HEX": KEY.hex(), prefix + "RECOVERY_AUTHORITY_ID": "recovery-1",
        prefix + "RECOVERY_VERIFICATION_KEY_DIGEST": "b" * 64,
        prefix + "MAXIMUM_CEILING_MICRODOLLARS": "500000",
        prefix + "QUOTE_TTL_SECONDS": "600",
    }


def test_environment_runtime_is_all_or_nothing(tmp_path: Path) -> None:
    store, _ = _ready(tmp_path / "store")
    assert multimedia_visual_authorization_runtime_from_environment(store=store, environ={}) is None
    runtime = multimedia_visual_authorization_runtime_from_environment(
        store=store, environ=_config(tmp_path / "runtime")
    )
    assert runtime is not None and "visual-authorization-key" not in repr(runtime)
    partial = _config(tmp_path / "partial")
    partial.pop("ANTIEK_MULTIMEDIA_VISUAL_AUTH_QUOTE_TTL_SECONDS")
    with pytest.raises(RuntimeError, match="incomplete"):
        multimedia_visual_authorization_runtime_from_environment(store=store, environ=partial)


def test_multimedia_registration_installs_visual_authority(tmp_path: Path, monkeypatch) -> None:
    store, _ = _ready(tmp_path / "store")
    runtime = multimedia_visual_authorization_runtime_from_environment(
        store=store, environ=_config(tmp_path / "runtime")
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
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_narration_authorization_runtime_from_environment", lambda *, store: None,
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_reviewed_visual_runtime_from_environment", lambda *, store: None,
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_production_worker_runtime_from_environment", lambda *, store: None,
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_tts_gateway_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_visual_authorization_runtime_from_environment", lambda *, store: runtime,
    )
    app = FastAPI()
    multimedia_routes_module.register_multimedia_routes(app)
    assert app.dependency_overrides[get_multimedia_visual_authorization_runtime]() is runtime
