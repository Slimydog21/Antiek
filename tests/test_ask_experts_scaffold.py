"""Endpoint truth tests for ask-experts scaffold disclosure."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from substrate.dispatch import reset_provider_registry


@pytest.fixture(autouse=True)
def _isolate_provider_registry():
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ask-experts-api-test-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    for key in (
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "HERMES_API_KEY",
        "OPENROUTER_API_KEY",
        "XIAOMI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def test_ask_experts_marks_scaffold_response(client):
    response = client.post(
        "/cross-graph/ask-experts",
        json={"topic_query": "oral history", "limit": 3},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scaffold"] is True
