"""Route tests for settings add-model + ND twin presentation pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_add_model_nd_shadow_twin_presentation_compose_routes import (
    register_settings_add_model_nd_shadow_twin_presentation_compose_routes,
)
from tests.test_nd_shadow_twin_presentation_competition_dr_source_attach_compose import (
    ND_SHADOW,
    TWIN_PRESENTATION,
)

_PATH = "/research/settings-add-model-nd-shadow-twin-presentation/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_settings_add_model_nd_shadow_twin_presentation_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "settings": {
            "models": [
                {"model_id": "gpt-5.5", "provider": "openai"},
                {"model_id": "grok-4.5", "provider": "xai"},
            ],
            "pending_add_model_ids": ["mimo-v2", "composer-2.5"],
            "action": "propose_add",
            "daily_cap_usd": 50,
            "spent_usd": 10,
            "selected_model_id": "gpt-5.5",
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        "nd_pack": {
            "nd_shadow": ND_SHADOW,
            "twin_presentation": TWIN_PRESENTATION,
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["secrets_stored"] is False
    assert body["inventory_mutated"] is False
    assert body["live_router_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "settings_add_model_nd_shadow_twin_presentation_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["secrets_stored"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
