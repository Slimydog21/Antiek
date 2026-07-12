"""Route tests for floating DR over workstation record model decision MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    register_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes,
)
from tests.test_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    HIGHLIGHT_LAUNCH,
    RECORD_PACK,
)

_PATH = "/research/floating-dr-workstation-record-model-decision-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "highlight_launch": HIGHLIGHT_LAUNCH,
        "record_pack": RECORD_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["parent_aligned"] is True
    assert body["highlight_launch"]["launch_ready"] is True
    assert body["record_pack"]["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["live_router_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_parent_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["highlight_launch"] = {
        **HIGHLIGHT_LAUNCH,
        "parent_asset_id": "book-other",
    }
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_aligned"] is False
    assert body["pack_ready"] is False
    assert body["live_dispatched"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
