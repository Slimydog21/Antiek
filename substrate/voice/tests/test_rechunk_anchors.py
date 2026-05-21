"""Tests for substrate/voice/workers/rechunk_anchors.py (SPR-02).

Confirms:
  - Stale anchors (chunker_version != current) are re-resolved.
  - Idempotency: a second run is a no-op.
  - --document-id scoping filters correctly.
  - The chunk_id update reflects the live resolver geometry (via
    a monkeypatched candidate-chunks function).
"""

from __future__ import annotations

import os
import sys

import duckdb
import pytest

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402
from substrate.voice import CHUNKER_VERSION  # noqa: E402
from substrate.voice.anchor_api import BBox, create_anchor  # noqa: E402
from substrate.voice.migrate import apply_at_path  # noqa: E402
from substrate.voice.workers.rechunk_anchors import (  # noqa: E402
    rechunk,
    rechunk_at_path,
)


@pytest.fixture
def db_path(tmp_path) -> str:
    p = str(tmp_path / "graph.duckdb")
    init_database_at_path(p)
    apply_at_path(p)
    return p


def _insert_document(con, *, document_id: str, document_type: str = "pdf") -> None:
    con.execute(
        "INSERT INTO documents "
        "(document_id, source_tier, document_type, title) "
        "VALUES (?, ?, ?, ?)",
        [document_id, 2, document_type, f"Test doc {document_id}"],
    )


def _force_stale_version(con, anchor_id: str, old_version: str = "0.0.1") -> None:
    """Rewrite chunker_version directly to simulate a chunker
    upgrade between the original write and now."""
    con.execute(
        "UPDATE voice_note_anchor SET chunker_version = ? "
        "WHERE anchor_id = ?",
        [old_version, anchor_id],
    )


def test_rechunk_updates_stale_anchor(db_path):
    with connect_write(db_path, purpose="test-seed") as con:
        _insert_document(con, document_id="doc-src-1")
        _insert_document(
            con, document_id="doc-vn-1", document_type="voice_note",
        )
        a = create_anchor(
            con, voice_note_id="doc-vn-1", document_id="doc-src-1",
            page=0, bbox=BBox(0, 0, 100, 100),
        )
        # Simulate "this row predates the current chunker".
        _force_stale_version(con, a.anchor_id, old_version="0.0.1")

    with connect_write(db_path, purpose="test-rechunk") as con:
        summary = rechunk(con)

    assert summary.scanned == 1
    assert summary.stale_before == 1
    assert summary.updated == 1
    # chunk_id_changed depends on whether the (old → new) chunk_id
    # changed. In the current substrate the resolver returns None
    # both times, so chunk_id_changed should be 0 here.
    assert summary.chunk_id_changed == 0

    con = duckdb.connect(db_path, read_only=True)
    try:
        row = con.execute(
            "SELECT chunker_version FROM voice_note_anchor "
            "WHERE anchor_id = ?",
            [a.anchor_id],
        ).fetchone()
    finally:
        con.close()
    assert row[0] == CHUNKER_VERSION


def test_rechunk_idempotent(db_path):
    """Run rechunk twice. Second run is a no-op (zero stale)."""
    with connect_write(db_path, purpose="test-seed") as con:
        _insert_document(con, document_id="doc-src-1")
        _insert_document(
            con, document_id="doc-vn-1", document_type="voice_note",
        )
        a = create_anchor(
            con, voice_note_id="doc-vn-1", document_id="doc-src-1",
            page=0, bbox=BBox(0, 0, 100, 100),
        )
        _force_stale_version(con, a.anchor_id, old_version="0.0.1")

    s1 = rechunk_at_path(db_path)
    s2 = rechunk_at_path(db_path)

    assert s1.updated == 1
    assert s2.scanned == 1
    assert s2.stale_before == 0
    assert s2.updated == 0
    assert s2.chunk_id_changed == 0


