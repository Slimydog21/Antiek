"""Route tests for workstation records over model decision twin search MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_routes import (
    register_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_routes,
)
from tests.test_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose import (
    DECISION_PACK,
    ITEMS,
)

_PATH = "/research/workstation-record-model-decision-twin-search-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-m-pack/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "session_id": "sess-1",
        "items": ITEMS,
        "decision_pack": DECISION_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["session_aligned"] is True
    assert body["records"]["pack_ready"] is True
    assert body["records"]["item_count"] == 2
    assert body["decision_pack"]["pack_ready"] is True
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["twin_written"] is False
    assert body["purchase_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_session_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["session_id"] = "sess-other"
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_aligned"] is False
    assert body["pack_ready"] is False
    assert body["record_persisted"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
