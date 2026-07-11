"""Hermetic tests for research workstation session compose routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.research_workstation_session_compose_routes import (
    register_research_workstation_session_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_research_workstation_session_compose_routes(app)
    return TestClient(app)


def test_compose_ok() -> None:
    r = _client().post(
        "/research/workstation-session/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
            "floating_instance_count": 1,
            "twin_bound": True,
            "source_family_count": 2,
            "quality_overall": 0.8,
            "would_exceed": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live_dispatch_authorized"] is False
    assert body["session_ready"] is True
    assert body["authority"] == "research_workstation_session_compose_advisory"


def test_cohesive_gate() -> None:
    r = _client().post(
        "/research/workstation-session/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
            "floating_instance_count": 2,
            "twin_bound": True,
            "source_family_count": 1,
            "quality_overall": 0.9,
            "would_exceed": False,
            "cohesive_pack_ready": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["session_ready"] is False
    assert r.json()["live_dispatch_authorized"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/workstation-session/compose",
        json={
            "session_id": "s",
            "parent_asset_id": "p",
            "floating_instance_count": 1,
            "twin_bound": True,
            "source_family_count": 1,
            "quality_overall": 0.9,
            "would_exceed": False,
            "live_dispatch_authorized": True,
        },
    )
    assert r.status_code == 422


def test_quality_null() -> None:
    r = _client().post(
        "/research/workstation-session/compose",
        json={
            "session_id": "s",
            "parent_asset_id": "p",
            "floating_instance_count": 1,
            "twin_bound": True,
            "source_family_count": 1,
            "quality_overall": None,
            "would_exceed": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["quality_ready"] is False
    assert r.json()["live_dispatch_authorized"] is False
