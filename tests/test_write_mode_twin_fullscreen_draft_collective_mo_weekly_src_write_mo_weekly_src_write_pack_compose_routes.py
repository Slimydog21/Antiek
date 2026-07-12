"""Route tests for write twin collective over fullscreen draft-before-merge pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    register_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes,
)
from tests.test_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    FULLSCREEN_PACK,
    WRITE,
)


def _client() -> TestClient:
    app = FastAPI()
    register_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "write": WRITE,
        "fullscreen_pack": FULLSCREEN_PACK,
        "operator_ack": operator_ack,
    }


_PATH = "/research/write-mode-twin-fullscreen-draft-collective-mo-weekly-src-write-mo-weekly-src-write-pack/compose"


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["write"]["pack_ready"] is True
    assert body["fullscreen_pack"]["pack_ready"] is True
    assert body["session_aligned"] is True
    assert body["parent_aligned"] is True
    assert body["draft_written"] is False
    assert body["analysis_written"] is False
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False
    assert body["live_execution_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["draft_written"] is False
    assert body["analysis_written"] is False


def test_compose_route_session_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["write"] = {**WRITE, "session_id": "sess-other"}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_aligned"] is False
    assert body["pack_ready"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
