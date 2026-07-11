"""Route tests for deep research quality budget gate compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.deep_research_quality_budget_gate_compose_routes import (
    register_deep_research_quality_budget_gate_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_deep_research_quality_budget_gate_compose_routes(app)
    return TestClient(app)


def test_compose_gate():
    c = _client()
    r = c.post(
        "/research/dr-quality-budget-gate/compose",
        json={
            "session_id": "dr-1",
            "quality_overall": 0.82,
            "quality_floor": 0.5,
            "would_exceed": False,
            "citation_pack_ready": True,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["gate_ready"] is True
    assert body["live_dispatch_authorized"] is False
