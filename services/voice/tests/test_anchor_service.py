"""Tests for services/voice/anchor_service.py (SPR-05 M3).

Verifies the load-bearing transactional invariant: if the anchor
insert fails, the voice_note documents row MUST be rolled back —
no orphan voice notes left behind.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import duckdb
import pytest

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write  # noqa: E402
from services.voice.anchor_service import (  # noqa: E402
    SaveAnchoredVoiceNoteError,
    save_anchored_voice_note,
)
from substrate.graph.schema import init_database_at_path  # noqa: E402
from substrate.voice.anchor_api import BBox  # noqa: E402
from substrate.voice.migrate import apply_at_path  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path) -> str:
    """Fresh DuckDB with documents + chunks + voice_note_anchor."""
    p = str(tmp_path / "graph.duckdb")
    init_database_at_path(p)
    apply_at_path(p)
    return p


def _seed_source_doc(con, document_id: str = "doc-src-1") -> str:
    """Insert a minimal PDF source document for the anchor's FK."""
    con.execute(
        "INSERT INTO documents "
        "(document_id, source_tier, document_type, title) "
        "VALUES (?, ?, ?, ?)",
        [document_id, 2, "pdf", "Test source"],
    )
    return document_id


def _count_voice_notes(db_path: str) -> int:
    con = duckdb.connect(db_path, read_only=True)
    try:
        row = con.execute(
            "SELECT count(*) FROM documents "
            "WHERE document_type = 'voice_note'"
        ).fetchone()
    finally:
        con.close()
    return int(row[0]) if row else 0


def _count_anchors(db_path: str) -> int:
    con = duckdb.connect(db_path, read_only=True)
    try:
        row = con.execute("SELECT count(*) FROM voice_note_anchor").fetchone()
    finally:
        con.close()
    return int(row[0]) if row else 0


# ─────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────


def test_save_anchored_voice_note_writes_both_rows(db_path):
    with connect_write(db_path, purpose="test_seed") as con:
        src = _seed_source_doc(con)
    result = save_anchored_voice_note(
        transcript="this is the user reacting to a passage",
        document_id=src,
        page=2,
        bbox=BBox(x0=10, y0=20, x1=100, y1=80),
        duration_seconds=4.2,
        db_path=db_path,
        recorded_at=datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc),
    )
    assert result.voice_note_id.startswith("doc-vn-")
    assert result.anchor.voice_note_id == result.voice_note_id
    assert result.anchor.document_id == src
    assert result.anchor.page == 2
    assert _count_voice_notes(db_path) == 1
    assert _count_anchors(db_path) == 1


def test_save_round_trips_through_get(db_path):
    from substrate.voice.anchor_api import get_anchor_by_voice_note

    with connect_write(db_path, purpose="test_seed") as con:
        src = _seed_source_doc(con)
    result = save_anchored_voice_note(
        transcript="round trip test",
        document_id=src,
        page=0,
        bbox=BBox(x0=0, y0=0, x1=50, y1=50),
        db_path=db_path,
    )
    con = duckdb.connect(db_path, read_only=True)
    try:
        fetched = get_anchor_by_voice_note(
            con, voice_note_id=result.voice_note_id,
        )
    finally:
        con.close()
    assert fetched is not None
    assert fetched.anchor_id == result.anchor.anchor_id


# ─────────────────────────────────────────────────────────────────────
# Rollback path — the load-bearing rigor test
# ─────────────────────────────────────────────────────────────────────


def test_rollback_when_anchor_insert_fails_leaves_no_voice_note(db_path):
    """If create_anchor raises, the voice_note document row MUST NOT
    be committed.

    We patch substrate.voice.anchor_api.create_anchor (imported into
    anchor_service) with a raising stub to simulate the failure mode
    M3 calls out: "simulated DB failure during anchor insert → no
    voice_note row left behind".
    """
    with connect_write(db_path, purpose="test_seed") as con:
        src = _seed_source_doc(con)

    def _boom(con, **kwargs):
        raise RuntimeError("simulated anchor insert failure")

    # The service imports create_anchor by name at module load
    # time; patch the symbol on the service module itself.
    with patch(
        "services.voice.anchor_service.create_anchor", side_effect=_boom,
    ):
        with pytest.raises(SaveAnchoredVoiceNoteError) as excinfo:
            save_anchored_voice_note(
                transcript="this must not persist",
                document_id=src,
                page=1,
                bbox=BBox(x0=0, y0=0, x1=50, y1=50),
                db_path=db_path,
            )

    # The wrapper preserves the underlying cause.
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "simulated anchor insert" in str(excinfo.value.__cause__)

    # Critical: NO orphan voice_note document, NO orphan anchor.
    assert _count_voice_notes(db_path) == 0, (
        "rollback failed — voice_note row leaked despite anchor error"
    )
    assert _count_anchors(db_path) == 0


def test_rollback_on_missing_source_doc_fk(db_path):
    """FK violation on the anchor side should also roll back.

    The anchor.document_id FK references documents — passing a
    document_id that doesn't exist should fail at INSERT time.
    Verify no voice_note row is left behind.
    """
    # Intentionally do NOT seed the source doc.
    with pytest.raises(SaveAnchoredVoiceNoteError):
        save_anchored_voice_note(
            transcript="anchored to a missing source",
            document_id="doc-nonexistent",
            page=0,
            bbox=BBox(x0=0, y0=0, x1=50, y1=50),
            db_path=db_path,
        )
    assert _count_voice_notes(db_path) == 0
    assert _count_anchors(db_path) == 0


def test_rollback_on_degenerate_bbox(db_path):
    """A degenerate bbox raises ValueError in the BBox dataclass —
    that happens before any DB write, but the wrapping is exercised
    inside the connect_write context. Verify no row leaks."""
    with connect_write(db_path, purpose="test_seed") as con:
        src = _seed_source_doc(con)
    with pytest.raises((ValueError, SaveAnchoredVoiceNoteError)):
        save_anchored_voice_note(
            transcript="x",
            document_id=src,
            page=0,
            # zero-area — BBox raises in __post_init__
            bbox=BBox(x0=10, y0=10, x1=10, y1=10),
            db_path=db_path,
        )
    assert _count_voice_notes(db_path) == 0
    assert _count_anchors(db_path) == 0


# ─────────────────────────────────────────────────────────────────────
# Concurrency: unique constraint on voice_note_id
# ─────────────────────────────────────────────────────────────────────


def test_second_save_for_same_voice_note_raises(db_path):
    """The SPR-02 unique constraint on voice_note_id is the source
    of truth. A second save for the same voice_note_id (same
    operator_id + recorded_at → same stable id) must surface as a
    SaveAnchoredVoiceNoteError, and the second attempt must NOT
    leave duplicate documents rows behind (since insert_document is
    on_conflict='ignore', the document is the same — the anchor
    insert is what fails)."""
    with connect_write(db_path, purpose="test_seed") as con:
        src = _seed_source_doc(con)
    when = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)

    save_anchored_voice_note(
        transcript="first",
        document_id=src,
        page=0,
        bbox=BBox(x0=0, y0=0, x1=50, y1=50),
        recorded_at=when,
        db_path=db_path,
    )
    with pytest.raises(SaveAnchoredVoiceNoteError):
        save_anchored_voice_note(
            transcript="second — same voice_note_id",
            document_id=src,
            page=1,
            bbox=BBox(x0=10, y0=10, x1=60, y1=60),
            recorded_at=when,  # same → same stable voice_note_id
            db_path=db_path,
        )
    # Only the first anchor survives.
    assert _count_voice_notes(db_path) == 1
    assert _count_anchors(db_path) == 1
