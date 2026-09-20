"""Thought-partner HTTP selection through real owner authority and usage storage."""

from __future__ import annotations

import importlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from substrate.auth import mint_session_cookie
from substrate.byot_usage.ledger import ByotUsageLedger
from substrate.dispatch import (
    NormalizedUsage,
    RawProviderResponse,
    register_provider,
    reset_provider_registry,
)


class RecordingProvider:
    def __init__(self, name: str, fingerprint: str) -> None:
        self.name = name
        self._user_model_authority_fingerprint = fingerprint
        self.calls: list[str] = []
        self.fail = False

    def call(self, *, model: str, prompt: str, max_tokens: int, temperature: float) -> RawProviderResponse:
        self.calls.append(prompt)
        if self.fail:
            raise RuntimeError("private-provider-error-marker")
        return RawProviderResponse(
            text="Owner-selected reply", raw_usage={"input_tokens": 2, "output_tokens": 3},
            finish_reason="stop", latency_ms=1, request_id="synthetic-thought-partner",
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(input_tokens=2, output_tokens=3)


@pytest.fixture
def owner_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    api = importlib.import_module("interfaces.research.api.app")

    reset_provider_registry()
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "synthetic-thought-partner-secret-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "owner@example.test")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    monkeypatch.setenv("ANTIEK_BYOT_USAGE_DB", str(tmp_path / "usage.sqlite3"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setattr(api, "_retrieve_thought_partner_context", lambda *a: ([], "empty", None))
    monkeypatch.setattr(api, "account_memory_context", lambda *a: "")
    app = api.create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    client = TestClient(app)
    client.cookies.set("ANTIEK_SESSION", mint_session_cookie(user_id="owner-a", email="owner@example.test"))
    created = client.post("/settings/models/user", json={
        "provider_kind": "openai_compat", "provider_catalog_id": "deepseek",
        "model_id": "deepseek-chat", "display_name": "My DeepSeek",
        "api_key": "synthetic-owner-key-123456",
    })
    assert created.status_code == 201, created.text
    provider_id = created.json()["id"]
    provider = RecordingProvider(provider_id, app.state.user_model_registration_fingerprints[provider_id])
    register_provider(provider)
    # A real house-routed dispatch would hit this provider, making an unwanted
    # fallback observable rather than just expecting an error.
    house = RecordingProvider("zai", "house")
    register_provider(house)
    payload = {
        "prompt": "Compare these ideas", "system_context": "private-context",
        "history": [{"question": "Earlier question", "answer": "Earlier answer"}],
        "model_choice": {"authority": "user_model", "provider_id": provider_id, "model_id": "deepseek-chat"},
        "operation_id": "thought-turn-1",
    }
    yield client, payload, provider, house, ByotUsageLedger(tmp_path / "usage.sqlite3")
    client.close()
    reset_provider_registry()


def test_selected_model_settles_once_and_returns_safe_receipt(owner_client):
    client, payload, provider, house, ledger = owner_client
    first = client.post("/thought-partner", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["text"] == "Owner-selected reply"
    receipt = first.json()["model_receipt"]
    assert receipt == {
        "authority": "owner_byot", "requested_provider_id": provider.name,
        "requested_model_id": "deepseek-chat", "actual_provider_id": provider.name,
        "actual_model_id": "deepseek-chat", "authority_digest": receipt["authority_digest"],
    }
    assert len(receipt["authority_digest"]) == 64
    assert "synthetic-owner-key" not in first.text
    assert "Earlier answer" in provider.calls[0]
    assert "private-context" in provider.calls[0]
    again = client.post("/thought-partner", json=payload)
    assert again.status_code == 200, again.text
    assert again.json() == first.json()
    assert len(provider.calls) == 1 and house.calls == []
    assert ledger.key_usage(provider.name, "owner-a").used_cents == 1
    assert ledger.operation("owner-a", "thought-turn-1").state == "settled"


def test_default_route_preserves_response_shape_without_owner_receipt(owner_client):
    client, payload, provider, house, _ = owner_client
    request = {key: value for key, value in payload.items() if key not in {"model_choice", "operation_id"}}
    response = client.post("/thought-partner", json=request)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {
        "text", "shape", "library_retrieval_status", "library_retrieval_degraded_reason",
    }
    assert provider.calls == [] and len(house.calls) == 1


def test_concurrent_duplicate_turn_cannot_spend_twice(owner_client, monkeypatch):
    client, payload, provider, house, ledger = owner_client
    entered = threading.Event()
    release = threading.Event()
    original = provider.call

    def held_call(**kwargs):
        entered.set()
        assert release.wait(10), "test did not release provider"
        return original(**kwargs)

    monkeypatch.setattr(provider, "call", held_call)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(client.post, "/thought-partner", json=payload)
        try:
            assert entered.wait(10), "provider was not called"
            duplicate = client.post("/thought-partner", json=payload)
            assert duplicate.status_code == 503, duplicate.text
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200
    assert len(provider.calls) == 1 and house.calls == []
    assert ledger.key_usage(provider.name, "owner-a").used_cents == 1


@pytest.mark.parametrize("change", [
    {"model_choice": None}, {"operation_id": None}, {"operation_id": 4},
    {"operation_id": " "}, {"operation_id": "x" * 129},
    {"model_choice": {"api_key": "must-not-echo"}},
])
def test_invalid_selection_refuses_before_retrieval_or_spend(owner_client, monkeypatch, change):
    api = importlib.import_module("interfaces.research.api.app")

    client, payload, provider, house, ledger = owner_client
    monkeypatch.setattr(api, "_retrieve_thought_partner_context", lambda *a: pytest.fail("invalid choice reached retrieval"))
    response = client.post("/thought-partner", json=payload | change)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "model_selection_invalid"
    assert "must-not-echo" not in response.text
    assert provider.calls == [] and house.calls == []
    assert ledger.operation("owner-a", "thought-turn-1") is None


@pytest.mark.parametrize("field,value", [
    ("prompt", "Compare other ideas"),
    ("system_context", "changed-context"),
    ("history", [{"question": "Earlier question", "answer": "Changed answer"}]),
    ("investigation_id", "different-investigation"),
])
def test_operation_cannot_replay_different_content(owner_client, field, value):
    client, payload, provider, house, _ = owner_client
    assert client.post("/thought-partner", json=payload).status_code == 200
    response = client.post("/thought-partner", json=payload | {field: value})
    assert response.status_code == 503
    assert response.json()["detail"] == "owner_model_unavailable"
    assert len(provider.calls) == 1 and house.calls == []


def test_other_owner_cannot_use_selected_model(owner_client):
    client, payload, provider, house, ledger = owner_client
    client.cookies.set("ANTIEK_SESSION", mint_session_cookie(user_id="owner-b", email="owner@example.test"))
    response = client.post("/thought-partner", json=payload)
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "owner_model_unavailable"
    assert provider.calls == [] and house.calls == []
    assert ledger.operation("owner-b", "thought-turn-1") is None


def test_spend_cap_refuses_before_provider_io(owner_client):
    client, payload, provider, house, ledger = owner_client
    ledger.set_limit(provider.name, "owner-a", 0)
    response = client.post("/thought-partner", json=payload)
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "owner_model_unavailable"
    assert provider.calls == [] and house.calls == []
    assert ledger.key_usage(provider.name, "owner-a").used_cents == 0


def test_revoked_key_cannot_start_another_turn(owner_client):
    client, payload, provider, house, _ = owner_client
    assert client.delete(f"/settings/models/user/{provider.name}").status_code == 200
    response = client.post("/thought-partner", json=payload)
    assert response.status_code == 503, response.text
    assert provider.calls == [] and house.calls == []


def test_unknown_provider_outcome_never_uses_house_or_resends(owner_client):
    client, payload, provider, house, ledger = owner_client
    provider.fail = True
    first = client.post("/thought-partner", json=payload)
    assert first.status_code == 503, first.text
    assert first.json()["detail"] == "owner_model_outcome_unknown"
    assert "private-provider-error-marker" not in first.text
    calls = len(provider.calls)
    assert calls > 0
    again = client.post("/thought-partner", json=payload)
    assert again.status_code == 503
    assert len(provider.calls) == calls and house.calls == []
    assert ledger.operation("owner-a", "thought-turn-1").state == "unknown"
