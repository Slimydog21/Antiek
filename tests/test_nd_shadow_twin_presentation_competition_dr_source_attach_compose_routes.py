"""Route tests for ND shadow + twin presentation competition DR source-attach."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.nd_shadow_twin_presentation_competition_dr_source_attach_compose_routes import (
    register_nd_shadow_twin_presentation_competition_dr_source_attach_compose_routes,
)
from tests.test_recursive_twin_presentation_competition_dr_source_attach_compose import (
    COMPETITION_PACK,
    PRESENTATION,
    TWIN,
)

_PATH = (
    "/research/nd-shadow-twin-presentation-competition-dr-source-attach/compose"
)


def _client() -> TestClient:
    app = FastAPI()
    register_nd_shadow_twin_presentation_competition_dr_source_attach_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True, open_requested: bool = True) -> dict:
    return {
        "nd_shadow": {
            "selected_model_id": "gpt-5.5",
            "nd_recommended_model_id": "claude-opus",
            "kill_switch_on": True,
            "confidence": 0.72,
            "task": "deep_research",
            "inventory_model_ids": ["gpt-5.5", "claude-opus", "mimo"],
        },
        "twin_presentation": {
            "twin": TWIN,
            "presentation": {**PRESENTATION, "open_requested": open_requested},
            "competition_pack": COMPETITION_PACK,
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_router_authorized"] is False
    assert body["twin_written"] is False
    assert body["merge_executed"] is False
    assert body["purchase_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "nd_shadow_twin_presentation_competition_dr_source_attach_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_router_authorized"] is False


def test_compose_route_open_false_blocks():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True, open_requested=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_router_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
