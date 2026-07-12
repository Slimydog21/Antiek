"""Route tests for recursive twin note-taker over twin search model decision pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_note_taker_twin_search_model_decision_compose_routes import (
    register_recursive_twin_note_taker_twin_search_model_decision_compose_routes,
)
from tests.test_recursive_twin_note_taker_twin_search_model_decision_compose import (
    TWIN,
    TWIN_SEARCH_PACK,
)

_PATH = "/research/recursive-twin-note-taker-twin-search-model-decision/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_note_taker_twin_search_model_decision_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "twin": TWIN,
        "twin_search_pack": TWIN_SEARCH_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["parent_aligned"] is True
    assert body["twin"]["twin_propose_ready"] is True
    assert body["twin_search_pack"]["pack_ready"] is True
    assert body["twin_written"] is False
    assert body["prompts_injected"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["purchase_executed"] is False
    assert body["secrets_stored"] is False
    assert body["live_router_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "recursive_twin_note_taker_twin_search_model_decision_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["twin_written"] is False
    assert body["remote_index_queried"] is False


def test_compose_route_parent_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["twin"] = {**TWIN, "parent_asset_id": "other-book"}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_aligned"] is False
    assert body["pack_ready"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
