"""Tests for SPR-04 M3 — full-text index for a stored T1 body.

The index path reuses ``chunk_markdown`` + ``insert_chunk`` and an injected
``EmbeddingModel`` Protocol (a deterministic fake — no sentence-transformers).
Asserted: a non-empty body yields chunks with embeddings; an empty body is a
defensive no-op; re-indexing the same body is idempotent (content-addressed
chunk ids → no duplicates).
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.index import index_body  # noqa: E402
from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.graph.ops import insert_document  # noqa: E402

_BODY = "# A Paper\n\nThis is the body of an open paper. " * 30


class _StubEmbedder:
    dimension = 16

    def __init__(self) -> None:
        self.calls = 0

    def encode(self, text: str) -> list[float]:
        self.calls += 1
        v = [0.0] * 16
        v[abs(hash(text)) % 16] = 1.0
        return v


@pytest.fixture
def temp_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr04-index-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    ensure_initialized(db_path)
    yield db_path


def _insert_doc(db_path: str, document_id: str) -> None:
    with connect_write(db_path, purpose="test/index") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=3,
            document_type="academic_paper",
            on_conflict="ignore",
        )


def test_index_body_writes_embedded_chunks(temp_db):
    doc_id = "doc-arxiv-2402-80001"
    _insert_doc(temp_db, doc_id)
    emb = _StubEmbedder()

    with connect_write(temp_db, purpose="test/index") as con:
        chunk_ids = index_body(con, document_id=doc_id, body=_BODY, embedder=emb)

    assert len(chunk_ids) > 0
    assert emb.calls == len(chunk_ids)
    with connect_read(temp_db) as con:
        rows = con.execute(
            "SELECT embedding FROM chunks WHERE document_id = ?", [doc_id]
        ).fetchall()
    assert len(rows) == len(chunk_ids)
    assert all(r[0] is not None for r in rows)  # embeddings stored


def test_index_empty_body_is_noop(temp_db):
    doc_id = "doc-arxiv-2402-80002"
    _insert_doc(temp_db, doc_id)
    with connect_write(temp_db, purpose="test/index") as con:
        assert index_body(con, document_id=doc_id, body="   ", embedder=_StubEmbedder()) == []
        assert index_body(con, document_id=doc_id, body="", embedder=_StubEmbedder()) == []
    with connect_read(temp_db) as con:
        n = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", [doc_id]
        ).fetchone()[0]
    assert n == 0


def test_reindex_is_idempotent(temp_db):
    doc_id = "doc-arxiv-2402-80003"
    _insert_doc(temp_db, doc_id)
    with connect_write(temp_db, purpose="test/index") as con:
        ids1 = index_body(con, document_id=doc_id, body=_BODY, embedder=_StubEmbedder())
    with connect_write(temp_db, purpose="test/index") as con:
        ids2 = index_body(con, document_id=doc_id, body=_BODY, embedder=_StubEmbedder())
    assert ids1 == ids2
    with connect_read(temp_db) as con:
        n = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", [doc_id]
        ).fetchone()[0]
    assert n == len(ids1)  # no duplicates
