"""Route tests for MO time goals price entry compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_time_goals_price_entry_compose_routes import (
    register_midnight_oil_time_goals_price_entry_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_time_goals_price_entry_compose_routes(app)
    return TestClient(app)


def test_compose_entry():
    c = _client()
    r = c.post(
        "/research/midnight-oil-entry/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 120,
            "goals": [
                {"goal_id": "g1", "title": "Survey arxiv"},
                {"goal_id": "g2", "title": "Draft notes"},
            ],
            "usd_per_hour": 15,
            "approved_ceiling_usd": 40,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["entry_ready"] is True
    assert body["live_execution_authorized"] is False
