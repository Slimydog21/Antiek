"""Route tests for recursive twin presentation + write twin collective MO."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_routes import (
    register_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_routes,
)
from tests.test_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose import (
    PRESENTATION,
    TWIN,
    WRITE_PACK,
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "twin": TWIN,
        "presentation": PRESENTATION,
        "write_pack": WRITE_PACK,
        "operator_ack": operator_ack,
    }


_PATH = (
    "/research/recursive-twin-presentation-write-twin-collective-fullscreen-mo-nd-twin/compose"
)


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["twin"]["twin_propose_ready"] is True
    assert body["presentation"]["presentation_ready"] is True
    assert body["write_pack"]["pack_ready"] is True
    assert body["parent_aligned"] is True
    assert body["twin_written"] is False
    assert body["prompts_injected"] is False
    assert body["merge_executed"] is False
    assert body["draft_written"] is False
    assert body["analysis_written"] is False
    assert body["live_dispatched"] is False
    assert body["live_execution_authorized"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["presentation"]["presentation_ready"] is False
    assert body["twin_written"] is False
    assert body["merge_executed"] is False


def test_compose_route_open_requested_false():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["presentation"] = {**PRESENTATION, "open_requested": False}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["presentation"]["presentation_ready"] is False
    assert body["pack_ready"] is False
    assert body["twin_written"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
