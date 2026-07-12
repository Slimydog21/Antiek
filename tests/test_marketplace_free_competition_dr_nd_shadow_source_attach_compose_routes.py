"""Route tests for marketplace free + competition DR ND shadow source-attach."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.marketplace_free_competition_dr_nd_shadow_source_attach_compose_routes import (
    register_marketplace_free_competition_dr_nd_shadow_source_attach_compose_routes,
)
from tests.test_marketplace_free_competition_dr_nd_shadow_source_attach_compose import (
    COMPETITION_PACK,
    MARKET,
)


def _client() -> TestClient:
    app = FastAPI()
    register_marketplace_free_competition_dr_nd_shadow_source_attach_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "market": MARKET,
        "competition_pack": COMPETITION_PACK,
        "operator_ack": operator_ack,
    }


_PATH = "/research/marketplace-free-competition-dr-nd-shadow-source-attach/compose"


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["market"]["port_ready"] is True
    assert body["competition_pack"]["pack_ready"] is True
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["pdf_view_authorized"] is False
    assert body["pdf_primary"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["backlog_mutated"] is False
    assert body["live_router_authorized"] is False
    assert body["twin_written"] is False
    assert body["merge_executed"] is False
    assert body["draft_written"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["competition_pack"]["nd_pack"]["nd_shadow"]["production_router_verdict"]
        == "REJECT"
    )
    assert (
        body["authority"]
        == "marketplace_free_competition_dr_nd_shadow_source_attach_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["live_dispatch_authorized"] is False


def test_compose_route_no_free_copy():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["market"] = {
        **MARKET,
        "free_copy_available": False,
        "free_html_projection_sha": None,
        "purchase_ack": False,
        "port_requested": True,
    }
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["market"]["port_ready"] is False
    assert body["pack_ready"] is False
    assert body["purchase_executed"] is False
    assert body["hosted"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
