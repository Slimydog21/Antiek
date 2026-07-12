"""Route tests for competition DR over ND shadow twin presentation weekly."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    register_competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes,
)
from tests.test_competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    COMPETITION,
    ND_PACK,
)

_PATH = "/research/competition-dr-nd-shadow-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "competition": COMPETITION,
        "nd_pack": ND_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["session_aligned"] is True
    assert body["competition"]["pack_ready"] is True
    assert body["nd_pack"]["pack_ready"] is True
    assert body["live_dispatch_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["backlog_mutated"] is False
    assert body["live_router_authorized"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_session_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["competition"] = {**COMPETITION, "session_id": "sess-other"}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_aligned"] is False
    assert body["pack_ready"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
