"""Hermetic tests for unattended brief routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_unattended_routes import (
    register_midnight_oil_unattended_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_unattended_routes(app)
    return TestClient(app)


def test_brief_ok() -> None:
    r = _client().post(
        "/midnight-oil/unattended/brief",
        json={
            "duration_minutes": 90,
            "goals": ["deep research on X"],
            "approved_ceiling_cents": 250,
            "recommended_ceiling_cents": 200,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live_execution_authorized"] is False
    assert body["authority"] == "operator_brief_only"
    assert body["duration_minutes"] == 90
    assert body["approved_ceiling_cents"] == 250


def test_brief_empty_goals_400() -> None:
    r = _client().post(
        "/midnight-oil/unattended/brief",
        json={
            "duration_minutes": 90,
            "goals": [],
            "approved_ceiling_cents": 100,
        },
    )
    assert r.status_code in (400, 422)


def test_brief_bad_duration_400() -> None:
    r = _client().post(
        "/midnight-oil/unattended/brief",
        json={
            "duration_minutes": 0,
            "goals": ["x"],
            "approved_ceiling_cents": 100,
        },
    )
    assert r.status_code == 400
    assert "duration_minutes" in r.json()["detail"]


def test_never_returns_live_authorized_true() -> None:
    r = _client().post(
        "/midnight-oil/unattended/brief",
        json={
            "duration_minutes": 30,
            "goals": ["y"],
            "approved_ceiling_cents": 0,
        },
    )
    assert r.status_code == 200
    assert r.json()["live_execution_authorized"] is False
