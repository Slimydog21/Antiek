"""Route tests for draft-before-merge + floating multi-select model decision pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.draft_before_merge_floating_multiselect_model_decision_compose_routes import (
    register_draft_before_merge_floating_multiselect_model_decision_compose_routes,
)
from tests.test_draft_before_merge_floating_multiselect_model_decision_compose import (
    DRAFT_GATE,
    MULTI_PACK,
)


def _client() -> TestClient:
    app = FastAPI()
    register_draft_before_merge_floating_multiselect_model_decision_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "draft_gate": DRAFT_GATE,
        "multi_pack": MULTI_PACK,
        "operator_ack": operator_ack,
    }


_PATH = "/research/draft-before-merge-floating-multiselect-model-decision/compose"


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["draft_gate"]["gate_ready"] is True
    assert body["multi_pack"]["pack_ready"] is True
    assert body["session_aligned"] is True
    assert body["parent_aligned"] is True
    assert body["draft_written"] is False
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "draft_before_merge_floating_multiselect_model_decision_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["draft_written"] is False
    assert body["merge_executed"] is False


def test_compose_route_session_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["draft_gate"] = {**DRAFT_GATE, "session_id": "sess-other"}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_aligned"] is False
    assert body["pack_ready"] is False
    assert body["draft_written"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
