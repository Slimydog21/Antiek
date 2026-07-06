"""GF-5/GF-6 activation — the supersession review API (GET candidates, POST review).

Exercises the supersession router in isolation against a temp DuckDB seeded with
one live contradiction (via the production detection path), so the review queue
is non-empty. Verifies the end-to-end loop this codebase demands: detection
(wired in extract.py) produces a candidate the reviewer can SEE (GET, with both
edges resolved to labels) and ACT on (POST -> apply_review, the only
edge-mutating path), and the closed four-decision set + idempotency are enforced.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.supersession_routes import supersession_router  # noqa: E402
from processing.extraction.extract import _run_supersession_detection  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph.ops import insert_edge, insert_node  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    db_path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(db_path)
    with connect_write(db_path, purpose="test.seed") as con:
        s = insert_node(con, canonical_label="Source", node_type="entity",
                        graph_scope="depth", investigation_id="inv-1")
        t1 = insert_node(con, canonical_label="OldTarget", node_type="entity",
                         graph_scope="depth", investigation_id="inv-1")
        t2 = insert_node(con, canonical_label="NewTarget", node_type="entity",
                         graph_scope="depth", investigation_id="inv-1")
        insert_edge(con, source_node_id=s, target_node_id=t1, relation="is",
                    source_tier=1, extraction_confidence=1.0,
                    graph_scope="depth", investigation_id="inv-1",
                    edge_id="e-old", valid_from=datetime(2020, 1, 1))
        insert_edge(con, source_node_id=s, target_node_id=t2, relation="is",
                    source_tier=1, extraction_confidence=1.0,
                    graph_scope="depth", investigation_id="inv-1",
                    edge_id="e-new", valid_from=datetime(2021, 1, 1))
    _run_supersession_detection(db_path, ["e-new"])
    app = FastAPI()
    app.include_router(supersession_router)
    return TestClient(app)


def _first_candidate_id(c: TestClient) -> str:
    return c.get("/supersession/candidates").json()["candidates"][0]["candidate_id"]


def test_list_candidates_returns_resolved_edges(client: TestClient) -> None:
    resp = client.get("/supersession/candidates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    cand = body["candidates"][0]
    assert cand["status"] == "open"
    assert cand["old_edge_id"] == "e-old"
    assert cand["new_edge_id"] == "e-new"
    assert cand["old_edge"]["relation"] == "is"
    assert cand["old_edge"]["source_label"] == "Source"
    assert cand["old_edge"]["target_label"] == "OldTarget"
    assert cand["new_edge"]["target_label"] == "NewTarget"


def test_review_applies_decision_and_moves_to_reviewed(client: TestClient) -> None:
    cid = _first_candidate_id(client)
    resp = client.post(
        f"/supersession/{cid}/review",
        json={"decision": "dismiss_new", "reviewer": "op", "review_notes": "typo"},
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["status"] == "reviewed"
    assert out["decision"] == "dismiss_new"
    assert client.get("/supersession/candidates?status=open").json()["count"] == 0
    assert client.get("/supersession/candidates?status=reviewed").json()["count"] == 1


def test_review_unknown_candidate_is_404(client: TestClient) -> None:
    resp = client.post(
        "/supersession/no-such-candidate/review", json={"decision": "coexist"}
    )
    assert resp.status_code == 404


def test_review_rejects_invalid_decision(client: TestClient) -> None:
    cid = _first_candidate_id(client)
    resp = client.post(f"/supersession/{cid}/review", json={"decision": "BOGUS"})
    assert resp.status_code == 400


def test_review_twice_is_409(client: TestClient) -> None:
    cid = _first_candidate_id(client)
    assert client.post(f"/supersession/{cid}/review", json={"decision": "coexist"}).status_code == 200
    assert client.post(f"/supersession/{cid}/review", json={"decision": "coexist"}).status_code == 409


def test_list_rejects_bad_status(client: TestClient) -> None:
    assert client.get("/supersession/candidates?status=bogus").status_code == 400
