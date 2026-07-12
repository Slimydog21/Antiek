"""Route tests for record→prompt + HTML-native recursive twin MO pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.record_prompt_html_native_recursive_twin_mo_compose_routes import (
    register_record_prompt_html_native_recursive_twin_mo_compose_routes,
)
from tests.test_html_native_recursive_twin_mo_write_pack_compose_routes import (
    _payload as _html_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_record_prompt_html_native_recursive_twin_mo_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    hp = _html_payload(operator_ack=operator_ack)
    return {
        "record_prompt": {
            "session_id": "sess-1",
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
                },
                {
                    "model_id": "composer-2.5",
                    "tier": "workhorse",
                    "projected_cost_usd_high": 0.5,
                },
            ],
            "daily_cap_usd": 100,
            "spent_usd": 40,
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        "html_pack": {
            "html_view": hp["html_view"],
            "twin_mo": hp["twin_mo"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/record-prompt-html-native-recursive-twin-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["pdf_primary"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert (
        body["authority"]
        == "record_prompt_html_native_recursive_twin_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/record-prompt-html-native-recursive-twin-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["prompts_injected"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/record-prompt-html-native-recursive-twin-mo/compose",
        json=payload,
    )
    assert r.status_code == 422
