"""Route tests for midnight oil recap → write twin collective compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_recap_write_mode_twin_collective_compose_routes import (
    register_midnight_oil_recap_write_mode_twin_collective_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_recap_write_mode_twin_collective_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/midnight-oil-recap-write-mode-twin-collective/compose",
        json={
            "run_id": "run-1",
            "operator_id": "op-1",
            "work_minutes_planned": 120,
            "work_minutes_actual": 115,
            "goals": [
                {
                    "goal_id": "g1",
                    "title": "Survey arxiv scaling laws",
                    "status": "done",
                    "notes": "Found key papers",
                },
                {
                    "goal_id": "g2",
                    "title": "Synthesize substack claims",
                    "status": "done",
                    "notes": "Draft synthesis",
                },
                {
                    "goal_id": "g3",
                    "title": "Open counter-claims",
                    "status": "pending",
                },
            ],
            "price_ceiling_usd": 40,
            "spend_usd": 28,
            "artifact_ids": ["art-1"],
            "operator_ack": True,
            "session_id": "sess-1",
            "draft_id": "draft-1",
            "parent_asset_id": "asset-1",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["draft_written"] is False
    assert body["analysis_written"] is False
    assert body["merge_executed"] is False
    assert body["store_mutated"] is False
    assert body["authority"] == (
        "midnight_oil_recap_write_mode_twin_collective_compose_advisory"
    )


def test_compose_route_no_ack():
    c = _client()
    r = c.post(
        "/research/midnight-oil-recap-write-mode-twin-collective/compose",
        json={
            "run_id": "run-2",
            "operator_id": "op-1",
            "work_minutes_planned": 60,
            "work_minutes_actual": 50,
            "goals": [
                {
                    "goal_id": "g1",
                    "title": "Survey",
                    "status": "done",
                },
                {
                    "goal_id": "g2",
                    "title": "Write",
                    "status": "done",
                },
            ],
            "price_ceiling_usd": 20,
            "spend_usd": 10,
            "operator_ack": False,
            "session_id": "s",
            "draft_id": "d",
            "parent_asset_id": "a",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_execution_authorized"] is False
