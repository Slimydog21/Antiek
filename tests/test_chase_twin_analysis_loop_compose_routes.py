"""Route tests for chase → twin → analysis loop compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.chase_twin_analysis_loop_compose_routes import (
    register_chase_twin_analysis_loop_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_chase_twin_analysis_loop_compose_routes(app)
    return TestClient(app)


def test_compose_loop():
    c = _client()
    r = c.post(
        "/research/chase-twin-analysis-loop/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "paper-1",
            "questions": [
                {"question_id": "q1", "body": "Core claim?", "priority": 2},
                {"question_id": "q2", "body": "Missing evidence?", "priority": 1},
            ],
            "chase_mode": "swarm_fanout",
            "would_exceed": False,
            "source_families": ["arxiv", "substack"],
            "operator_ack": True,
            "analysis_kind": "draft_analysis",
            "analysis_excerpt": "draft scaffold",
            "completed_slots": [
                {
                    "slot_id": "chase_1_q1",
                    "question_id": "q1",
                    "parent_asset_id": "paper-1",
                    "status": "completed",
                    "findings": ["claim A"],
                },
                {
                    "slot_id": "chase_2_q2",
                    "question_id": "q2",
                    "parent_asset_id": "paper-1",
                    "status": "completed",
                    "findings": ["gap B"],
                },
            ],
            "mark_for_prompt_context": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["loop_ready"] is True
    assert body["live_dispatched"] is False
    assert body["twin_written"] is False
    assert body["analysis_written"] is False
    assert body["record_persisted"] is False
    assert body["pack_dispatched"] is False


def test_compose_would_exceed():
    c = _client()
    r = c.post(
        "/research/chase-twin-analysis-loop/compose",
        json={
            "session_id": "s",
            "parent_asset_id": "p",
            "questions": [
                {"question_id": "q1", "body": "A?"},
                {"question_id": "q2", "body": "B?"},
            ],
            "chase_mode": "swarm_fanout",
            "would_exceed": True,
            "operator_ack": True,
            "analysis_kind": "draft_analysis",
            "completed_slots": [
                {
                    "slot_id": "a",
                    "question_id": "q1",
                    "parent_asset_id": "p",
                    "status": "completed",
                    "findings": ["x"],
                },
                {
                    "slot_id": "b",
                    "question_id": "q2",
                    "parent_asset_id": "p",
                    "status": "completed",
                    "findings": ["y"],
                },
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["loop_ready"] is False
    assert r.json()["live_dispatched"] is False
