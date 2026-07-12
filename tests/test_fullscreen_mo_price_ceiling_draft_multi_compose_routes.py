"""Route tests for fullscreen + MO price-ceiling draft multi pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.fullscreen_mo_price_ceiling_draft_multi_compose_routes import (
    register_fullscreen_mo_price_ceiling_draft_multi_compose_routes,
)
from tests.test_mo_price_ceiling_draft_multi_select_record_write_compose_routes import (
    _payload as _mo_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_fullscreen_mo_price_ceiling_draft_multi_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, gated: bool = False) -> dict:
    mo = _mo_payload(operator_ack=operator_ack)
    return {
        "fullscreen": {
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "highlight": "Scaling laws claim from page 12",
            "prompt": "What evidence supports this?",
            "gated": gated,
        },
        "mo_pack": {
            "mo": mo["mo"],
            "draft_multi": mo["draft_multi"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/fullscreen-mo-price-ceiling-draft-multi/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "fullscreen_mo_price_ceiling_draft_multi_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/fullscreen-mo-price-ceiling-draft-multi/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False


def test_compose_route_gated_400():
    c = _client()
    r = c.post(
        "/research/fullscreen-mo-price-ceiling-draft-multi/compose",
        json=_payload(operator_ack=True, gated=True),
    )
    assert r.status_code == 400
    assert "gated" in r.json()["detail"].lower()


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/fullscreen-mo-price-ceiling-draft-multi/compose",
        json=payload,
    )
    assert r.status_code == 422
