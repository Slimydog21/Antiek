"""Route tests for research interrogation subagent chase compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.research_interrogation_subagent_chase_compose_routes import (
    register_research_interrogation_subagent_chase_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_research_interrogation_subagent_chase_compose_routes(app)
    return TestClient(app)


def test_compose_swarm():
    c = _client()
    r = c.post(
        "/research/interrogation-subagent-chase/compose",
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
            "mark_for_twin_record": True,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["chase_ready"] is True
    assert body["slot_count"] == 2
    assert body["live_dispatched"] is False
    assert body["pack_dispatched"] is False
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False


def test_compose_single():
    c = _client()
    r = c.post(
        "/research/interrogation-subagent-chase/compose",
        json={
            "session_id": "s",
            "parent_asset_id": "p",
            "questions": [{"question_id": "q1", "body": "x"}],
            "chase_mode": "single_question",
            "would_exceed": False,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["slot_count"] == 1
    assert r.json()["live_dispatched"] is False


def test_compose_budget_block():
    c = _client()
    r = c.post(
        "/research/interrogation-subagent-chase/compose",
        json={
            "session_id": "s",
            "parent_asset_id": "p",
            "questions": [{"question_id": "q1", "body": "x"}],
            "chase_mode": "single_question",
            "would_exceed": True,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["chase_ready"] is False
    assert r.json()["live_dispatched"] is False


def test_compose_secret_model_400():
    c = _client()
    r = c.post(
        "/research/interrogation-subagent-chase/compose",
        json={
            "session_id": "s",
            "parent_asset_id": "p",
            "questions": [{"question_id": "q1", "body": "x"}],
            "chase_mode": "single_question",
            "would_exceed": False,
            "selected_model_id": "sk-secret",
            "operator_ack": True,
        },
    )
    assert r.status_code == 400
