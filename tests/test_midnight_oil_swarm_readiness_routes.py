"""Hermetic tests for Midnight Oil swarm readiness routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_swarm_readiness_routes import (
    register_midnight_oil_swarm_readiness_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_swarm_readiness_routes(app)
    return TestClient(app)


def test_evaluate_ready() -> None:
    r = _client().post(
        "/midnight-oil/swarm-readiness/evaluate",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goal_count": 2,
            "price_ceiling_usd": 5,
            "recommended_ceiling_usd": 4,
            "brief_dispatch_ready": True,
            "unattended_ack": True,
            "spend_consent": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unattended_ready"] is True
    assert body["live_execution_authorized"] is False


def test_null_ceiling() -> None:
    r = _client().post(
        "/midnight-oil/swarm-readiness/evaluate",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goal_count": 1,
            "price_ceiling_usd": None,
            "brief_dispatch_ready": True,
            "unattended_ack": True,
            "spend_consent": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["unattended_ready"] is False
    assert r.json()["live_execution_authorized"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/midnight-oil/swarm-readiness/evaluate",
        json={
            "operator_id": "op",
            "work_minutes": 10,
            "goal_count": 1,
            "price_ceiling_usd": 0,
            "brief_dispatch_ready": True,
            "unattended_ack": True,
            "spend_consent": False,
            "live_execution_authorized": True,
        },
    )
    assert r.status_code == 422


def test_strict_bool() -> None:
    r = _client().post(
        "/midnight-oil/swarm-readiness/evaluate",
        json={
            "operator_id": "op",
            "work_minutes": 10,
            "goal_count": 1,
            "price_ceiling_usd": 0,
            "brief_dispatch_ready": True,
            "unattended_ack": "true",
            "spend_consent": False,
        },
    )
    assert r.status_code == 422
