"""Route tests for recursive twin + marketplace free competition pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_marketplace_free_competition_dr_compose_routes import (
    register_recursive_twin_marketplace_free_competition_dr_compose_routes,
)
from tests.test_marketplace_free_competition_dr_settings_bench_mo_compose_routes import (
    _payload as _market_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_marketplace_free_competition_dr_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    mp = _market_payload(operator_ack=operator_ack)
    return {
        "twin": {
            "parent_asset_id": "book-1",
            "source_excerpt": (
                "<p>Scaling laws hold under noise in compute-optimal regimes.</p>"
            ),
            "focus_questions": ["Where does it break?", "What residual gaps?"],
            "existing_twin_asset_id": "twin-book-1",
        },
        "market_pack": {
            "market": mp["market"],
            "competition_pack": mp["competition_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/recursive-twin-marketplace-free-competition-dr/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["parent_aligned"] is True
    assert body["twin"]["twin_propose_ready"] is True
    assert body["twin_written"] is False
    assert body["prompts_injected"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "recursive_twin_marketplace_free_competition_dr_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/recursive-twin-marketplace-free-competition-dr/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["twin_written"] is False
    assert body["purchase_executed"] is False


def test_compose_route_parent_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["twin"]["parent_asset_id"] = "book-other"
    r = c.post(
        "/research/recursive-twin-marketplace-free-competition-dr/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_aligned"] is False
    assert body["pack_ready"] is False
    assert body["twin_written"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/recursive-twin-marketplace-free-competition-dr/compose",
        json=payload,
    )
    assert r.status_code == 422
