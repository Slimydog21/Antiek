"""Route tests for settings decision + MO unattended fullscreen pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_decision_mo_unattended_fullscreen_compose_routes import (
    register_settings_decision_mo_unattended_fullscreen_compose_routes,
)
from tests.test_mo_unattended_fullscreen_draft_collective_compose_routes import (
    _payload as _mo_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_settings_decision_mo_unattended_fullscreen_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, spent_usd: float = 10) -> dict:
    mo = _mo_payload(operator_ack=operator_ack)
    return {
        "decision": {
            "selected_model_id": "gpt-5.5",
            "models": [
                {
                    "model_id": "gpt-5.5",
                    "tier": "frontier",
                    "projected_cost_usd_high": 2,
                    "projected_cost_usd_low": 1,
                },
                {
                    "model_id": "composer-2.5",
                    "tier": "workhorse",
                    "projected_cost_usd_high": 0.5,
                },
            ],
            "daily_cap_usd": 50,
            "spent_usd": spent_usd,
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
            "focus_task": "deep_research",
            "pending_add_model_ids": ["mimo-v2"],
        },
        "mo_pack": {
            "mo": mo["mo"],
            "fullscreen_pack": mo["fullscreen_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/settings-decision-mo-unattended-fullscreen/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["live_execution_authorized"] is False
    assert body["purchase_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "settings_decision_mo_unattended_fullscreen_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/settings-decision-mo-unattended-fullscreen/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_router_authorized"] is False


def test_compose_route_would_exceed_blocks():
    c = _client()
    payload = _payload(operator_ack=True, spent_usd=49)
    payload["decision"]["projected_cost_usd_high"] = 5
    payload["decision"]["projected_cost_usd_low"] = 3
    r = c.post(
        "/research/settings-decision-mo-unattended-fullscreen/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"]["would_exceed"] is True
    assert body["pack_ready"] is False
    assert body["live_router_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/settings-decision-mo-unattended-fullscreen/compose",
        json=payload,
    )
    assert r.status_code == 422
