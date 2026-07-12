"""Route tests for MO price-ceiling + write twin settings draft pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.mo_price_ceiling_write_twin_settings_draft_compose_routes import (
    register_mo_price_ceiling_write_twin_settings_draft_compose_routes,
)
from tests.test_write_twin_collective_settings_draft_fullscreen_nd_mo_compose_routes import (
    _payload as _write_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_mo_price_ceiling_write_twin_settings_draft_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    wp = _write_payload(operator_ack=operator_ack)
    return {
        "mo": {
            "operator_id": "op-1",
            "work_minutes": 120,
            "goals": [
                {"goal_id": "g1", "title": "Map scaling literature"},
                {"goal_id": "g2", "title": "Synthesize open problems"},
            ],
            "usd_per_hour": 30,
            "price_ceiling_ack": True,
            "stage": "recommend_only",
        },
        "research_write": {
            "write": wp["write"],
            "settings_research": wp["settings_research"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/mo-price-ceiling-write-twin-settings-draft/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["draft_written"] is False
    assert body["analysis_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert (
        body["authority"]
        == "mo_price_ceiling_write_twin_settings_draft_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/mo-price-ceiling-write-twin-settings-draft/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["charge_executed"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/mo-price-ceiling-write-twin-settings-draft/compose",
        json=payload,
    )
    assert r.status_code == 422
