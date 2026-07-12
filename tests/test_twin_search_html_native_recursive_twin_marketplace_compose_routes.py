"""Route tests for twin search + HTML-native recursive twin marketplace pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_search_html_native_recursive_twin_marketplace_compose_routes import (
    register_twin_search_html_native_recursive_twin_marketplace_compose_routes,
)
from tests.test_html_native_recursive_twin_marketplace_free_compose_routes import (
    _payload as _html_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_twin_search_html_native_recursive_twin_marketplace_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    hp = _html_payload(operator_ack=operator_ack)
    return {
        "search_query": "scaling noise",
        "twin_records": [
            {
                "twin_id": "twin-book-1",
                "parent_asset_id": "book-1",
                "insights": [
                    "scaling laws hold under noise in compute-optimal regimes"
                ],
                "questions": [
                    "Where does scaling break under distribution shift?"
                ],
                "source_label": "book-1-twin",
            },
            {
                "twin_id": "twin-arxiv-1",
                "parent_asset_id": "cite-parent-c1",
                "insights": ["Scaling Laws under Noise"],
                "questions": ["How does arxiv residual inform Antiek DR?"],
                "source_label": "arxiv",
            },
        ],
        "html_pack": {
            "html_view": hp["html_view"],
            "twin_pack": hp["twin_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/twin-search-html-native-recursive-twin-marketplace/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["hit_count"] >= 1
    assert body["remote_index_queried"] is False
    assert body["pdf_view_authorized"] is False
    assert body["twin_written"] is False
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "twin_search_html_native_recursive_twin_marketplace_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/twin-search-html-native-recursive-twin-marketplace/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_view_authorized"] is False


def test_compose_route_zero_hits():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["search_query"] = "zzzznonexistenttoken"
    r = c.post(
        "/research/twin-search-html-native-recursive-twin-marketplace/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hit_count"] == 0
    assert body["pack_ready"] is False
    assert body["remote_index_queried"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/twin-search-html-native-recursive-twin-marketplace/compose",
        json=payload,
    )
    assert r.status_code == 422
