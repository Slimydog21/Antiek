"""Route tests for ND shadow over twin presentation weekly source-attach."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.nd_shadow_recursive_twin_weekly_src_write_mo_weekly_pack_compose_routes import (
    register_nd_shadow_recursive_twin_weekly_src_write_mo_weekly_pack_compose_routes,
)
from tests.test_nd_shadow_recursive_twin_weekly_src_write_mo_weekly_pack_compose import (
    ND_SHADOW,
    TWIN_PRESENTATION,
)
from tests.test_recursive_twin_presentation_weekly_src_write_mo_weekly_pack_compose import (
    PRESENTATION,
)

_PATH = (
    "/research/nd-shadow-recursive-twin-weekly-src-write-mo-weekly-pack/compose"
)


def _client() -> TestClient:
    app = FastAPI()
    register_nd_shadow_recursive_twin_weekly_src_write_mo_weekly_pack_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "nd_shadow": ND_SHADOW,
        "twin_presentation": TWIN_PRESENTATION,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["nd_shadow"]["production_router_verdict"] == "REJECT"
    assert body["nd_shadow"]["live_router_authorized"] is False
    assert body["twin_presentation"]["pack_ready"] is True
    assert body["live_router_authorized"] is False
    assert body["twin_written"] is False
    assert body["backlog_mutated"] is False
    assert body["suite_rewritten"] is False
    assert body["remote_fetched"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "nd_shadow_recursive_twin_weekly_src_write_mo_weekly_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_router_authorized"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_open_requested_false():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["twin_presentation"] = {
        **TWIN_PRESENTATION,
        "presentation": {**PRESENTATION, "open_requested": False},
    }
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["twin_presentation"]["presentation"]["presentation_ready"] is False
    assert body["pack_ready"] is False
    assert body["live_router_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
