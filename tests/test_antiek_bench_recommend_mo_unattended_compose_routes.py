"""Route tests for Antiek-bench recommend + MO unattended pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.antiek_bench_recommend_mo_unattended_compose_routes import (
    register_antiek_bench_recommend_mo_unattended_compose_routes,
)
from tests.test_mo_unattended_source_attach_model_decision_compose_routes import (
    _payload as _mo_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_antiek_bench_recommend_mo_unattended_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    mo = _mo_payload(operator_ack=operator_ack, session_id=session_id)
    return {
        "bench": {
            "week_id": "2026-W28",
            "focus_task": "deep_research",
            "events": [
                {
                    "event_id": "e1",
                    "task": "deep_research",
                    "model_id": "gpt-5.5",
                    "outcome": "worked",
                    "score": 0.9,
                },
                {
                    "event_id": "e2",
                    "task": "deep_research",
                    "model_id": "gpt-5.5",
                    "outcome": "worked",
                    "score": 0.85,
                },
                {
                    "event_id": "e3",
                    "task": "deep_research",
                    "model_id": "mimo-v2",
                    "outcome": "failed",
                    "score": 0.2,
                },
                {
                    "event_id": "e4",
                    "task": "deep_research",
                    "model_id": "mimo-v2",
                    "outcome": "failed",
                    "score": 0.3,
                },
            ],
            "models": [
                {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.5},
                {"model_id": "mimo-v2", "projected_cost_usd_high": 0.1},
            ],
            "daily_cap_usd": 20,
            "spent_usd": 5,
            "projected_cost_usd_high": 0.5,
            "existing_tasks": ["deep_research"],
        },
        "mo_pack": {
            "mo": mo["mo"],
            "research_pack": mo["research_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/antiek-bench-recommend-mo-unattended/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_router_authorized"] is False
    assert body["suite_rewritten"] is False
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "antiek_bench_recommend_mo_unattended_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/antiek-bench-recommend-mo-unattended/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_router_authorized"] is False


def test_compose_route_session_mismatch_blocks():
    c = _client()
    payload = _payload(operator_ack=True, session_id="sess-1")
    payload["mo_pack"]["research_pack"]["sources"]["session_id"] = "sess-other"
    r = c.post(
        "/research/antiek-bench-recommend-mo-unattended/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_execution_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/antiek-bench-recommend-mo-unattended/compose",
        json=payload,
    )
    assert r.status_code == 422
