"""Route tests for marketplace free + competition DR settings pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.marketplace_free_competition_dr_settings_bench_mo_compose_routes import (
    register_marketplace_free_competition_dr_settings_bench_mo_compose_routes,
)
from tests.test_competition_dr_settings_add_model_bench_source_mo_compose_routes import (
    _payload as _comp_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_marketplace_free_competition_dr_settings_bench_mo_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    cp = _comp_payload(operator_ack=operator_ack)
    return {
        "market": {
            "title": "Scaling Laws Book",
            "account_id": "acct-1",
            "free_copy_available": True,
            "free_html_projection_sha": "sha-free-html",
            "purchase_ack": False,
            "port_requested": True,
        },
        "competition_pack": {
            "competition": cp["competition"],
            "settings_pack": cp["settings_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/marketplace-free-competition-dr-settings-bench-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["market"]["port_ready"] is True
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["inventory_mutated"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "marketplace_free_competition_dr_settings_bench_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/marketplace-free-competition-dr-settings-bench-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["purchase_executed"] is False
    assert body["hosted"] is False


def test_compose_route_no_free_sha():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["market"]["free_html_projection_sha"] = None
    r = c.post(
        "/research/marketplace-free-competition-dr-settings-bench-mo/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["market"]["port_ready"] is False
    assert body["pack_ready"] is False
    assert body["purchase_executed"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/marketplace-free-competition-dr-settings-bench-mo/compose",
        json=payload,
    )
    assert r.status_code == 422
