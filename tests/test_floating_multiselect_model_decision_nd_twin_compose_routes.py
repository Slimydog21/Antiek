"""Route tests for floating multi-select + model decision ND twin pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_multiselect_model_decision_nd_twin_compose_routes import (
    register_floating_multiselect_model_decision_nd_twin_compose_routes,
)
from tests.test_floating_multiselect_model_decision_nd_twin_compose import (
    DECISION_PACK,
    MULTISELECT,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_multiselect_model_decision_nd_twin_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "multiselect": MULTISELECT,
        "decision_pack": DECISION_PACK,
        "operator_ack": operator_ack,
    }


_PATH = "/research/floating-multiselect-model-decision-nd-twin/compose"


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["multiselect"]["pack_ready"] is True
    assert body["decision_pack"]["pack_ready"] is True
    assert body["session_aligned"] is True
    assert body["parent_aligned"] is True
    assert body["live_dispatched"] is False
    assert body["pack_dispatched"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "floating_multiselect_model_decision_nd_twin_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_dispatched"] is False
    assert body["live_router_authorized"] is False


def test_compose_route_session_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["multiselect"] = {**MULTISELECT, "session_id": "sess-other"}
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
