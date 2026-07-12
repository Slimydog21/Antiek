"""Route tests for paid-purchase free-first + ND twin presentation pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.paid_purchase_nd_shadow_twin_presentation_compose_routes import (
    register_paid_purchase_nd_shadow_twin_presentation_compose_routes,
)
from tests.test_nd_shadow_twin_presentation_competition_compose_routes import (
    _payload as _nd_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_paid_purchase_nd_shadow_twin_presentation_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    nd = _nd_payload(operator_ack=operator_ack)
    return {
        "purchase": {
            "title": "Scaling Laws Book",
            "account_id": "acct-1",
            "free_copy_available": True,
            "free_html_projection_sha": "sha-free-html",
            "purchase_ack": False,
            "port_requested": True,
            "list_price_usd": 10,
            "approved_spend_usd": 20,
            "remaining_budget_usd": 50,
        },
        "nd_twin": {
            "nd_shadow": nd["nd_shadow"],
            "twin_presentation": nd["twin_presentation"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/paid-purchase-nd-shadow-twin-presentation/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["purchase_executed"] is False
    assert body["charge_executed"] is False
    assert body["hosted"] is False
    assert body["live_router_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "paid_purchase_nd_shadow_twin_presentation_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/paid-purchase-nd-shadow-twin-presentation/compose",
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
        "/research/paid-purchase-nd-shadow-twin-presentation/compose",
        json=payload,
    )
    assert r.status_code == 422
