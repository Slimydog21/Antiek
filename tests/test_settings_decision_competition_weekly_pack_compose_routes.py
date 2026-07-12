"""Route tests for settings decision over competition DR ND shadow twin weekly."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_decision_competition_weekly_pack_compose_routes import (
    register_settings_decision_competition_weekly_pack_compose_routes,
)
from tests.test_settings_decision_competition_weekly_pack_compose import (
    COMPETITION_PACK,
    SETTINGS,
)

_PATH = (
    "/research/settings-decision-competition-weekly-pack/compose"
)


def _client() -> TestClient:
    app = FastAPI()
    register_settings_decision_competition_weekly_pack_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "settings": SETTINGS,
        "competition_pack": COMPETITION_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["week_aligned"] is True
    assert body["session_aligned"] is True
    assert body["settings"]["pack_ready"] is True
    assert body["competition_pack"]["pack_ready"] is True
    assert body["secrets_stored"] is False
    assert body["inventory_mutated"] is False
    assert body["live_router_authorized"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "settings_decision_competition_weekly_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["secrets_stored"] is False
    assert body["inventory_mutated"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_week_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["settings"] = {**SETTINGS, "week_id": "2026-W99"}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["week_aligned"] is False
    assert body["pack_ready"] is False
    assert body["secrets_stored"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
