from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.byok.store import list_credentials
from substrate.auth.magic_link import mint_session_cookie
from substrate.dispatch.router import reset_provider_registry

_BODY = {
    "provider_kind": "openai_compat",
    "provider_catalog_id": "deepseek",
    "model_id": "deepseek-chat",
    "display_name": "My DeepSeek",
    "api_key": "sk-test-only-user-key-abcdefghijklmnopqrstuvwxyz",
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "test-only-auth-secret-at-least-32-bytes")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "user-a@example.test,user-b@example.test")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    reset_provider_registry()
    app = create_app(register_wrestling=False, register_providers=False)
    with TestClient(app) as test_client:
        yield test_client
    reset_provider_registry()


def _cookie(user_id: str) -> dict[str, str]:
    value = mint_session_cookie(user_id=user_id, email=f"{user_id}@example.test")
    return {"ANTIEK_SESSION": value}


def test_model_onboarding_catalog_requires_settings_auth(client: TestClient) -> None:
    unauthenticated = client.get("/settings/models/catalog")
    assert unauthenticated.status_code == 401

    authenticated = client.get("/settings/models/catalog", cookies=_cookie("user-a"))
    assert authenticated.status_code == 200
    assert authenticated.json()["count"] > 0


def test_two_sessions_cannot_list_resolve_or_delete_each_others_models(
    client: TestClient,
    tmp_path: Path,
) -> None:
    cookies_a = _cookie("user-a")
    cookies_b = _cookie("user-b")

    created_a = client.post("/settings/models/user", json=_BODY, cookies=cookies_a)
    created_b = client.post(
        "/settings/models/user",
        json={**_BODY, "api_key": "sk-test-only-second-key-abcdefghijklmnopqrstuvwxyz"},
        cookies=cookies_b,
    )
    assert created_a.status_code == created_b.status_code == 201
    id_a = created_a.json()["id"]
    id_b = created_b.json()["id"]
    assert id_a != id_b
    assert id_a == f"user-{hashlib.blake2b(b'user-a').hexdigest()[:8]}-my-deepseek"
    assert id_b == f"user-{hashlib.blake2b(b'user-b').hexdigest()[:8]}-my-deepseek"

    assert [
        row["id"] for row in client.get("/settings/models/user", cookies=cookies_a).json()["models"]
    ] == [id_a]
    assert [
        row["id"] for row in client.get("/settings/models/user", cookies=cookies_b).json()["models"]
    ] == [id_b]
    visible_a = {
        row["provider_id"]
        for row in client.get("/settings/models", cookies=cookies_a).json()["models"]
        if row["provider_id"].startswith("user-")
    }
    visible_b = {
        row["provider_id"]
        for row in client.get("/settings/models", cookies=cookies_b).json()["models"]
        if row["provider_id"].startswith("user-")
    }
    assert visible_a == {id_a}
    assert visible_b == {id_b}

    choice_a = {
        "authority": "user_model",
        "provider_id": id_a,
        "model_id": "deepseek-chat",
    }
    assert (
        client.post("/settings/models/user/resolve", json=choice_a, cookies=cookies_b).status_code
        == 409
    )
    assert client.delete(f"/settings/models/user/{id_a}", cookies=cookies_b).status_code == 404

    registry = json.loads((tmp_path / "models.json").read_text(encoding="utf-8"))
    cred_a = registry[id_a]["cred_ref"]
    metadata = {item.cred_id: item for item in list_credentials()}
    assert metadata[cred_a].owner_user_id == "user-a"
    assert {item.owner_user_id for item in metadata.values()} == {"user-a", "user-b"}

    removed = client.delete(f"/settings/models/user/{id_a}", cookies=cookies_a)
    assert removed.status_code == 200
    assert cred_a not in {item.cred_id for item in list_credentials()}
    assert client.get("/settings/models/user", cookies=cookies_b).json()["count"] == 1
