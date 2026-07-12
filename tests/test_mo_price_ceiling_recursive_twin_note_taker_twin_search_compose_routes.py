"""Route tests for MO price-ceiling over recursive twin note-taker twin search pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_routes import (
    register_mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_routes,
)
from tests.test_mo_price_ceiling_recursive_twin_note_taker_twin_search_compose import (
    MO,
    TWIN_PACK,
)

_PATH = "/research/mo-price-ceiling-recursive-twin-note-taker-twin-search/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "mo": MO,
        "twin_pack": TWIN_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["mo"]["pack_ready"] is True
    assert body["mo"]["ceiling_approved"] is True
    assert body["twin_pack"]["pack_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["twin_written"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False


def test_compose_route_below_ceiling():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["mo"] = {
        **MO,
        "approved_ceiling_usd": 1,
        "below_recommend_override": False,
    }
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mo"]["ceiling_approved"] is False
    assert body["pack_ready"] is False
    assert body["live_execution_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
