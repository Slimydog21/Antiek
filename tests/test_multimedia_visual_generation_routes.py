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
    multimedia_visual_authorization_runtime_from_environment,
)
from interfaces.research.api.multimedia_visual_generation_routes import (
    MultimediaVisualGenerationRuntime,
    get_multimedia_visual_generation_runtime,
    multimedia_visual_generation_router,
    multimedia_visual_generation_runtime_from_environment,
)
from tests.test_multimedia_visual_authorization import _ready, _request
from tests.test_multimedia_visual_authorization_routes import _config
from tests.test_multimedia_visual_generation import NOW, FakeKreaClient


def _client(runtime) -> TestClient:
    app = FastAPI()
    app.include_router(multimedia_visual_generation_router, prefix="/multimedia")
    app.dependency_overrides[authenticated_multimedia_operator] = lambda: "owner-1"
    app.dependency_overrides[get_multimedia_visual_generation_runtime] = lambda: runtime
    return TestClient(app)


def test_submit_and_poll_routes_expose_only_safe_execution_projection(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path)
    authority = multimedia_visual_authorization_runtime_from_environment(
        store=store, environ=_config(tmp_path / "runtime")
    )
    assert authority is not None
    authority.registry.authorize(
        ready.asset.asset_id, _request(ready), owner_id="owner-1", store=store,
        terms=authority.terms, now=NOW,
    )
    client = FakeKreaClient()
    api = _client(
        MultimediaVisualGenerationRuntime(
            authority, client, str(tmp_path / "execution.duckdb"), lambda: NOW
        )
    )
    submit = api.post(
        f"/multimedia/assets/{ready.asset.asset_id}/visual-generations",
        json={"request_id": "visual-request-1", "expected_revision_id": ready.asset.revision_id},
    )
    assert submit.status_code == 200, submit.text
    execution_id = submit.json()["execution_id"]
    poll = api.post(
        f"/multimedia/assets/{ready.asset.asset_id}/visual-generations/{execution_id}/poll",
        json={"expected_revision_id": ready.asset.revision_id},
    )
    assert poll.status_code == 200, poll.text
    assert poll.json()["candidate_count"] == 2
    assert set(poll.json()) == {
        "execution_id", "authorization_id", "provider_job_id", "status", "candidate_count"
    }
    lowered = poll.text.lower()
    assert "prompt" not in lowered and "https://" not in lowered and "secret" not in lowered


def test_generation_environment_requires_bound_krea_account(tmp_path: Path) -> None:
    store, _ = _ready(tmp_path / "store")
    assert multimedia_visual_generation_runtime_from_environment(store=store, environ={}) is None
    config = _config(tmp_path / "runtime")
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_TOKEN"] = "account-id:secret"
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_ACCOUNT_IDENTITY_DIGEST"] = hashlib.sha256(
        b"account-id"
    ).hexdigest()
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_DB_PATH"] = str(
        tmp_path / "runtime" / "execution.duckdb"
    )
    runtime = multimedia_visual_generation_runtime_from_environment(store=store, environ=config)
    assert runtime is not None and "secret" not in repr(runtime)
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_ACCOUNT_IDENTITY_DIGEST"] = "a" * 64
    try:
        multimedia_visual_generation_runtime_from_environment(store=store, environ=config)
    except RuntimeError as exc:
        assert "invalid" in str(exc)
    else:
        raise AssertionError("account drift must fail startup")


def test_multimedia_registration_installs_generation_runtime(tmp_path: Path, monkeypatch) -> None:
    store, _ = _ready(tmp_path / "store")
    config = _config(tmp_path / "runtime")
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_TOKEN"] = "account-id:secret"
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_ACCOUNT_IDENTITY_DIGEST"] = hashlib.sha256(
        b"account-id"
    ).hexdigest()
    config["ANTIEK_MULTIMEDIA_VISUAL_GENERATION_DB_PATH"] = str(
        tmp_path / "runtime" / "execution.duckdb"
    )
    runtime = multimedia_visual_generation_runtime_from_environment(store=store, environ=config)
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
    ):
        monkeypatch.setattr(multimedia_routes_module, name, lambda *, store: None)
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_tts_gateway_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_visual_generation_runtime_from_environment", lambda *, store: runtime,
    )
    app = FastAPI()
    multimedia_routes_module.register_multimedia_routes(app)
    assert app.dependency_overrides[get_multimedia_visual_generation_runtime]() is runtime
