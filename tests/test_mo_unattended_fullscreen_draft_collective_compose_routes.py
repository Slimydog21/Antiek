"""Route tests for MO unattended + fullscreen draft collective pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.mo_unattended_fullscreen_draft_collective_compose_routes import (
    register_mo_unattended_fullscreen_draft_collective_compose_routes,
)
from tests.test_fullscreen_draft_collective_presented_twins_compose_routes import (
    _payload as _fs_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_mo_unattended_fullscreen_draft_collective_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    fs = _fs_payload(operator_ack=operator_ack)
    return {
        "mo": {
            "operator_id": "op-1",
            "work_minutes": 120,
            "goals": [
                {"goal_id": "g1", "title": "Map arxiv competition gaps"},
                {"goal_id": "g2", "title": "Synthesize twin notes"},
            ],
            "usd_per_hour": 15,
            "approved_ceiling_usd": 40,
            "unattended_ack": True,
            "spend_consent": True,
            "brief_dispatch_ready": True,
        },
        "fullscreen_pack": {
            "fullscreen": fs["fullscreen"],
            "draft_collective": fs["draft_collective"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/mo-unattended-fullscreen-draft-collective/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["live_dispatched"] is False
    assert body["purchase_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "mo_unattended_fullscreen_draft_collective_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/mo-unattended-fullscreen-draft-collective/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_execution_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/mo-unattended-fullscreen-draft-collective/compose",
        json=payload,
    )
    assert r.status_code == 422
