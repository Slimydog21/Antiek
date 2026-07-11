"""Hermetic tests for MO launch package routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_launch_package_compose_routes import (
    register_midnight_oil_launch_package_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_launch_package_compose_routes(app)
    return TestClient(app)


def test_compose_ok() -> None:
    r = _client().post(
        "/midnight-oil/launch-package/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goals": [
                {
                    "goal_id": "g1",
                    "statement": "Map arxiv",
                    "priority": 1,
                }
            ],
            "price_ceiling_usd": 15,
            "usd_per_hour": 10,
            "operator_approved": True,
            "unattended_ack": True,
            "spend_consent": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live_execution_authorized"] is False
    assert body["package_ready"] is True
    assert body["authority"] == "midnight_oil_launch_package_compose_advisory"


def test_not_ready_without_ack() -> None:
    r = _client().post(
        "/midnight-oil/launch-package/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goals": [
                {"goal_id": "g1", "statement": "x", "priority": 1}
            ],
            "price_ceiling_usd": 10,
            "recommended_ceiling_usd": 8,
            "operator_approved": True,
            "unattended_ack": False,
            "spend_consent": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["package_ready"] is False
    assert r.json()["live_execution_authorized"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/midnight-oil/launch-package/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goals": [
                {"goal_id": "g1", "statement": "x", "priority": 1}
            ],
            "price_ceiling_usd": 1,
            "operator_approved": False,
            "unattended_ack": False,
            "spend_consent": False,
            "live_execution_authorized": True,
        },
    )
    assert r.status_code == 422


def test_unknown_rate_null_recommend() -> None:
    r = _client().post(
        "/midnight-oil/launch-package/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goals": [
                {"goal_id": "g1", "statement": "x", "priority": 1}
            ],
            "price_ceiling_usd": 5,
            "usd_per_hour": None,
            "operator_approved": True,
            "unattended_ack": True,
            "spend_consent": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["recommend"]["recommended_ceiling_usd"] is None
    assert r.json()["live_execution_authorized"] is False