def test_rechunk_scopes_to_document_id(db_path):
    with connect_write(db_path, purpose="test-seed") as con:
        _insert_document(con, document_id="doc-src-1")
        _insert_document(con, document_id="doc-src-2")
        _insert_document(
            con, document_id="doc-vn-1", document_type="voice_note",
        )
        _insert_document(
            con, document_id="doc-vn-2", document_type="voice_note",
        )
        a1 = create_anchor(
            con, voice_note_id="doc-vn-1", document_id="doc-src-1",
            page=0, bbox=BBox(0, 0, 10, 10),
        )
        a2 = create_anchor(
            con, voice_note_id="doc-vn-2", document_id="doc-src-2",
            page=0, bbox=BBox(0, 0, 10, 10),
        )
        _force_stale_version(con, a1.anchor_id, old_version="0.0.1")
        _force_stale_version(con, a2.anchor_id, old_version="0.0.1")

    summary = rechunk_at_path(db_path, document_id="doc-src-1")
    assert summary.scanned == 1
    assert summary.updated == 1

    # a2 is still stale because it was scoped out.
    con = duckdb.connect(db_path, read_only=True)
    try:
        v1, v2 = con.execute(
            "SELECT anchor_id, chunker_version FROM voice_note_anchor "
            "ORDER BY anchor_id"
        ).fetchall()
    finally:
        con.close()
    versions = {v1[0]: v1[1], v2[0]: v2[1]}
    assert versions[a1.anchor_id] == CHUNKER_VERSION
    assert versions[a2.anchor_id] == "0.0.1"


def test_rechunk_changes_chunk_id_when_geometry_moves(monkeypatch, db_path):
    """Inject two different candidate-chunks tables: one used at
    initial write, then a 'new chunker' table used by the worker.
    The chunk_id moves from the old argmax to the new argmax.
    """
    from substrate.voice import anchor_api

    # Initial geometry: chunk OLD covers 60% of the anchor.
    def initial_candidates(con, document_id, page):
        return [("OLD", BBox(0, 0, 60, 100))]

    monkeypatch.setattr(
        anchor_api, "_candidate_chunks_for_overlap", initial_candidates,
    )

    with connect_write(db_path, purpose="test-seed") as con:
        _insert_document(con, document_id="doc-src-1")
        _insert_document(
            con, document_id="doc-vn-move", document_type="voice_note",
        )
        # We need OLD and NEW to be valid chunks table rows for the
        # FK to accept. Seed them via raw INSERT.
        for cid in ("OLD", "NEW"):
            con.execute(
                "INSERT INTO chunks "
                "(chunk_id, document_id, chunk_index, text) "
                "VALUES (?, ?, ?, ?)",
                [cid, "doc-src-1", 0, "stub text"],
            )
        a = create_anchor(
            con, voice_note_id="doc-vn-move", document_id="doc-src-1",
            page=0, bbox=BBox(0, 0, 100, 100),
        )
        # Sanity: the initial write resolved to OLD.
        row = con.execute(
            "SELECT chunk_id FROM voice_note_anchor WHERE anchor_id=?",
            [a.anchor_id],
        ).fetchone()
        assert row[0] == "OLD"
        _force_stale_version(con, a.anchor_id, old_version="0.0.1")

    # New geometry: chunk NEW covers 80% of the anchor.
    def new_candidates(con, document_id, page):
        return [("NEW", BBox(0, 0, 80, 100))]

    monkeypatch.setattr(
        anchor_api, "_candidate_chunks_for_overlap", new_candidates,
    )

    with connect_write(db_path, purpose="test-rechunk") as con:
        summary = rechunk(con)
    assert summary.updated == 1
    assert summary.chunk_id_changed == 1

    con = duckdb.connect(db_path, read_only=True)
    try:
        row = con.execute(
            "SELECT chunk_id, chunker_version FROM voice_note_anchor "
            "WHERE anchor_id = ?",
            [a.anchor_id],
        ).fetchone()
    finally:
        con.close()
    assert row[0] == "NEW"
    assert row[1] == CHUNKER_VERSION
