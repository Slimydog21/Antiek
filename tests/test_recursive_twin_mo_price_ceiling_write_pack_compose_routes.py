"""Route tests for recursive twin + MO price-ceiling write pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_mo_price_ceiling_write_pack_compose_routes import (
    register_recursive_twin_mo_price_ceiling_write_pack_compose_routes,
)
from tests.test_mo_price_ceiling_write_twin_settings_draft_compose_routes import (
    _payload as _mo_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_mo_price_ceiling_write_pack_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    mp = _mo_payload(operator_ack=operator_ack)
    return {
        "twin": {
            "parent_asset_id": "book-1",
            "source_excerpt": (
                "<p>Scaling laws hold under noise in compute-optimal regimes.</p>"
            ),
            "focus_questions": ["Where does it break?", "What residual gaps?"],
        },
        "mo_write": {
            "mo": mp["mo"],
            "research_write": mp["research_write"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/recursive-twin-mo-price-ceiling-write-pack/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["twin_written"] is False
    assert body["prompts_injected"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["charge_executed"] is False
    assert body["live_execution_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "recursive_twin_mo_price_ceiling_write_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/recursive-twin-mo-price-ceiling-write-pack/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["twin_written"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/recursive-twin-mo-price-ceiling-write-pack/compose",
        json=payload,
    )
    assert r.status_code == 422
