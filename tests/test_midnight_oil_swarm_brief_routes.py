"""Hermetic tests for MO swarm brief routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_swarm_brief_routes import (
    register_midnight_oil_swarm_brief_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_swarm_brief_routes(app)
    return TestClient(app)


def test_build_ok() -> None:
    r = _client().post(
        "/midnight-oil/swarm-brief/build",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goals": [
                {"goal_id": "g1", "statement": "Map arxiv", "priority": 2},
                {"goal_id": "g2", "statement": "Substack", "priority": 1},
            ],
            "price_ceiling_usd": 5,
            "operator_approved": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live_execution_authorized"] is False
    assert body["dispatch_ready"] is True
    assert len(body["lanes"]) == 2


def test_null_ceiling() -> None:
    r = _client().post(
        "/midnight-oil/swarm-brief/build",
        json={
            "operator_id": "op",
            "work_minutes": 30,
            "goals": [{"goal_id": "g1", "statement": "x", "priority": 1}],
            "price_ceiling_usd": None,
            "operator_approved": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["dispatch_ready"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/midnight-oil/swarm-brief/build",
        json={
            "operator_id": "op",
            "work_minutes": 30,
            "goals": [{"goal_id": "g1", "statement": "x", "priority": 1}],
            "price_ceiling_usd": 1,
            "operator_approved": True,
            "live_execution_authorized": True,
        },
    )
    assert r.status_code == 422


def test_strict_bool() -> None:
    r = _client().post(
        "/midnight-oil/swarm-brief/build",
        json={
            "operator_id": "op",
            "work_minutes": 30,
            "goals": [{"goal_id": "g1", "statement": "x", "priority": 1}],
            "price_ceiling_usd": 1,
            "operator_approved": "true",
        },
    )
    assert r.status_code == 422
