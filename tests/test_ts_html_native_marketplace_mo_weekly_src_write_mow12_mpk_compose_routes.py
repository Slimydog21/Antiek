"""Route tests for twin search over HTML-native marketplace MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.ts_html_native_marketplace_mo_weekly_src_write_mow12_mpk_compose_routes import (
    register_twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_mpack_compose_routes,
)
from tests.test_ts_html_native_marketplace_mo_weekly_src_write_mow12_mpk_compose import (
    HTML_PACK,
    TWIN_RECORDS,
)

_PATH = "/research/twin-search-html-native-marketplace-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mpk/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_mpack_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "search_query": "scaling noise",
        "twin_records": TWIN_RECORDS,
        "html_pack": HTML_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["hit_count"] >= 1
    assert body["html_pack"]["pack_ready"] is True
    assert body["remote_index_queried"] is False
    assert body["twin_written"] is False
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["pdf_primary"] is False
    assert body["live_execution_authorized"] is False
    assert body["charge_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["remote_index_queried"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_empty_records():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["twin_records"] = []
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hit_count"] == 0
    assert body["pack_ready"] is False
    assert body["remote_index_queried"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
