"""Route tests for Midnight Oil over settings decision competition DR."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    register_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes,
)
from tests.test_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    MO,
    SETTINGS_PACK,
)

_PATH = "/research/midnight-oil-settings-decision-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "mo": MO,
        "settings_pack": SETTINGS_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["mo"]["pack_ready"] is True
    assert body["settings_pack"]["pack_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["secrets_stored"] is False
    assert body["inventory_mutated"] is False
    assert body["live_router_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_price_ceiling_ack_false():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["mo"] = {**MO, "price_ceiling_ack": False}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mo"]["pack_ready"] is False
    assert body["pack_ready"] is False
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
