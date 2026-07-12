"""Route tests for twin search over HTML-native marketplace free settings ND twin."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_search_html_native_marketplace_free_settings_nd_twin_compose_routes import (
    register_twin_search_html_native_marketplace_free_settings_nd_twin_compose_routes,
)
from tests.test_html_native_marketplace_free_settings_nd_twin_compose import (
    HTML_VIEW,
    MARKET_PACK,
)
from tests.test_twin_search_html_native_marketplace_free_settings_nd_twin_compose import (
    TWIN_RECORDS,
)

_PATH = (
    "/research/twin-search-html-native-marketplace-free-settings-nd-twin/compose"
)


def _client() -> TestClient:
    app = FastAPI()
    register_twin_search_html_native_marketplace_free_settings_nd_twin_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "search_query": "scaling noise",
        "twin_records": TWIN_RECORDS,
        "html_pack": {
            "html_view": HTML_VIEW,
            "market_pack": MARKET_PACK,
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["hit_count"] >= 1
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["purchase_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "twin_search_html_native_marketplace_free_settings_nd_twin_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["remote_index_queried"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
