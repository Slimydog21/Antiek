"""Link Monster — graph stew tests (temp substrate DB).

Mirrors the acquisition adapter test pattern: a tmp DuckDB + events dir
via env vars, a deterministic stub embedder, and assertions on the rows
+ events actually written. No network is touched (store_digest takes a
prebuilt LinkDigest).
"""

from __future__ import annotations

import json
import os
import tempfile

import duckdb
import pytest

from acquisition.link_monster.digest import LinkDigest, TextInfo
from acquisition.link_monster.store import (
    get_digest,
    link_monster_doc_id,
    list_digests,
    store_digest,
)


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-lm-test-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


def _meal_digest(final_url: str = "https://www.example.com/post/1") -> LinkDigest:
    return LinkDigest(
        url=final_url,
        final_url=final_url,
        platform="generic",
        platform_label="Web",
        title="OG Title",
        author="Jane Researcher",
        author_url=None,
        published_at=None,
        description="A description.",
        site_name="Example Site",
        thumbnail_url="https://img.example.com/cover.jpg",
        image_urls=["https://img.example.com/cover.jpg"],
        video=None,
        transcript=None,
        text=TextInfo(
            markdown=(
                "# OG Title\n\nThis is a substantive article body with enough words "
                "to clear the chunker's minimum threshold. It discusses knowledge "
                "graphs, provenance, and the value of compounding notes across "
                "investigations over time."
            ),
            chars=230,
            word_count=38,
            source="dom",
        ),
        provenance={"title": "og", "text": "dom"},
        outcome="meal",
        artifacts={"images": 1, "videos": 0, "transcript_chars": 0, "text_chars": 230, "body_chars": 230},
    )


def test_store_meal_writes_rows(temp_substrate):
    digest = _meal_digest()
    res = store_digest(digest, db_path=temp_substrate["db_path"], emb=_StubEmbedder())
    assert res.document_id == link_monster_doc_id(digest.final_url)
    assert res.chunks_written >= 1
    assert res.node_ids and res.edge_ids
    assert res.content_class == "personal_reading"  # deny-by-default rights

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?", [res.document_id]
        ).fetchone()
        (chunk_count,) = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", [res.document_id]
        ).fetchone()
        (node_count,) = con.execute(
            "SELECT COUNT(*) FROM nodes WHERE node_id IN (" + ", ".join("?" for _ in res.node_ids) + ")",
            res.node_ids,
        ).fetchone()
        (edge_count,) = con.execute(
            "SELECT COUNT(*) FROM edges WHERE edge_id IN (" + ", ".join("?" for _ in res.edge_ids) + ")",
            res.edge_ids,
        ).fetchone()
        (class_row,) = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?", [res.document_id]
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1
    assert chunk_count == res.chunks_written
    assert node_count == len(res.node_ids)
    assert edge_count == len(res.edge_ids)
    assert class_row == "personal_reading"


def test_store_dedup_idempotent(temp_substrate):
    digest = _meal_digest()
    r1 = store_digest(digest, db_path=temp_substrate["db_path"], emb=_StubEmbedder())
    r2 = store_digest(digest, db_path=temp_substrate["db_path"], emb=_StubEmbedder())
    assert r1.document_id == r2.document_id
    assert r2.already_digested is True
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (n,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?", [r1.document_id]
        ).fetchone()
    finally:
        con.close()
    assert n == 1  # no duplicate rows


def test_store_metadata_roundtrip_and_feed(temp_substrate):
    digest = _meal_digest()
    res = store_digest(digest, db_path=temp_substrate["db_path"], emb=_StubEmbedder())
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (meta_raw,) = con.execute(
            "SELECT metadata FROM documents WHERE document_id = ?", [res.document_id]
        ).fetchone()
    finally:
        con.close()
    meta = json.loads(meta_raw)
    assert meta["platform"] == "generic"
    assert meta["outcome"] == "meal"
    assert meta["title"] == "OG Title"
    assert meta["digested_at"] is not None

    feed = list_digests(db_path=temp_substrate["db_path"])
    assert len(feed) == 1
    assert feed[0]["document_id"] == res.document_id
    assert feed[0]["digest"]["platform"] == "generic"

    detail = get_digest(res.document_id, db_path=temp_substrate["db_path"])
    assert detail is not None
    assert detail["chunks"]  # chunk summary present
    assert detail["neighbors"]  # author/publisher nodes reachable
    assert "raw_text" not in detail  # body only via the sanctioned serve gate
    assert detail["metadata"]["title"] == "OG Title"


def test_store_authorless_meal_gets_published_edge(temp_substrate):
    """No author meta → publisher→title 'published' edge (traversable)."""
    digest = LinkDigest(
        url="https://www.example.com/noauthor",
        final_url="https://www.example.com/noauthor",
        platform="generic",
        platform_label="Web",
        title="An Authorless Page",
        author=None,
        author_url=None,
        published_at=None,
        description=None,
        site_name="Example Site",
        thumbnail_url=None,
        image_urls=[],
        video=None,
        transcript=None,
        text=TextInfo(
            markdown="# An Authorless Page\n\nSome substantive body text with enough words to clear the chunker minimum threshold for this test fixture.",
            chars=140,
            word_count=22,
            source="dom",
        ),
        provenance={"title": "og", "text": "dom"},
        outcome="meal",
        artifacts={"images": 0, "videos": 0, "transcript_chars": 0, "text_chars": 140, "body_chars": 140},
    )
    res = store_digest(digest, db_path=temp_substrate["db_path"], emb=_StubEmbedder())
    assert res.edge_ids  # at least the published edge
    assert res.node_ids
