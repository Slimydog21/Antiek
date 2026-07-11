"""Route tests for workstation session insight record compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.workstation_session_insight_record_compose_routes import (
    register_workstation_session_insight_record_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_workstation_session_insight_record_compose_routes(app)
    return TestClient(app)


def test_compose_records():
    c = _client()
    r = c.post(
        "/research/session-insight-record/compose",
        json={
            "session_id": "ws-1",
            "parent_asset_id": "asset-1",
            "operator_ack": True,
            "mark_for_prompt_context": True,
            "records": [
                {
                    "record_id": "r1",
                    "kind": "insight",
                    "body": "claim holds",
                },
                {
                    "record_id": "r2",
                    "kind": "question",
                    "body": "sample size?",
                },
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["record_ready"] is True
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["store_mutated"] is False
