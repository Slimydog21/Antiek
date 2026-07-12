"""Route tests for Antiek-bench weekly + HTML-native recursive twin pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.antiek_bench_weekly_html_native_recursive_twin_compose_routes import (
    register_antiek_bench_weekly_html_native_recursive_twin_compose_routes,
)
from tests.test_html_native_recursive_twin_settings_fullscreen_mo_compose_routes import (
    _payload as _hp_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_antiek_bench_weekly_html_native_recursive_twin_compose_routes(app)
    return TestClient(app)


def _weekly_learn(*, min_events_per_task: int = 2) -> dict:
    return {
        "week_id": "2026-W28",
        "min_events_per_task": min_events_per_task,
        "events": [
            {
                "event_id": "e1",
                "task": "deep_research",
                "model_id": "gpt-5",
                "outcome": "failed",
            },
            {
                "event_id": "e2",
                "task": "deep_research",
                "model_id": "gpt-5",
                "outcome": "failed",
            },
            {
                "event_id": "e3",
                "task": "twin_notes",
                "model_id": "claude",
                "outcome": "worked",
            },
            {
                "event_id": "e4",
                "task": "twin_notes",
                "model_id": "claude",
                "outcome": "worked",
            },
        ],
    }


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    hp = _hp_payload(operator_ack=operator_ack, session_id=session_id)
    return {
        "weekly_learn": _weekly_learn(),
        "html_pack": {
            "html_view": hp["html_view"],
            "twin_pack": hp["twin_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/antiek-bench-weekly-html-native-recursive-twin/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["learn_ready"] is True
    assert body["backlog_mutated"] is False
    assert body["store_mutated"] is False
    assert body["suite_rewritten"] is False
    assert body["pdf_view_authorized"] is False
    assert body["pdf_primary"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "antiek_bench_weekly_html_native_recursive_twin_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/antiek-bench-weekly-html-native-recursive-twin/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["suite_rewritten"] is False


def test_compose_route_session_mismatch_blocks():
    c = _client()
    payload = _payload(operator_ack=True, session_id="sess-1")
    payload["html_pack"]["html_view"]["session_id"] = "sess-other"
    r = c.post(
        "/research/antiek-bench-weekly-html-native-recursive-twin/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["twin_written"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/antiek-bench-weekly-html-native-recursive-twin/compose",
        json=payload,
    )
    assert r.status_code == 422
