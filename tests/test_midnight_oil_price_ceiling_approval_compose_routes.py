"""Route tests for MO price-ceiling approval compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_price_ceiling_approval_compose_routes import (
    register_midnight_oil_price_ceiling_approval_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_price_ceiling_approval_compose_routes(app)
    return TestClient(app)


def test_recommend_route():
    c = _client()
    r = c.post(
        "/research/midnight-oil-price-ceiling-approval/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goals": [
                {"goal_id": "g1", "title": "Goal A"},
                {"goal_id": "g2", "title": "Goal B"},
            ],
            "usd_per_hour": 25,
            "price_ceiling_ack": False,
            "operator_ack": False,
            "stage": "recommend_only",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["recommend"]["recommended_ceiling_usd"] is not None


def test_approve_route():
    c = _client()
    r0 = c.post(
        "/research/midnight-oil-price-ceiling-approval/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goals": [{"goal_id": "g1", "title": "Goal A"}],
            "usd_per_hour": 20,
            "price_ceiling_ack": False,
            "operator_ack": False,
            "stage": "recommend_only",
        },
    )
    rec = r0.json()["recommend"]["recommended_ceiling_usd"]
    r = c.post(
        "/research/midnight-oil-price-ceiling-approval/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goals": [{"goal_id": "g1", "title": "Goal A"}],
            "usd_per_hour": 20,
            "approved_ceiling_usd": rec,
            "price_ceiling_ack": True,
            "operator_ack": True,
            "stage": "approve_ceiling",
        },
    )
    assert r.status_code == 200
    assert r.json()["ceiling_approved"] is True
    assert r.json()["charge_executed"] is False
