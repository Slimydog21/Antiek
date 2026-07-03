"""Endpoint truth tests for the trajectory collection route."""

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
    tmpdir = tempfile.mkdtemp(prefix="trajectory-collection-api-test-")
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


def _post_dispatch(client: TestClient, investigation_id: str, prompt_hash: str) -> None:
    payload = {
        "action_type": "dispatch.call",
        "provider": "p",
        "model": "m",
        "tier": "flash",
        "target_role": "decomposer",
        "input_tokens": 1,
        "output_tokens": 1,
        "cost_usd": 0.0,
        "latency_ms": 1,
        "prompt_hash": prompt_hash,
    }
    response = client.post(
        "/events/typed",
        json={"investigation_id": investigation_id, "payload": payload},
    )
    assert response.status_code == 201, response.text


def test_trajectory_collection_recent_first_across_investigations(client):
    _post_dispatch(client, "inv-old", "old")
    _post_dispatch(client, "inv-mid", "mid")
    _post_dispatch(client, "inv-new", "new")

    response = client.get("/trajectory?limit=2")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"count", "events"}
    assert body["count"] == 2
    assert [e["payload"]["prompt_hash"] for e in body["events"]] == ["new", "mid"]
    assert [e["investigation_id"] for e in body["events"]] == ["inv-new", "inv-mid"]
