"""Route tests for workstation record→prompt + write twin highlight pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.workstation_record_write_twin_highlight_compose_routes import (
    register_workstation_record_write_twin_highlight_compose_routes,
)
from tests.test_write_twin_collective_highlight_float_twin_search_compose_routes import (
    _payload as _write_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_workstation_record_write_twin_highlight_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    wp = _write_payload(operator_ack=operator_ack, session_id=session_id)
    return {
        "record_prompt": {
            "session_id": session_id,
            "parent_asset_id": "book-1",
            "records": [
                {
                    "record_id": "r1",
                    "kind": "insight",
                    "body": "scaling holds under noise",
                    "source_ref": "book-1",
                },
                {
                    "record_id": "r2",
                    "kind": "question",
                    "body": "What is the failure mode?",
                },
            ],
            "user_prompt": "Summarize open questions from the pack",
            "selected_model_id": "gpt-5",
            "models": [
                {
                    "model_id": "gpt-5",
                    "tier": "frontier",
                    "projected_cost_usd_high": 2,
                    "projected_cost_usd_low": 1,
                }
            ],
            "daily_cap_usd": 100,
            "spent_usd": 40,
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        "write_pack": {
            "write": wp["write"],
            "highlight_pack": wp["highlight_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/workstation-record-write-twin-highlight/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "workstation_record_write_twin_highlight_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/workstation-record-write-twin-highlight/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False


def test_compose_route_session_mismatch_blocks():
    c = _client()
    r = c.post(
        "/research/workstation-record-write-twin-highlight/compose",
        json=_payload(operator_ack=True, session_id="sess-other"),
    )
    # session_id sess-other may still align if write also uses sess-other from helper
    # force mismatch: write pack uses sess-1 from helper when we pass session_id only to record
    payload = _payload(operator_ack=True, session_id="sess-1")
    payload["record_prompt"]["session_id"] = "sess-other"
    r = c.post(
        "/research/workstation-record-write-twin-highlight/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/workstation-record-write-twin-highlight/compose",
        json=payload,
    )
    assert r.status_code == 422
