"""Route tests for collective presented twins + paid ND pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.collective_presented_twins_paid_nd_compose_routes import (
    register_collective_presented_twins_paid_nd_compose_routes,
)
from tests.test_paid_purchase_nd_shadow_twin_presentation_compose_routes import (
    _payload as _paid_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_collective_presented_twins_paid_nd_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    paid = _paid_payload(operator_ack=operator_ack)
    return {
        "collective": {
            "session_id": "sess-1",
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
            "cohesive_prompt": (
                "Synthesize presented twin instances A and B as one unit"
            ),
        },
        "paid_nd": {
            "purchase": paid["purchase"],
            "nd_twin": paid["nd_twin"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/collective-presented-twins-paid-nd/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["purchase_executed"] is False
    assert body["live_router_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "collective_presented_twins_paid_nd_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/collective-presented-twins-paid-nd/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_dispatched"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/collective-presented-twins-paid-nd/compose",
        json=payload,
    )
    assert r.status_code == 422
