"""Hermetic tests for research launch readiness routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.research_launch_readiness_routes import (
    register_research_launch_readiness_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_research_launch_readiness_routes(app)
    return TestClient(app)


def test_evaluate_ready() -> None:
    r = _client().post(
        "/research/launch-readiness/evaluate",
        json={
            "session_id": "sess-1",
            "source_family_count": 2,
            "quality_overall": 0.8,
            "quality_floor": 0.5,
            "would_exceed": False,
            "operator_override": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["launch_ready"] is True
    assert body["live_dispatch_authorized"] is False


def test_null_exceed() -> None:
    r = _client().post(
        "/research/launch-readiness/evaluate",
        json={
            "session_id": "sess-1",
            "source_family_count": 1,
            "quality_overall": None,
            "would_exceed": None,
        },
    )
    assert r.status_code == 200
    assert r.json()["launch_ready"] is False
    assert r.json()["live_dispatch_authorized"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/launch-readiness/evaluate",
        json={
            "session_id": "s",
            "source_family_count": 1,
            "would_exceed": False,
            "live_dispatch_authorized": True,
        },
    )
    assert r.status_code == 422


def test_strict_bool() -> None:
    r = _client().post(
        "/research/launch-readiness/evaluate",
        json={
            "session_id": "s",
            "source_family_count": 1,
            "would_exceed": False,
            "operator_override": "true",
        },
    )
    assert r.status_code == 422
