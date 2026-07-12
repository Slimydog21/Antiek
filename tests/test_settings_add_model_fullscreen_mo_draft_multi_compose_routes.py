"""Route tests for settings add-model + fullscreen MO draft multi pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_add_model_fullscreen_mo_draft_multi_compose_routes import (
    register_settings_add_model_fullscreen_mo_draft_multi_compose_routes,
)
from tests.test_fullscreen_mo_price_ceiling_draft_multi_compose_routes import (
    _payload as _fs_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_settings_add_model_fullscreen_mo_draft_multi_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, action: str = "preview") -> dict:
    fs = _fs_payload(operator_ack=operator_ack)
    return {
        "settings": {
            "models": [
                {"model_id": "gpt-5.5", "provider": "openai"},
                {"model_id": "grok-4.5", "provider": "xai"},
            ],
            "pending_add_model_ids": ["mimo-v2"],
            "action": action,
            "daily_cap_usd": 25,
            "spent_usd": 4,
            "selected_model_id": "gpt-5.5",
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        "fullscreen_mo": {
            "fullscreen": fs["fullscreen"],
            "mo_pack": fs["mo_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/settings-add-model-fullscreen-mo-draft-multi/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["secrets_stored"] is False
    assert body["inventory_mutated"] is False
    assert body["live_dispatched"] is False
    assert body["charge_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "settings_add_model_fullscreen_mo_draft_multi_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/settings-add-model-fullscreen-mo-draft-multi/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["secrets_stored"] is False


def test_compose_route_propose_add():
    c = _client()
    r = c.post(
        "/research/settings-add-model-fullscreen-mo-draft-multi/compose",
        json=_payload(operator_ack=True, action="propose_add"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["inventory_mutated"] is False
    assert body["settings"]["proposed_new_count"] >= 1


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/settings-add-model-fullscreen-mo-draft-multi/compose",
        json=payload,
    )
    assert r.status_code == 422
