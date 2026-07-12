"""Route tests for fullscreen + MO unattended draft multiselect ND twin."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_routes import (
    register_fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_routes,
)
from tests.test_fullscreen_mo_unattended_draft_multiselect_nd_twin_compose import (
    FULLSCREEN,
    MO_PACK,
)


def _client() -> TestClient:
    app = FastAPI()
    register_fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "fullscreen": FULLSCREEN,
        "mo_pack": MO_PACK,
        "operator_ack": operator_ack,
    }


_PATH = "/research/fullscreen-mo-unattended-draft-multiselect-nd-twin/compose"


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["fullscreen"]["fullscreen_ready"] is True
    assert body["mo_pack"]["pack_ready"] is True
    assert body["session_aligned"] is True
    assert body["parent_aligned"] is True
    assert body["live_dispatched"] is False
    assert body["live_execution_authorized"] is False
    assert body["merge_executed"] is False
    assert body["draft_written"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_dispatched"] is False
    assert body["live_execution_authorized"] is False


def test_compose_route_session_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["fullscreen"] = {**FULLSCREEN, "session_id": "sess-other"}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_aligned"] is False
    assert body["pack_ready"] is False
    assert body["live_dispatched"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
