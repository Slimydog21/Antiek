"""Route tests for Antiek-bench weekly learn over source-attach write twin pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    register_antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes,
)
from tests.test_antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    SOURCE_PACK,
    WEEKLY_LEARN,
)
from tests.test_source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    SOURCES,
    WRITE_PACK,
)

_PATH = "/research/antiek-bench-weekly-src-write-fs-draft-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "weekly_learn": WEEKLY_LEARN,
        "source_pack": SOURCE_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["learn_ready"] is True
    assert body["attach_ready"] is True
    assert body["session_aligned"] is True
    assert body["parent_aligned"] is True
    assert body["weekly_learn"]["learn_ready"] is True
    assert body["source_pack"]["pack_ready"] is True
    assert body["backlog_mutated"] is False
    assert body["store_mutated"] is False
    assert body["suite_rewritten"] is False
    assert body["remote_fetched"] is False
    assert body["pdf_primary"] is False
    assert body["draft_written"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["backlog_mutated"] is False
    assert body["remote_fetched"] is False
    assert body["suite_rewritten"] is False


def test_compose_route_session_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["source_pack"] = {
        "sources": {**SOURCES, "session_id": "sess-other"},
        "write_pack": WRITE_PACK,
    }
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_aligned"] is False
    assert body["pack_ready"] is False
    assert body["remote_fetched"] is False
    assert body["backlog_mutated"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
