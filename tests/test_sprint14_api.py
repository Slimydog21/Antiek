"""Tests for Sprint 14 API additions: blocks/search, sections/reorder-block,
sources/twitter, source-kind detection for twitter URLs."""

from __future__ import annotations

import os
import sys
import tempfile
from typing import List

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.app import _detect_source_kind


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-sprint14-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


def _client(temp_substrate):
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────
# 1. Source-kind detection: twitter
# ─────────────────────────────────────────────────────────────────────


def test_detect_source_kind_twitter():
    assert _detect_source_kind("https://x.com/foo/status/1234") == "twitter"
    assert _detect_source_kind("https://twitter.com/foo/status/1234") == "twitter"


def test_ingest_twitter_url_returns_extension_guidance(temp_substrate):
    """The /sources/ingest endpoint for kind=twitter must reject and
    point the operator at the browser extension."""
    client = _client(temp_substrate)
    resp = client.post("/sources/ingest", json={
        "url": "https://x.com/foo/status/1234",
    })
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "error"
    assert body["detected_kind"] == "twitter"
    assert "extension" in (body["error_message"] or "").lower()


# ─────────────────────────────────────────────────────────────────────
# 2. POST /sources/twitter (extension entry point)
# ─────────────────────────────────────────────────────────────────────


def _good_thread_payload(thread_id: str = "1234") -> dict:
    return {
        "thread_url": f"https://x.com/foo/status/{thread_id}",
        "root_tweet_id": thread_id,
        "author_handle": "foo",
        "tweets": [
            {
                "tweet_id": thread_id,
                "text": "Long-enough first tweet about substrate compounding mechanics.",
                "author_handle": "foo",
            },
            {
                "tweet_id": f"{thread_id}-r",
                "text": "And the second tweet explaining the multiplicative case.",
                "author_handle": "foo",
                "reply_to": thread_id,
            },
        ],
    }


def test_post_twitter_thread_happy(temp_substrate):
    client = _client(temp_substrate)
    resp = client.post("/sources/twitter", json=_good_thread_payload())
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "ingested"
    assert body["document_id"].startswith("doc-x-")
    assert body["chunks_written"] == 2
    assert "Thread by @foo" in (body["title"] or "")


def test_post_twitter_empty_tweets_422(temp_substrate):
    client = _client(temp_substrate)
    resp = client.post("/sources/twitter", json={
        "thread_url": "https://x.com/foo/status/1",
        "root_tweet_id": "1",
        "author_handle": "foo",
        "tweets": [],
    })
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# 3. GET /blocks/search
# ─────────────────────────────────────────────────────────────────────


def test_blocks_search_returns_empty_when_no_nodes(temp_substrate):
    client = _client(temp_substrate)
    resp = client.get("/blocks/search?q=anything")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0


def test_blocks_search_finds_inserted_nodes(temp_substrate):
    """Seed two nodes via graph ops, then search for one of them."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_node
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test-seed") as con:
        insert_node(
            con, canonical_label="substrate compounding mechanics",
            node_type="entity", graph_scope="cross_domain",
            investigation_id="inv-seed",
        )
        insert_node(
            con, canonical_label="market microstructure",
            node_type="entity", graph_scope="cross_domain",
            investigation_id="inv-seed",
        )

    client = _client(temp_substrate)
    resp = client.get("/blocks/search?q=substrate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert "substrate" in body["hits"][0]["label"]


def test_blocks_search_empty_query_returns_all(temp_substrate):
    """Empty q returns the most recent nodes, capped at limit."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_node
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test-seed") as con:
        for i in range(5):
            insert_node(
                con, canonical_label=f"node {i}",
                node_type="entity", graph_scope="cross_domain",
                investigation_id="inv-seed",
            )

    client = _client(temp_substrate)
    resp = client.get("/blocks/search?q=&limit=3")
    body = resp.json()
    assert body["count"] == 3


# ─────────────────────────────────────────────────────────────────────
# 4. POST /sections/reorder-block
# ─────────────────────────────────────────────────────────────────────


def _make_section_with_block(client) -> tuple[str, str]:
    """Create deliverable + section + attached block; return (sid, bid)."""
    d = client.post("/deliverables", json={
        "title": "Memo", "deliverable_kind": "research_memo",
    }).json()
    s = client.post("/sections", json={
        "deliverable_id": d["deliverable_id"], "section_index": 0,
        "title": "Intro",
    }).json()
    client.post("/sections/attach-block", json={
        "section_id": s["section_id"],
        "block_kind": "insight",
        "block_id": "node-A",
        "block_index": 0,
    })
    return s["section_id"], "node-A"


def test_reorder_block_in_section(temp_substrate):
    """In-section reorder: bump block_index, verify via direct DuckDB."""
    import duckdb
    client = _client(temp_substrate)
    sid, bid = _make_section_with_block(client)
    resp = client.post("/sections/reorder-block", json={
        "section_id": sid,
        "block_kind": "insight",
        "block_id": bid,
        "new_block_index": 7,
    })
    assert resp.status_code == 202
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (idx,) = con.execute(
            "SELECT block_index FROM section_blocks "
            "WHERE section_id = ? AND block_id = ?", [sid, bid],
        ).fetchone()
    finally:
        con.close()
    assert idx == 7


def test_reorder_block_to_new_section(temp_substrate):
    """Move a block to a different section in the same deliverable."""
    import duckdb
    client = _client(temp_substrate)
    sid, bid = _make_section_with_block(client)
    # Add a second section
    d = client.get("/deliverables").json()["deliverables"][0]
    s2 = client.post("/sections", json={
        "deliverable_id": d["deliverable_id"], "section_index": 1,
        "title": "Body",
    }).json()
    resp = client.post("/sections/reorder-block", json={
        "section_id": sid,
        "block_kind": "insight",
        "block_id": bid,
        "new_section_id": s2["section_id"],
        "new_block_index": 0,
    })
    assert resp.status_code == 202
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        old = con.execute(
            "SELECT 1 FROM section_blocks WHERE section_id = ? "
            "AND block_id = ?", [sid, bid],
        ).fetchone()
        new = con.execute(
            "SELECT block_index FROM section_blocks WHERE section_id = ? "
            "AND block_id = ?", [s2["section_id"], bid],
        ).fetchone()
    finally:
        con.close()
    assert old is None
    assert new is not None and new[0] == 0


def test_reorder_block_target_section_not_found_404(temp_substrate):
    client = _client(temp_substrate)
    resp = client.post("/sections/reorder-block", json={
        "section_id": "sec-x",
        "block_kind": "insight",
        "block_id": "node-A",
        "new_section_id": "sec-nope",
        "new_block_index": 0,
    })
    assert resp.status_code == 404
