"""Route tests for fullscreen + draft collective presented twins pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.fullscreen_draft_collective_presented_twins_compose_routes import (
    register_fullscreen_draft_collective_presented_twins_compose_routes,
)
from tests.test_draft_before_merge_collective_presented_twins_compose_routes import (
    _payload as _draft_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_fullscreen_draft_collective_presented_twins_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    draft = _draft_payload(operator_ack=operator_ack)
    return {
        "fullscreen": {
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "highlight": "Scaling laws claim from page 12",
            "prompt": "What evidence supports this?",
            "gated": False,
        },
        "draft_collective": {
            "draft_gate": draft["draft_gate"],
            "collective_pack": draft["collective_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/fullscreen-draft-collective-presented-twins/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["draft_written"] is False
    assert body["purchase_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "fullscreen_draft_collective_presented_twins_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/fullscreen-draft-collective-presented-twins/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_dispatched"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/fullscreen-draft-collective-presented-twins/compose",
        json=payload,
    )
    assert r.status_code == 422
