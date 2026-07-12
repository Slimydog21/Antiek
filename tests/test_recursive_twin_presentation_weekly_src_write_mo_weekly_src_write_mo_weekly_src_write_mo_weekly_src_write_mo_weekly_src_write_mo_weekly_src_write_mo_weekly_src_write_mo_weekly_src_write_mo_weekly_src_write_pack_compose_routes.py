"""Route tests for recursive twin presentation over weekly source-attach write twin."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    register_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes,
)
from tests.test_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    PRESENTATION,
    TWIN,
    WEEKLY_PACK,
)

_PATH = (
    "/research/recursive-twin-presentation-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack/compose"
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "twin": TWIN,
        "presentation": PRESENTATION,
        "weekly_pack": WEEKLY_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["presentation"]["presentation_ready"] is True
    assert body["weekly_pack"]["pack_ready"] is True
    assert body["weekly_pack"]["learn_ready"] is True
    assert body["parent_aligned"] is True
    assert body["session_aligned"] is True
    assert body["twin_written"] is False
    assert body["backlog_mutated"] is False
    assert body["suite_rewritten"] is False
    assert body["remote_fetched"] is False
    assert body["pdf_primary"] is False
    assert body["draft_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["twin_written"] is False
    assert body["backlog_mutated"] is False
    assert body["remote_fetched"] is False


def test_compose_route_open_requested_false():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["presentation"] = {**PRESENTATION, "open_requested": False}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["presentation"]["presentation_ready"] is False
    assert body["pack_ready"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
