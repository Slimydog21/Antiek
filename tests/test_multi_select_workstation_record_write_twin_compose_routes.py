"""Route tests for multi-select + workstation record write twin pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.multi_select_workstation_record_write_twin_compose_routes import (
    register_multi_select_workstation_record_write_twin_compose_routes,
)
from tests.test_workstation_record_write_twin_highlight_compose_routes import (
    _payload as _rw_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_multi_select_workstation_record_write_twin_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    rw = _rw_payload(operator_ack=operator_ack, session_id=session_id)
    return {
        "multiselect": {
            "session_id": session_id,
            "parent_asset_id": "book-1",
            "members": [
                {
                    "instance_id": "inst-a",
                    "parent_asset_id": "book-1",
                    "status": "open",
                    "highlight": "scaling laws claim",
                },
                {
                    "instance_id": "inst-b",
                    "parent_asset_id": "book-1",
                    "status": "completed",
                    "highlight": "counter-evidence",
                    "findings": ["finding-b1"],
                },
            ],
            "selected_instance_ids": ["inst-a", "inst-b"],
            "pack_mode": "cohesive_prompt",
            "cohesive_prompt": "Synthesize A and B as one unit",
        },
        "record_write": {
            "record_prompt": rw["record_prompt"],
            "write_pack": rw["write_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/multi-select-workstation-record-write-twin/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["pack_dispatched"] is False
    assert body["prompts_injected"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "multi_select_workstation_record_write_twin_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/multi-select-workstation-record-write-twin/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False


def test_compose_route_session_mismatch_blocks():
    c = _client()
    payload = _payload(operator_ack=True, session_id="sess-1")
    payload["multiselect"]["session_id"] = "sess-other"
    r = c.post(
        "/research/multi-select-workstation-record-write-twin/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/multi-select-workstation-record-write-twin/compose",
        json=payload,
    )
    assert r.status_code == 422
