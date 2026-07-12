"""Route tests for ND shadow + twin presentation competition pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.nd_shadow_twin_presentation_competition_compose_routes import (
    register_nd_shadow_twin_presentation_competition_compose_routes,
)
from tests.test_recursive_twin_presentation_competition_dr_compose_routes import (
    _payload as _twin_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_nd_shadow_twin_presentation_competition_compose_routes(app)
    return TestClient(app)


def _payload(
    *,
    operator_ack: bool = True,
    kill_switch_on: bool = True,
    open_requested: bool = True,
) -> dict:
    twin = _twin_payload(
        operator_ack=operator_ack, open_requested=open_requested
    )
    return {
        "nd_shadow": {
            "selected_model_id": "gpt-5.5",
            "nd_recommended_model_id": "claude-opus",
            "kill_switch_on": kill_switch_on,
            "confidence": 0.72,
            "task": "deep_research",
            "inventory_model_ids": ["gpt-5.5", "claude-opus"],
        },
        "twin_presentation": {
            "twin": twin["twin"],
            "presentation": twin["presentation"],
            "competition_pack": twin["competition_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/nd-shadow-twin-presentation-competition/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert body["twin_written"] is False
    assert body["purchase_executed"] is False
    assert (
        body["authority"]
        == "nd_shadow_twin_presentation_competition_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/nd-shadow-twin-presentation-competition/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_router_authorized"] is False


def test_compose_route_kill_switch_off_still_reject():
    c = _client()
    r = c.post(
        "/research/nd-shadow-twin-presentation-competition/compose",
        json=_payload(operator_ack=True, kill_switch_on=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert body["pack_ready"] is True


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/nd-shadow-twin-presentation-competition/compose",
        json=payload,
    )
    assert r.status_code == 422
