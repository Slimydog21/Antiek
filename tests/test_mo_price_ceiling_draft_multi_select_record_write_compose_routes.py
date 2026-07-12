"""Route tests for MO price-ceiling + draft multi-select record write pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.mo_price_ceiling_draft_multi_select_record_write_compose_routes import (
    register_mo_price_ceiling_draft_multi_select_record_write_compose_routes,
)
from tests.test_draft_before_merge_multi_select_record_write_compose_routes import (
    _payload as _dm_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_mo_price_ceiling_draft_multi_select_record_write_compose_routes(app)
    return TestClient(app)


def _payload(
    *,
    operator_ack: bool = True,
    stage: str = "recommend_only",
    price_ceiling_ack: bool = True,
) -> dict:
    dm = _dm_payload(operator_ack=operator_ack)
    return {
        "mo": {
            "operator_id": "op-1",
            "work_minutes": 120,
            "goals": [
                {"goal_id": "g1", "title": "Map scaling literature"},
                {"goal_id": "g2", "title": "Synthesize open problems"},
            ],
            "usd_per_hour": 30,
            "price_ceiling_ack": price_ceiling_ack,
            "stage": stage,
            "approved_ceiling_usd": 60 if stage != "recommend_only" else None,
        },
        "draft_multi": {
            "draft_gate": dm["draft_gate"],
            "multi_pack": dm["multi_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/mo-price-ceiling-draft-multi-select-record-write/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["draft_written"] is False
    assert body["merge_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "mo_price_ceiling_draft_multi_select_record_write_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/mo-price-ceiling-draft-multi-select-record-write/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["charge_executed"] is False


def test_compose_route_approve_without_ceiling_ack_blocks():
    c = _client()
    r = c.post(
        "/research/mo-price-ceiling-draft-multi-select-record-write/compose",
        json=_payload(
            operator_ack=True,
            stage="approve_ceiling",
            price_ceiling_ack=False,
        ),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_execution_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/mo-price-ceiling-draft-multi-select-record-write/compose",
        json=payload,
    )
    assert r.status_code == 422
