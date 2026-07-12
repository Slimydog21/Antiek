"""Route tests for marketplace free + Antiek-bench recommend MO pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.marketplace_free_antiek_bench_recommend_mo_compose_routes import (
    register_marketplace_free_antiek_bench_recommend_mo_compose_routes,
)
from tests.test_antiek_bench_recommend_mo_unattended_compose_routes import (
    _payload as _bm_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_marketplace_free_antiek_bench_recommend_mo_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    bm = _bm_payload(operator_ack=operator_ack, session_id=session_id)
    return {
        "market": {
            "title": "Scaling Laws Book",
            "account_id": "acct-1",
            "free_copy_available": True,
            "free_html_projection_sha": "sha-free-html",
            "purchase_ack": False,
            "port_requested": True,
        },
        "bench_mo": {
            "bench": bm["bench"],
            "mo_pack": bm["mo_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/marketplace-free-antiek-bench-recommend-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["pdf_primary"] is False
    assert body["live_router_authorized"] is False
    assert body["live_execution_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "marketplace_free_antiek_bench_recommend_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/marketplace-free-antiek-bench-recommend-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["purchase_executed"] is False


def test_compose_route_unknown_free_blocks():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["market"]["free_copy_available"] = None
    payload["market"]["free_html_projection_sha"] = None
    r = c.post(
        "/research/marketplace-free-antiek-bench-recommend-mo/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["market"]["path"] == "blocked_unknown_free"
    assert body["pack_ready"] is False
    assert body["hosted"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/marketplace-free-antiek-bench-recommend-mo/compose",
        json=payload,
    )
    assert r.status_code == 422
