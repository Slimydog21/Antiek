"""Hermetic tests for unattended launch gate routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_launch_gate_routes import (
    register_midnight_oil_launch_gate_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_launch_gate_routes(app)
    return TestClient(app)


def test_gate_ready() -> None:
    r = _client().post(
        "/midnight-oil/unattended/launch-gate",
        json={
            "operator_approved": True,
            "consent_receipt_id": "rcpt-1",
            "duration_minutes": 90,
            "goals": ["map X"],
            "approved_ceiling_cents": 200,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dispatch_ready"] is True
    assert body["live_execution_authorized"] is False


def test_gate_not_ready_without_receipt() -> None:
    r = _client().post(
        "/midnight-oil/unattended/launch-gate",
        json={
            "operator_approved": True,
            "duration_minutes": 90,
            "goals": ["map X"],
            "approved_ceiling_cents": 200,
        },
    )
    assert r.status_code == 200
    assert r.json()["dispatch_ready"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/midnight-oil/unattended/launch-gate",
        json={
            "operator_approved": True,
            "duration_minutes": 30,
            "goals": ["y"],
            "approved_ceiling_cents": 0,
            "live_execution_authorized": True,
        },
    )
    assert r.status_code == 422


def test_coerced_approved_rejected() -> None:
    r = _client().post(
        "/midnight-oil/unattended/launch-gate",
        json={
            "operator_approved": "true",
            "duration_minutes": 30,
            "goals": ["y"],
            "approved_ceiling_cents": 0,
        },
    )
    assert r.status_code == 422
