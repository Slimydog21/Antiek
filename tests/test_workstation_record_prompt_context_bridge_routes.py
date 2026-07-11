"""Hermetic tests for record prompt context bridge routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.workstation_record_prompt_context_bridge_routes import (
    register_workstation_record_prompt_context_bridge_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_workstation_record_prompt_context_bridge_routes(app)
    return TestClient(app)


def test_bridge_ok() -> None:
    r = _client().post(
        "/research/record-prompt-context/bridge",
        json={
            "session_id": "sess-1",
            "user_prompt": "What are open questions?",
            "items": [
                {
                    "record_id": "r1",
                    "kind": "insight",
                    "text": "scaling holds",
                    "weight": 0.9,
                }
            ],
            "placement": "prefix",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["prompts_injected"] is False
    assert body["record_persisted"] is False
    assert body["bridge_ready"] is True
    assert "scaling holds" in body["proposed_prompt"]
    assert body["authority"] == "workstation_record_prompt_context_bridge_advisory"


def test_empty_items_ok() -> None:
    r = _client().post(
        "/research/record-prompt-context/bridge",
        json={
            "session_id": "s",
            "user_prompt": "Hello",
            "items": [],
        },
    )
    assert r.status_code == 200
    assert r.json()["proposed_prompt"] == "Hello"
    assert r.json()["prompts_injected"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/record-prompt-context/bridge",
        json={
            "session_id": "s",
            "user_prompt": "x",
            "items": [],
            "prompts_injected": True,
        },
    )
    assert r.status_code == 422
