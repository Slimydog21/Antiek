"""Route tests for MO unattended + source attach model decision pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.mo_unattended_source_attach_model_decision_compose_routes import (
    register_mo_unattended_source_attach_model_decision_compose_routes,
)
from tests.test_source_attach_model_decision_twin_search_compose_routes import (
    _payload as _rp_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_mo_unattended_source_attach_model_decision_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    rp = _rp_payload(operator_ack=operator_ack, session_id=session_id)
    return {
        "mo": {
            "operator_id": "op-1",
            "work_minutes": 120,
            "goals": [
                {"goal_id": "g1", "title": "Map arxiv competition gaps"},
                {"goal_id": "g2", "title": "Synthesize twin notes"},
            ],
            "usd_per_hour": 30,
            "approved_ceiling_usd": 500,
            "price_ceiling_ack": True,
            "unattended_ack": True,
            "spend_consent": True,
            "stage": "unattended_pack",
        },
        "research_pack": {
            "sources": rp["sources"],
            "decision_pack": rp["decision_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/mo-unattended-source-attach-model-decision/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["remote_fetched"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "mo_unattended_source_attach_model_decision_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/mo-unattended-source-attach-model-decision/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_execution_authorized"] is False


def test_compose_route_session_mismatch_blocks():
    c = _client()
    payload = _payload(operator_ack=True, session_id="sess-1")
    payload["research_pack"]["sources"]["session_id"] = "sess-other"
    r = c.post(
        "/research/mo-unattended-source-attach-model-decision/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["charge_executed"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/mo-unattended-source-attach-model-decision/compose",
        json=payload,
    )
    assert r.status_code == 422
