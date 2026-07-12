"""Route tests for settings add-model + draft fullscreen weekly ND."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_add_model_draft_fullscreen_weekly_nd_mo_compose_routes import (
    register_settings_add_model_draft_fullscreen_weekly_nd_mo_compose_routes,
)
from tests.test_floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_routes import (
    _payload as _draft_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_settings_add_model_draft_fullscreen_weekly_nd_mo_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, secret_pending: bool = False) -> dict:
    draft = _draft_payload(operator_ack=operator_ack)
    return {
        "settings": {
            "models": [
                {"model_id": "gpt-5.5", "provider": "openai"},
                {"model_id": "grok-4.5", "provider": "xai"},
            ],
            "pending_add_model_ids": (
                ["sk-abc123secret"] if secret_pending else ["mimo-v2"]
            ),
            "action": "preview",
            "daily_cap_usd": 25,
            "spent_usd": 4,
            "selected_model_id": "gpt-5.5",
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        "research_pack": {
            "draft_gate": draft["draft_gate"],
            "fullscreen_pack": draft["fullscreen_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/settings-add-model-draft-fullscreen-weekly-nd-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["secrets_stored"] is False
    assert body["inventory_mutated"] is False
    assert body["draft_written"] is False
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert (
        body["authority"]
        == "settings_add_model_draft_fullscreen_weekly_nd_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/settings-add-model-draft-fullscreen-weekly-nd-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["secrets_stored"] is False


def test_compose_route_secret_pending_400():
    c = _client()
    r = c.post(
        "/research/settings-add-model-draft-fullscreen-weekly-nd-mo/compose",
        json=_payload(operator_ack=True, secret_pending=True),
    )
    assert r.status_code == 400


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/settings-add-model-draft-fullscreen-weekly-nd-mo/compose",
        json=payload,
    )
    assert r.status_code == 422
