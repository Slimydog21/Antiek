"""Route tests for Midnight Oil unattended recap compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_unattended_recap_compose_routes import (
    register_midnight_oil_unattended_recap_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_unattended_recap_compose_routes(app)
    return TestClient(app)


def test_compose_recap():
    c = _client()
    r = c.post(
        "/research/midnight-oil-recap/compose",
        json={
            "run_id": "mo-1",
            "operator_id": "op-1",
            "work_minutes_planned": 120,
            "work_minutes_actual": 110,
            "price_ceiling_usd": 25,
            "spend_usd": 18.5,
            "operator_ack": True,
            "artifact_ids": ["art-1"],
            "goals": [
                {"goal_id": "g1", "title": "Survey", "status": "done"},
                {"goal_id": "g2", "title": "Draft", "status": "blocked"},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["recap_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["store_mutated"] is False
    assert body["within_ceiling"] is True
