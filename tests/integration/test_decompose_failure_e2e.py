"""DRW decompose failure — live route through dispatch (SPR-04)."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import interfaces.research.api.cascade_routes as cr
from interfaces.research.api.cascade_routes import cascade_router
from substrate.dispatch.base import ProviderError
from substrate.dispatch.providers import register_default_providers
from substrate.dispatch.router import reset_provider_registry

# Must match substrate.dispatch.providers.bootstrap env gates (see test_dispatch_bootstrap).
_PROVIDER_ENV_KEYS = (
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "XIAOMI_API_KEY",
    "HERMES_API_KEY",
    "OPENAI_API_KEY",
    "ANTIEK_TILERT_API_KEY",
)


def _isolate_empty_provider_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic empty registry — runner env keys must not register live providers."""
    reset_provider_registry()
    for key in _PROVIDER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    register_default_providers(quiet=True)


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        return [0.1] * self.dimension


@pytest.fixture
def cascade_client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="decompose-e2e-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    app = FastAPI()
    app.include_router(cascade_router)
    return TestClient(app)


def test_empty_registry_yields_provider_unconfigured(cascade_client, monkeypatch):
    """Genuine _decompose → dispatch path with no provider keys in env."""
    _isolate_empty_provider_registry(monkeypatch)
    r = cascade_client.post(
        "/research/plans",
        json={"problem": "What drives critical mineral supply chains?"},
    )
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "provider_unconfigured"
    assert "ProviderError" not in r.text
    assert detail["retryable"] is False


def test_upstream_provider_error_envelope(cascade_client, monkeypatch):
    def _upstream(problem: str, max_depth: int):
        raise ProviderError(
            "upstream failed",
            provider="openrouter",
            model="test-model",
            latency_ms=10,
        )

    monkeypatch.setattr(cr, "_decompose", _upstream)
    r = cascade_client.post("/research/plans", json={"problem": "P"})
    assert r.status_code == 502, r.text
    assert r.json()["detail"]["code"] == "provider_upstream_error"


def test_timeout_envelope(cascade_client, monkeypatch):

    def _timeout(problem: str, max_depth: int):
        raise TimeoutError()

    monkeypatch.setattr(cr, "_decompose", _timeout)
    r = cascade_client.post("/research/plans", json={"problem": "P"})
    assert r.status_code == 504, r.text
    assert r.json()["detail"]["code"] == "timeout"