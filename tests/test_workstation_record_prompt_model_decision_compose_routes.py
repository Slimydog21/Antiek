"""Route tests for workstation record→prompt→model decision compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.workstation_record_prompt_model_decision_compose_routes import (
    register_workstation_record_prompt_model_decision_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_workstation_record_prompt_model_decision_compose_routes(app)
    return TestClient(app)


def test_compose_ok():
    c = _client()
    r = c.post(
        "/research/workstation-record-prompt-model-decision/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "paper-1",
            "records": [
                {
                    "record_id": "r1",
                    "kind": "insight",
                    "body": "scaling holds under noise",
                },
                {
                    "record_id": "r2",
                    "kind": "question",
                    "body": "What is the failure mode?",
                },
            ],
            "user_prompt": "Summarize open questions",
            "selected_model_id": "gpt-5",
            "models": [
                {
                    "model_id": "gpt-5",
                    "tier": "frontier",
                    "projected_cost_usd_high": 2,
                },
                {"model_id": "composer-2.5", "projected_cost_usd_high": 0.5},
            ],
            "daily_cap_usd": 100,
            "spent_usd": 40,
            "projected_cost_usd_high": 2,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["usage_percent"] == 40.0
    assert body["would_exceed"] is False
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["live_meter_read"] is False


def test_compose_ack_false():
    c = _client()
    r = c.post(
        "/research/workstation-record-prompt-model-decision/compose",
        json={
            "session_id": "s",
            "parent_asset_id": "p",
            "records": [
                {"record_id": "r1", "kind": "insight", "body": "x"},
            ],
            "user_prompt": "Go",
            "selected_model_id": "gpt-5",
            "models": [{"model_id": "gpt-5"}],
            "daily_cap_usd": 100,
            "spent_usd": 10,
            "operator_ack": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["pack_ready"] is False
    assert r.json()["prompts_injected"] is False
