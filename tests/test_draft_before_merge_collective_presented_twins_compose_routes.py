"""Route tests for draft-before-merge + collective presented twins pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.draft_before_merge_collective_presented_twins_compose_routes import (
    register_draft_before_merge_collective_presented_twins_compose_routes,
)
from tests.test_collective_presented_twins_paid_nd_compose_routes import (
    _payload as _col_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_draft_before_merge_collective_presented_twins_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    col = _col_payload(operator_ack=operator_ack)
    return {
        "draft_gate": {
            "session_id": "sess-1",
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
        "collective_pack": {
            "collective": col["collective"],
            "paid_nd": col["paid_nd"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/draft-before-merge-collective-presented-twins/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["draft_written"] is False
    assert body["merge_executed"] is False
    assert body["purchase_executed"] is False
    assert body["live_router_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "draft_before_merge_collective_presented_twins_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/draft-before-merge-collective-presented-twins/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["draft_written"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/draft-before-merge-collective-presented-twins/compose",
        json=payload,
    )
    assert r.status_code == 422
