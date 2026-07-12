"""Route tests for write twin collective + settings draft fullscreen ND."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.write_twin_collective_settings_draft_fullscreen_nd_mo_compose_routes import (
    register_write_twin_collective_settings_draft_fullscreen_nd_mo_compose_routes,
)
from tests.test_settings_add_model_draft_fullscreen_weekly_nd_mo_compose_routes import (
    _payload as _settings_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_write_twin_collective_settings_draft_fullscreen_nd_mo_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    sp = _settings_payload(operator_ack=operator_ack)
    return {
        "write": {
            "session_id": "sess-1",
            "draft_id": "draft-1",
            "parent_asset_id": "book-1",
            "twin_slices": [
                {
                    "parent_asset_id": "asset-1",
                    "insights": ["scaling claim holds"],
                    "questions": ["Where does it break?"],
                },
                {
                    "parent_asset_id": "asset-2",
                    "insights": ["attention efficiency"],
                    "questions": [],
                },
            ],
            "base_draft_html": "<p>Opening</p>",
            "chase_slots": [
                {
                    "slot_id": "s1",
                    "question_id": "q1",
                    "parent_asset_id": "book-1",
                    "status": "completed",
                    "findings": ["finding A"],
                    "body": "Evidence?",
                },
                {
                    "slot_id": "s2",
                    "question_id": "q2",
                    "parent_asset_id": "book-1",
                    "status": "completed",
                    "findings": ["finding B"],
                    "body": "Counter?",
                },
            ],
            "analysis_kind": "draft_analysis",
        },
        "settings_research": {
            "settings": sp["settings"],
            "research_pack": sp["research_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/write-twin-collective-settings-draft-fullscreen-nd-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["draft_written"] is False
    assert body["analysis_written"] is False
    assert body["merge_executed"] is False
    assert body["secrets_stored"] is False
    assert body["inventory_mutated"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert (
        body["authority"]
        == "write_twin_collective_settings_draft_fullscreen_nd_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/write-twin-collective-settings-draft-fullscreen-nd-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["analysis_written"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/write-twin-collective-settings-draft-fullscreen-nd-mo/compose",
        json=payload,
    )
    assert r.status_code == 422
