"""Route tests for MO entry → swarm readiness compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_entry_to_swarm_readiness_compose_routes import (
    register_midnight_oil_entry_to_swarm_readiness_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_entry_to_swarm_readiness_compose_routes(app)
    return TestClient(app)


def test_compose_ok():
    c = _client()
    r = c.post(
        "/research/midnight-oil-entry-readiness/compose",
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
            "brief_dispatch_ready": True,
            "unattended_ack": True,
            "spend_consent": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["package_ready"] is True
    assert body["live_execution_authorized"] is False


def test_compose_unattended_false():
    c = _client()
    r = c.post(
        "/research/midnight-oil-entry-readiness/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goals": [{"goal_id": "g1", "title": "T"}],
            "usd_per_hour": 10,
            "approved_ceiling_usd": 20,
            "operator_ack": True,
            "brief_dispatch_ready": True,
            "unattended_ack": False,
            "spend_consent": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["package_ready"] is False
    assert r.json()["live_execution_authorized"] is False
