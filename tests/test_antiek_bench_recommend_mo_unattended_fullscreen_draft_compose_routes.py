"""Route tests for Antiek-bench recommend + MO unattended fullscreen draft pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.antiek_bench_recommend_mo_unattended_fullscreen_draft_compose_routes import (
    register_antiek_bench_recommend_mo_unattended_fullscreen_draft_compose_routes,
)
from tests.test_antiek_bench_recommend_mo_unattended_fullscreen_draft_compose import (
    BENCH,
    MO_PACK,
)


def _client() -> TestClient:
    app = FastAPI()
    register_antiek_bench_recommend_mo_unattended_fullscreen_draft_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "bench": BENCH,
        "mo_pack": MO_PACK,
        "operator_ack": operator_ack,
    }


_PATH = "/research/antiek-bench-recommend-mo-unattended-fullscreen-draft/compose"


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["bench"]["pack_ready"] is True
    assert body["mo_pack"]["pack_ready"] is True
    assert body["operator_id"] == "op-1"
    assert body["live_router_authorized"] is False
    assert body["suite_rewritten"] is False
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["draft_written"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "antiek_bench_recommend_mo_unattended_fullscreen_draft_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_router_authorized"] is False
    assert body["live_execution_authorized"] is False


def test_compose_route_unattended_ack_false():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["mo_pack"] = {
        **MO_PACK,
        "mo": {**MO_PACK["mo"], "unattended_ack": False},
    }
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mo_pack"]["pack_ready"] is False
    assert body["pack_ready"] is False
    assert body["live_execution_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
