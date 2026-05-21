"""Tests for substrate/voice/anchor_api.py + migrate.py (SPR-02).

Covers the contract surface SPR-05 will rely on, plus the
concurrency invariant (rigor #3 — the unique constraint MUST live
in the DB layer, not the application layer).

Test fixture seeds a minimal documents + chunks schema via
substrate.graph.schema.init_database_at_path, then applies the
voice_note_anchor migration on top. Voice notes are written as
documents with document_type='voice_note' — matching the Sprint
13 storage shape.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import uuid
from typing import Optional

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
from substrate.voice.anchor_api import (  # noqa: E402
    BBox,
    MIN_CHUNK_OVERLAP_FRACTION,
    create_anchor,
    get_anchor_by_voice_note,
    get_anchors_on_page,
    resolve_chunk_for_bbox,
)
from substrate.voice.migrate import (  # noqa: E402
    MissingPrerequisiteError,
    apply,
    apply_at_path,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path) -> str:
    """Fresh DuckDB with documents + chunks tables AND the
    voice_note_anchor table applied. Returns the path."""
    p = str(tmp_path / "graph.duckdb")
    init_database_at_path(p)
    apply_at_path(p)
    return p


@pytest.fixture
def db_path_no_voice(tmp_path) -> str:
    """Fresh DuckDB with documents + chunks but NO voice_note_anchor
    yet (for migration tests)."""
    p = str(tmp_path / "graph.duckdb")
    init_database_at_path(p)
    return p


@pytest.fixture
def empty_db_path(tmp_path) -> str:
    """Fresh DuckDB with NO tables (for missing-prerequisite test)."""
    return str(tmp_path / "graph.duckdb")


def _insert_document(con, *, document_id: str, document_type: str = "pdf") -> None:
    """Minimal document insert. Bypasses substrate.graph.ops because
    the events_dir isn't set up in these tests — we just need a row
    the anchor FK can target."""
    con.execute(
        "INSERT INTO documents "
        "(document_id, source_tier, document_type, title) "
        "VALUES (?, ?, ?, ?)",
        [document_id, 2, document_type, f"Test doc {document_id}"],
    )


def _seed_voice_note(con, voice_note_id: str) -> None:
    _insert_document(
        con, document_id=voice_note_id, document_type="voice_note",
    )


def _seed_source_doc(con, document_id: str = "doc-src-1") -> str:
    _insert_document(con, document_id=document_id, document_type="pdf")
    return document_id


# ─────────────────────────────────────────────────────────────────────
# Migration
# ─────────────────────────────────────────────────────────────────────


def test_migration_creates_table(db_path_no_voice):
    apply_at_path(db_path_no_voice)
    con = duckdb.connect(db_path_no_voice, read_only=True)
    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name='voice_note_anchor'"
        ).fetchall()
    finally:
        con.close()
    assert rows == [("voice_note_anchor",)]


def test_migration_is_idempotent(db_path_no_voice):
    # First apply.
    apply_at_path(db_path_no_voice)
    # Second apply must succeed (no exception).
    apply_at_path(db_path_no_voice)
    con = duckdb.connect(db_path_no_voice, read_only=True)
    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name='voice_note_anchor'"
        ).fetchall()
    finally:
        con.close()
    assert rows == [("voice_note_anchor",)]


def test_migration_fails_without_documents_table(empty_db_path):
    # No init_database_at_path call — documents doesn't exist.
    with pytest.raises(MissingPrerequisiteError) as excinfo:
        apply_at_path(empty_db_path)
    # The error must point to Sprint 13 / substrate.graph.
    msg = str(excinfo.value).lower()
    assert "documents" in msg
    assert "sprint 13" in msg or "init_database" in msg


# ─────────────────────────────────────────────────────────────────────
# create_anchor + reads
# ─────────────────────────────────────────────────────────────────────


def test_create_anchor_round_trips(db_path):
    with connect_write(db_path, purpose="test") as con:
        _seed_voice_note(con, "doc-vn-aaaa")
        src = _seed_source_doc(con)
        anchor = create_anchor(
            con,
            voice_note_id="doc-vn-aaaa",
            document_id=src,
            page=3,
            bbox=BBox(x0=10, y0=20, x1=100, y1=80),
        )
    assert anchor.voice_note_id == "doc-vn-aaaa"
    assert anchor.document_id == src
    assert anchor.page == 3
    assert anchor.bbox.x0 == 10
    assert anchor.bbox.y1 == 80
    assert anchor.chunker_version == CHUNKER_VERSION
    # No bbox geometry on chunks → chunk_id NULL (documented gap).
    assert anchor.chunk_id is None
    assert anchor.anchor_id.startswith("vna-")


def test_get_anchors_on_page_after_create(db_path):
    with connect_write(db_path, purpose="test") as con:
        src = _seed_source_doc(con)
        _seed_voice_note(con, "doc-vn-1")
        _seed_voice_note(con, "doc-vn-2")
        _seed_voice_note(con, "doc-vn-3")
        create_anchor(
            con, voice_note_id="doc-vn-1", document_id=src,
            page=1, bbox=BBox(0, 0, 50, 50),
        )
        create_anchor(
            con, voice_note_id="doc-vn-2", document_id=src,
            page=1, bbox=BBox(60, 60, 100, 100),
        )
        create_anchor(
            con, voice_note_id="doc-vn-3", document_id=src,
            page=2, bbox=BBox(0, 0, 50, 50),
        )
    con = duckdb.connect(db_path, read_only=True)
    try:
        page1 = get_anchors_on_page(con, document_id=src, page=1)
        page2 = get_anchors_on_page(con, document_id=src, page=2)
        page_missing = get_anchors_on_page(con, document_id=src, page=99)
    finally:
        con.close()
    assert {a.voice_note_id for a in page1} == {"doc-vn-1", "doc-vn-2"}
    assert {a.voice_note_id for a in page2} == {"doc-vn-3"}
    assert page_missing == []


def test_get_anchor_by_voice_note_returns_none_when_missing(db_path):
    con = duckdb.connect(db_path, read_only=True)
    try:
        assert (
            get_anchor_by_voice_note(con, voice_note_id="doc-vn-unknown")
            is None
        )
    finally:
        con.close()


def test_get_anchor_by_voice_note_returns_anchor(db_path):
    with connect_write(db_path, purpose="test") as con:
        src = _seed_source_doc(con)
        _seed_voice_note(con, "doc-vn-q")
        created = create_anchor(
            con, voice_note_id="doc-vn-q", document_id=src,
            page=0, bbox=BBox(1, 1, 10, 10),
        )
    con = duckdb.connect(db_path, read_only=True)
    try:
        got = get_anchor_by_voice_note(con, voice_note_id="doc-vn-q")
    finally:
        con.close()
    assert got is not None
    assert got.anchor_id == created.anchor_id
    assert got.page == 0


# ─────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────


def test_create_anchor_rejects_degenerate_bbox():
    # BBox.__post_init__ rejects before we even reach the DB.
    with pytest.raises(ValueError, match="degenerate"):
        BBox(x0=10, y0=10, x1=10, y1=20)
    with pytest.raises(ValueError, match="degenerate"):
        BBox(x0=10, y0=10, x1=20, y1=10)


def test_create_anchor_rejects_negative_page(db_path):
    with connect_write(db_path, purpose="test") as con:
        src = _seed_source_doc(con)
        _seed_voice_note(con, "doc-vn-neg")
        with pytest.raises(ValueError, match="page must be >= 0"):
            create_anchor(
                con, voice_note_id="doc-vn-neg", document_id=src,
                page=-1, bbox=BBox(0, 0, 10, 10),
            )


def test_create_anchor_requires_locked_connection(db_path):
    raw = duckdb.connect(db_path)
    try:
        with pytest.raises(TypeError, match="LockedConnection"):
            create_anchor(
                raw, voice_note_id="doc-vn-x", document_id="doc-src-1",
                page=0, bbox=BBox(0, 0, 10, 10),
            )
    finally:
        raw.close()


# ─────────────────────────────────────────────────────────────────────
# Concurrency — rigor #3
# ─────────────────────────────────────────────────────────────────────


def test_concurrent_creates(db_path):
    """Two simultaneous create_anchor calls for the same
    voice_note_id MUST collide on the unique constraint. One wins,
    one raises.

    Uses real threads, not mocks. The flock in db_lock serializes
    the writes, so the "simultaneous" here is "both threads call
    create_anchor at the same time"; the constraint enforcement is
    the substrate's unique index on voice_note_id, and a unique
    violation is exactly what we want.
    """
    # Pre-seed the prerequisite rows on the main thread so the two
    # writer threads don't race on inserting them. The DB lock makes
    # this safe; we just want the threads to race on the anchor
    # write specifically.
    with connect_write(db_path, purpose="test-seed") as con:
        src = _seed_source_doc(con)
        _seed_voice_note(con, "doc-vn-race")

    barrier = threading.Barrier(2)
    results: list[tuple[str, Optional[Exception]]] = []
    results_lock = threading.Lock()

    def worker(tag: str) -> None:
        barrier.wait()  # ensure both threads attempt at the same time
        try:
            with connect_write(
                db_path, purpose=f"test-race-{tag}",
            ) as con:
                create_anchor(
                    con,
                    voice_note_id="doc-vn-race",
                    document_id=src,
                    page=0,
                    bbox=BBox(0, 0, 10, 10),
                )
            with results_lock:
                results.append((tag, None))
        except Exception as e:  # noqa: BLE001 — we want to record any
            with results_lock:
                results.append((tag, e))

    threads = [
        threading.Thread(target=worker, args=("A",)),
        threading.Thread(target=worker, args=("B",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30.0)
        assert not t.is_alive(), "thread hung — likely deadlocked"

    # Exactly one success, exactly one failure.
    successes = [r for r in results if r[1] is None]
    failures = [r for r in results if r[1] is not None]
    assert len(successes) == 1, f"expected 1 success, got {successes!r}"
    assert len(failures) == 1, f"expected 1 failure, got {failures!r}"
    # The failure MUST be a unique-constraint violation — not a
    # locking timeout, not a generic error. DuckDB raises
    # ConstraintException; we accept any exception whose message
    # mentions "unique" / "constraint" / "duplicate" since the
    # exact class name varies by DuckDB version.
    err = failures[0][1]
    msg = str(err).lower()
    assert (
        "unique" in msg or "constraint" in msg or "duplicate" in msg
    ), f"expected unique-constraint violation, got: {type(err).__name__}: {err}"

    # The substrate has exactly one row for this voice_note_id.
    con = duckdb.connect(db_path, read_only=True)
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM voice_note_anchor "
            "WHERE voice_note_id = ?",
            ["doc-vn-race"],
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 1


# ─────────────────────────────────────────────────────────────────────
# resolve_chunk_for_bbox — geometry behavior
# ─────────────────────────────────────────────────────────────────────


def test_resolve_chunk_zero_overlap_returns_none(db_path):
    """An anchor whose bbox doesn't overlap any chunk gets chunk_id
    = None. With the current substrate (no per-chunk bbox), every
    bbox falls into this branch — which is the documented behavior."""
    con = duckdb.connect(db_path, read_only=True)
    try:
        result = resolve_chunk_for_bbox(
            con, document_id="doc-src-1", page=0,
            bbox=BBox(0, 0, 10, 10),
        )
    finally:
        con.close()
    assert result is None


def test_resolve_chunk_overlap_argmax_with_stubbed_geometry(monkeypatch, db_path):
    """When per-chunk bbox geometry IS available, the API picks
    the chunk with the maximum overlap fraction (over the
    threshold). We stub ``_candidate_chunks_for_overlap`` to inject
    fixture chunks — the production geometry source isn't in this
    sprint, but the overlap math must be correct so SPR-05 + the
    future chunker-PDF integration can rely on it.

    Anchor bbox: (0, 0, 100, 100) — area 10000.
    Chunk A:    (0, 0, 60, 100)  — intersects (0,0,60,100) area 6000 → 60%.
    Chunk B:    (50, 50, 100, 100) — intersects (50,50,100,100) area 2500 → 25%.
    Expected: chunk_id = "A" (60% wins, 25% below threshold).
    """
    from substrate.voice import anchor_api

    def fake_candidates(con, document_id, page):
        return [
            ("A", BBox(0, 0, 60, 100)),
            ("B", BBox(50, 50, 100, 100)),
        ]

    monkeypatch.setattr(
        anchor_api, "_candidate_chunks_for_overlap", fake_candidates,
    )
    con = duckdb.connect(db_path, read_only=True)
    try:
        result = resolve_chunk_for_bbox(
            con, document_id="doc-src-1", page=0,
            bbox=BBox(0, 0, 100, 100),
        )
    finally:
        con.close()
    assert result == "A"


def test_resolve_chunk_below_threshold_returns_none(monkeypatch, db_path):
    """A chunk that overlaps the anchor below
    ``MIN_CHUNK_OVERLAP_FRACTION`` is rejected even if it's the
    only candidate."""
    from substrate.voice import anchor_api

    # Anchor (0,0,100,100) area 10000. Candidate covers a 20×100
    # strip → 2000 area, 20% overlap. Below the 30% default.
    def fake_candidates(con, document_id, page):
        return [("low", BBox(0, 0, 20, 100))]

    monkeypatch.setattr(
        anchor_api, "_candidate_chunks_for_overlap", fake_candidates,
    )
    con = duckdb.connect(db_path, read_only=True)
    try:
        result = resolve_chunk_for_bbox(
            con, document_id="doc-src-1", page=0,
            bbox=BBox(0, 0, 100, 100),
        )
    finally:
        con.close()
    assert result is None


def test_min_chunk_overlap_fraction_is_30_percent():
    """Lock the threshold value so a silent change requires a
    deliberate edit. The SCHEMA_NOTES.md justification refers to
    this number."""
    assert MIN_CHUNK_OVERLAP_FRACTION == 0.30
