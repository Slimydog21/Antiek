"""Route tests for chase completion collective analysis compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.chase_completion_collective_analysis_compose_routes import (
    register_chase_completion_collective_analysis_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_chase_completion_collective_analysis_compose_routes(app)
    return TestClient(app)


def test_compose_draft():
    c = _client()
    r = c.post(
        "/research/chase-completion-analysis/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "paper-1",
            "kind": "draft_analysis",
            "operator_ack": False,
            "slots": [
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
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["analysis_ready"] is True
    assert body["analysis_written"] is False
    assert body["live_dispatched"] is False
    assert body["pack_dispatched"] is False


def test_compose_full():
    c = _client()
    r = c.post(
        "/research/chase-completion-analysis/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "paper-1",
            "kind": "full_analysis",
            "operator_ack": True,
            "slots": [
                {
                    "slot_id": "a",
                    "question_id": "q1",
                    "parent_asset_id": "paper-1",
                    "status": "completed",
                },
                {
                    "slot_id": "b",
                    "question_id": "q2",
                    "parent_asset_id": "paper-1",
                    "status": "completed",
                },
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["analysis_ready"] is True
    assert r.json()["analysis_written"] is False


def test_compose_full_no_ack_400():
    c = _client()
    r = c.post(
        "/research/chase-completion-analysis/compose",
        json={
            "session_id": "s",
            "parent_asset_id": "p",
            "kind": "full_analysis",
            "operator_ack": False,
            "slots": [
                {
                    "slot_id": "a",
                    "question_id": "q1",
                    "parent_asset_id": "p",
                    "status": "completed",
                },
                {
                    "slot_id": "b",
                    "question_id": "q2",
                    "parent_asset_id": "p",
                    "status": "completed",
                },
            ],
        },
    )
    assert r.status_code == 400
