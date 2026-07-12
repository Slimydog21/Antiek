"""Route tests for marketplace free + source-attach record→prompt pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.marketplace_free_source_attach_record_prompt_compose_routes import (
    register_marketplace_free_source_attach_record_prompt_compose_routes,
)
from tests.test_source_attach_record_prompt_html_native_mo_compose_routes import (
    _payload as _research_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_marketplace_free_source_attach_record_prompt_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    rp = _research_payload(operator_ack=operator_ack)
    return {
        "market": {
            "title": "Scaling Laws Book",
            "account_id": "acct-1",
            "free_copy_available": True,
            "free_html_projection_sha": "sha-free-1",
            "purchase_ack": False,
            "port_requested": True,
        },
        "research": {
            "sources": rp["sources"],
            "record_html": rp["record_html"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/marketplace-free-source-attach-record-prompt/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["remote_fetched"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert (
        body["authority"]
        == "marketplace_free_source_attach_record_prompt_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/marketplace-free-source-attach-record-prompt/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["purchase_executed"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/marketplace-free-source-attach-record-prompt/compose",
        json=payload,
    )
    assert r.status_code == 422
