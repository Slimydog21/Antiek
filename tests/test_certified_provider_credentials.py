"""Operator-scoped account onboarding for certified dispatch credentials."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.settings_budget import register_settings_budget_routes
from runtime.byok.store import list_credentials, load_credential
from substrate.dispatch.router import get_provider, reset_provider_registry

_SECRET = "sk-certified-deepseek-000111222333"


def _app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _identity(request: Request, call_next):
        request.state.user_id = request.headers.get("x-test-user", "operator-1")
        return await call_next(request)

    register_settings_budget_routes(app)
    assert any(
        getattr(route, "path", None) == "/settings/providers/certified" for route in app.routes
    )
    app.state.registered_providers = set()
    return app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ANTIEK_OPERATOR_USER_ID", "operator-1")
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    for name in (
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "XIAOMI_API_KEY",
        "HERMES_API_KEY",
        "Z_AI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_provider_registry()
    with TestClient(_app()) as test_client:
        yield test_client
    reset_provider_registry()


def test_defaults_closed_without_configured_operator(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTIEK_OPERATOR_USER_ID")
    response = client.get("/settings/providers/certified")
    assert response.status_code == 403
    assert response.json() == {"detail": "certified provider credential access denied"}


def test_non_operator_cannot_list_or_write(client: TestClient) -> None:
    headers = {"x-test-user": "friend-2"}
    assert client.get("/settings/providers/certified", headers=headers).status_code == 403
    response = client.put(
        "/settings/providers/certified/deepseek",
        headers=headers,
        json={"api_key": _SECRET},
    )
    assert response.status_code == 403
    assert _SECRET not in response.text
    assert list_credentials() == []


def test_put_stores_exact_bootstrap_namespace_and_activates_provider(
    client: TestClient,
) -> None:
    response = client.put(
        "/settings/providers/certified/deepseek",
        json={"api_key": _SECRET},
    )
    assert response.status_code == 201
    assert response.json() == {
        "provider_handle": "deepseek",
        "key_present": True,
        "registered_providers": ["deepseek"],
        "source": "encrypted_byok_store",
    }
    assert _SECRET not in response.text
    metadata = list_credentials()
    assert len(metadata) == 1
    assert metadata[0].pipeline_kind == "provider:deepseek"
    assert metadata[0].owner_user_id == "operator-1"
    assert load_credential(metadata[0].cred_id).reveal() == _SECRET
    assert _SECRET.encode() not in Path(os.environ["ANTIEK_BYOK_ARTIFACT"]).read_bytes()
    assert get_provider("deepseek")._resolve_api_key() == _SECRET  # noqa: SLF001
    assert "deepseek" in client.app.state.registered_providers


def test_list_is_metadata_only_and_reports_byot_only(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_BYOT_ONLY", "1")
    assert (
        client.put(
            "/settings/providers/certified/deepseek",
            json={"api_key": _SECRET},
        ).status_code
        == 201
    )
    response = client.get("/settings/providers/certified")
    assert response.status_code == 200
    assert response.json() == {
        "providers": [
            {"provider_handle": handle, "key_present": handle == "deepseek"}
            for handle in ("anthropic", "deepseek", "hermes", "openrouter", "xiaomi", "zai")
        ],
        "byot_only": True,
    }
    assert _SECRET not in response.text


def test_replacement_leaves_one_new_authoritative_ciphertext(client: TestClient) -> None:
    first = "sk-certified-first-000111222"
    second = "sk-certified-second-333444555"
    assert (
        client.put(
            "/settings/providers/certified/deepseek",
            json={"api_key": first},
        ).status_code
        == 201
    )
    assert (
        client.put(
            "/settings/providers/certified/deepseek",
            json={"api_key": second},
        ).status_code
        == 201
    )
    metadata = [m for m in list_credentials() if m.pipeline_kind == "provider:deepseek"]
    assert len(metadata) == 1
    assert load_credential(metadata[0].cred_id).reveal() == second
    assert get_provider("deepseek")._resolve_api_key() == second  # noqa: SLF001


def test_shared_zai_key_activates_direct_and_reasoning_policies(
    client: TestClient,
) -> None:
    response = client.put("/settings/providers/certified/zai", json={"api_key": _SECRET})
    assert response.status_code == 201
    assert response.json()["registered_providers"] == ["zai", "zai_reasoning"]
    assert get_provider("zai")._resolve_api_key() == _SECRET  # noqa: SLF001
    assert get_provider("zai_reasoning")._resolve_api_key() == _SECRET  # noqa: SLF001


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"api_key": "short"},
        {"api_key": _SECRET, "extra": "no"},
        {"api_key": 123},
        {"api_key": "x" * 513},
    ],
)
def test_invalid_body_is_value_free(client: TestClient, body: object) -> None:
    response = client.put("/settings/providers/certified/deepseek", json=body)
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid certified provider credential request"}
    assert _SECRET not in response.text


def test_unknown_handle_is_value_free_and_does_not_store(client: TestClient) -> None:
    response = client.put(
        "/settings/providers/certified/not-a-provider",
        json={"api_key": _SECRET},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "unknown certified provider"}
    assert _SECRET not in response.text
    assert list_credentials() == []
