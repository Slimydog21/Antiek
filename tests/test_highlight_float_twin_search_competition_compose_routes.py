"""Route tests for highlight float → twin search competition pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.highlight_float_twin_search_competition_compose_routes import (
    register_highlight_float_twin_search_competition_compose_routes,
)
from tests.test_twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_routes import (
    _payload as _twin_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_highlight_float_twin_search_competition_compose_routes(app)
    return TestClient(app)


def _payload(
    *,
    operator_ack: bool = True,
    parent_asset_id: str = "book-1",
    gated: bool = False,
) -> dict:
    twin = _twin_payload(operator_ack=operator_ack)
    return {
        "highlight": {
            "parent_asset_id": parent_asset_id,
            "highlight": "scaling orchestration residual under noise",
            "gated": gated,
            "would_exceed": False,
            "preferred_view_mode": "floating",
            "source_families": ["arxiv", "substack"],
        },
        "twin_search_pack": {
            "competition_pack": twin["competition_pack"],
            # seed from highlight; omit search_query
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/highlight-float-twin-search-competition/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["remote_index_queried"] is False
    assert body["merge_executed"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "highlight_float_twin_search_competition_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/highlight-float-twin-search-competition/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_dispatched"] is False


def test_compose_route_gated_400():
    c = _client()
    r = c.post(
        "/research/highlight-float-twin-search-competition/compose",
        json=_payload(operator_ack=True, gated=True),
    )
    assert r.status_code == 400
    assert "gated" in r.json()["detail"].lower()


def test_compose_route_parent_mismatch_blocks():
    c = _client()
    r = c.post(
        "/research/highlight-float-twin-search-competition/compose",
        json=_payload(operator_ack=True, parent_asset_id="book-other"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["remote_index_queried"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/highlight-float-twin-search-competition/compose",
        json=payload,
    )
    assert r.status_code == 422
