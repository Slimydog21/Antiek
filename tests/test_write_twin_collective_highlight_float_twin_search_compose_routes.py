"""Route tests for write twin + highlight float twin-search pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.write_twin_collective_highlight_float_twin_search_compose_routes import (
    register_write_twin_collective_highlight_float_twin_search_compose_routes,
)
from tests.test_highlight_float_twin_search_competition_compose_routes import (
    _payload as _hl_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_write_twin_collective_highlight_float_twin_search_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    hl = _hl_payload(operator_ack=operator_ack)
    return {
        "write": {
            "session_id": session_id,
            "draft_id": "draft-1",
            "parent_asset_id": "book-1",
            "twin_slices": [
                {
                    "parent_asset_id": "asset-1",
                    "insights": ["scaling holds"],
                    "questions": ["breaks?"],
                },
                {
                    "parent_asset_id": "asset-2",
                    "insights": ["attention"],
                    "questions": [],
                },
            ],
            "chase_slots": [
                {
                    "slot_id": "s1",
                    "question_id": "q1",
                    "parent_asset_id": "book-1",
                    "status": "completed",
                    "findings": ["A"],
                    "body": "Evidence?",
                },
                {
                    "slot_id": "s2",
                    "question_id": "q2",
                    "parent_asset_id": "book-1",
                    "status": "completed",
                    "findings": ["B"],
                    "body": "Counter?",
                },
            ],
            "analysis_kind": "draft_analysis",
        },
        "highlight_pack": {
            "highlight": hl["highlight"],
            "twin_search_pack": hl["twin_search_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/write-twin-collective-highlight-float-twin-search/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["draft_written"] is False
    assert body["analysis_written"] is False
    assert body["remote_index_queried"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "write_twin_collective_highlight_float_twin_search_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/write-twin-collective-highlight-float-twin-search/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False


def test_compose_route_session_mismatch_blocks():
    c = _client()
    r = c.post(
        "/research/write-twin-collective-highlight-float-twin-search/compose",
        json=_payload(operator_ack=True, session_id="sess-other"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/write-twin-collective-highlight-float-twin-search/compose",
        json=payload,
    )
    assert r.status_code == 422
