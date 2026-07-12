"""Route tests for draft-before-merge + multi-select record write pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.draft_before_merge_multi_select_record_write_compose_routes import (
    register_draft_before_merge_multi_select_record_write_compose_routes,
)
from tests.test_multi_select_workstation_record_write_twin_compose_routes import (
    _payload as _ms_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_draft_before_merge_multi_select_record_write_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    ms = _ms_payload(operator_ack=operator_ack, session_id=session_id)
    return {
        "draft_gate": {
            "session_id": session_id,
            "parent_asset_id": "book-1",
            "parent_excerpt": "<p>Parent body on scaling laws</p>",
            "sources": [
                {
                    "instance_id": "float-1",
                    "parent_asset_id": "book-1",
                    "status": "completed",
                    "highlight": "key claim",
                    "findings": ["evidence A"],
                }
            ],
            "stage": "draft_only",
        },
        "multi_pack": {
            "multiselect": ms["multiselect"],
            "record_write": ms["record_write"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/draft-before-merge-multi-select-record-write/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["draft_written"] is False
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "draft_before_merge_multi_select_record_write_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/draft-before-merge-multi-select-record-write/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False


def test_compose_route_session_mismatch_blocks():
    c = _client()
    payload = _payload(operator_ack=True, session_id="sess-1")
    payload["draft_gate"]["session_id"] = "sess-other"
    r = c.post(
        "/research/draft-before-merge-multi-select-record-write/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/draft-before-merge-multi-select-record-write/compose",
        json=payload,
    )
    assert r.status_code == 422
