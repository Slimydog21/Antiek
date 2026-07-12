"""Route tests for recursive twin presentation + competition DR pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_presentation_competition_dr_compose_routes import (
    register_recursive_twin_presentation_competition_dr_compose_routes,
)
from tests.test_competition_dr_marketplace_free_bench_mo_compose_routes import (
    _payload as _comp_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_presentation_competition_dr_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, open_requested: bool = True) -> dict:
    comp = _comp_payload(operator_ack=operator_ack, session_id="sess-1")
    return {
        "twin": {
            "parent_asset_id": "book-1",
            "source_excerpt": (
                "<p>Scaling laws hold under noise in compute-optimal regimes.</p>"
            ),
            "focus_questions": ["Where does it break?", "What residual gaps?"],
            "existing_twin_asset_id": "twin-book-1",
        },
        "presentation": {
            "view_mode": "side_panel",
            "open_requested": open_requested,
            "merge_to_parent_preview": False,
            "presented_insights": [
                "scaling laws hold under noise in compute-optimal regimes",
            ],
            "presented_questions": [
                "Where does scaling break under distribution shift?",
            ],
        },
        "competition_pack": {
            "competition": comp["competition"],
            "free_pack": comp["free_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/recursive-twin-presentation-competition-dr/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["presentation"]["presentation_ready"] is True
    assert body["twin_written"] is False
    assert body["merge_executed"] is False
    assert body["purchase_executed"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "recursive_twin_presentation_competition_dr_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/recursive-twin-presentation-competition-dr/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["twin_written"] is False


def test_compose_route_open_false_blocks():
    c = _client()
    r = c.post(
        "/research/recursive-twin-presentation-competition-dr/compose",
        json=_payload(operator_ack=True, open_requested=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["presentation"]["presentation_ready"] is False
    assert body["pack_ready"] is False
    assert body["merge_executed"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/recursive-twin-presentation-competition-dr/compose",
        json=payload,
    )
    assert r.status_code == 422
