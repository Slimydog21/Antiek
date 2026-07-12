"""Route tests for draft-before-merge + collective multiselect floating DR MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    register_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes,
)
from tests.test_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    COLLECTIVE_PACK,
    DRAFT_GATE,
)


def _client() -> TestClient:
    app = FastAPI()
    register_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "draft_gate": DRAFT_GATE,
        "collective_pack": COLLECTIVE_PACK,
        "operator_ack": operator_ack,
    }


_PATH = (
    "/research/draft-before-merge-collective-floating-dr-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack/compose"
)


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["draft_gate"]["gate_ready"] is True
    assert body["collective_pack"]["pack_ready"] is True
    assert body["session_aligned"] is True
    assert body["parent_aligned"] is True
    assert body["draft_written"] is False
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False
    assert body["pack_dispatched"] is False
    assert body["analysis_written"] is False
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["draft_written"] is False
    assert body["merge_executed"] is False


def test_compose_route_session_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["draft_gate"] = {**DRAFT_GATE, "session_id": "sess-other"}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_aligned"] is False
    assert body["pack_ready"] is False
    assert body["draft_written"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
