"""voice_note_anchor read/write API (SPR-02).

Contract surface that SPR-05 calls. Stable signatures — the UI
sprint should not need contract changes mid-build.

Functions:
  - ``create_anchor`` — write one anchor row. Resolves chunk_id at
    write time and stamps the current CHUNKER_VERSION.
  - ``get_anchors_on_page`` — list anchors on a (document_id, page).
  - ``get_anchor_by_voice_note`` — fetch the anchor for one voice
    note (None if unanchored).
  - ``resolve_chunk_for_bbox`` — given a bbox, return the chunk_id
    of the chunk with maximum overlap above the 30% threshold.

Concurrency:
  ``create_anchor`` does NOT catch unique-constraint violations on
  ``voice_note_id``. Two simultaneous calls for the same voice note
  → one succeeds, the other raises a DuckDB ConstraintException.
  This is by design — the substrate's unique constraint is the
  authority. See SCHEMA_NOTES.md.

Geometry gap (surfaced for handoff):
  The Antiek ``chunks`` table has NO ``page`` or ``bbox`` columns
  today (only document_id, chunk_index, section_path, text,
  embedding, token_count). The text chunker
  (processing.chunking.chunker.chunk_markdown) operates on markdown
  headings, not PDF page geometry. Therefore
  ``resolve_chunk_for_bbox`` cannot return a real chunk_id today —
  it returns NULL.

  When chunks gain per-chunk page+bbox metadata (a future sprint
  that wires up PDF-aware chunking), update
  ``_compute_chunk_overlap`` to read those columns and return the
  argmax. The 30% threshold + chunker_version plumbing already
  works; only the geometry source is missing.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

# Repo root for direct-script invocation.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from runtime.db_lock import LockedConnection  # noqa: E402
from substrate.voice import CHUNKER_VERSION  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────


# Minimum bbox-overlap fraction (intersection_area / anchor_area)
# required to associate a chunk with an anchor at write time. Below
# this, chunk_id is NULL. See SCHEMA_NOTES.md for the rationale.
MIN_CHUNK_OVERLAP_FRACTION: float = 0.30


# ─────────────────────────────────────────────────────────────────────
# Public dataclasses
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BBox:
    """PDF user-space bounding box. Y-axis convention follows the PDF
    coordinate system (origin bottom-left), but the API is convention-
    agnostic: the bbox is just four floats and an inside-or-outside
    test. SPR-05 stamps the convention via the caller.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        # Enforce non-degenerate. Anchors with zero-area bboxes are
        # almost always a UI bug; reject loudly.
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError(
                f"degenerate bbox: x0={self.x0}, y0={self.y0}, "
                f"x1={self.x1}, y1={self.y1} (must have x1>x0 and y1>y0)"
            )

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    def to_json(self) -> str:
        return json.dumps(
            {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}
        )

    @classmethod
    def from_json(cls, s: str) -> "BBox":
        d = json.loads(s)
        return cls(x0=d["x0"], y0=d["y0"], x1=d["x1"], y1=d["y1"])

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> "BBox":
        return cls(x0=d["x0"], y0=d["y0"], x1=d["x1"], y1=d["y1"])


@dataclass(frozen=True)
class VoiceNoteAnchor:
    anchor_id: str
    voice_note_id: str
    document_id: str
    page: int
    bbox: BBox
    chunk_id: Optional[str]
    chunker_version: str
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────


def _assert_write_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"voice_note_anchor writes require a LockedConnection "
            f"(got {type(con).__name__}). Acquire via "
            "runtime.db_lock.connect_write(db_path, purpose=...)."
        )


def _row_to_anchor(row: tuple[Any, ...]) -> VoiceNoteAnchor:
    return VoiceNoteAnchor(
        anchor_id=row[0],
        voice_note_id=row[1],
        document_id=row[2],
        page=int(row[3]),
        bbox=BBox.from_json(row[4]),
        chunk_id=row[5],
        chunker_version=row[6],
        created_at=row[7],
    )


_SELECT_COLS = (
    "anchor_id, voice_note_id, document_id, page, bbox, "
    "chunk_id, chunker_version, created_at"
)


def _new_anchor_id() -> str:
    return f"vna-{uuid.uuid4().hex[:16]}"


# ─────────────────────────────────────────────────────────────────────
# Chunk resolution
# ─────────────────────────────────────────────────────────────────────


def _intersection_area(a: BBox, b: BBox) -> float:
    """Axis-aligned rectangle intersection area. Returns 0.0 for
    disjoint or edge-touching rectangles (strictly positive overlap
    required)."""
    x0 = max(a.x0, b.x0)
    y0 = max(a.y0, b.y0)
    x1 = min(a.x1, b.x1)
    y1 = min(a.y1, b.y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def _candidate_chunks_for_overlap(
    con: Any, document_id: str, page: int,
) -> list[tuple[str, BBox]]:
    """Return ``(chunk_id, chunk_bbox)`` for chunks on the given page.

    GEOMETRY GAP: the live chunks schema (substrate.graph.schema
    v1) has no page or bbox columns. Until per-chunk page+bbox
    metadata is added, this function returns an empty list, and
    callers therefore get NULL from ``resolve_chunk_for_bbox``.

    The empty-list path is intentionally explicit: surfacing the
    gap rather than silently degrading. When chunks gain
    page+bbox columns, replace the body with the SELECT that
    reads them and project into ``BBox.from_json`` / a dedicated
    columns-to-BBox converter.
    """
    # Intentional no-op until chunks expose per-chunk geometry.
    # Touching the args so future maintainers don't drop them in a
    # signature-cleanup pass.
    _ = (con, document_id, page)
    return []


def resolve_chunk_for_bbox(
    con: Any,
    *,
    document_id: str,
    page: int,
    bbox: BBox,
) -> Optional[str]:
    """Return the chunk_id of the chunk on ``(document_id, page)``
    that overlaps ``bbox`` by at least
    ``MIN_CHUNK_OVERLAP_FRACTION``, taking the argmax overlap if
    multiple qualify.

    Returns ``None`` if no chunk meets the threshold OR if chunks
    don't expose per-chunk geometry on this substrate (the current
    state — see SCHEMA_NOTES.md and the docstring of
    ``_candidate_chunks_for_overlap``).

    Read-only: accepts a plain DuckDB connection or a
    LockedConnection. Does not write.
    """
    anchor_area = bbox.area
    if anchor_area <= 0:
        return None
    candidates = _candidate_chunks_for_overlap(con, document_id, page)
    best_chunk: Optional[str] = None
    best_overlap_fraction: float = 0.0
    for chunk_id, chunk_bbox in candidates:
        inter = _intersection_area(bbox, chunk_bbox)
        if inter <= 0:
            continue
        # Overlap fraction is measured against the anchor area
        # (the user's selection). This is the "how much of the
        # user's region does this chunk cover" question. See
        # SCHEMA_NOTES.md for why this denominator, not the
        # chunk's area.
        fraction = inter / anchor_area
        if fraction < MIN_CHUNK_OVERLAP_FRACTION:
            continue
        if fraction > best_overlap_fraction:
            best_overlap_fraction = fraction
            best_chunk = chunk_id
    return best_chunk


# ─────────────────────────────────────────────────────────────────────
# Public read/write API
# ─────────────────────────────────────────────────────────────────────


def create_anchor(
    con: LockedConnection,
    *,
    voice_note_id: str,
    document_id: str,
    page: int,
    bbox: BBox,
    anchor_id: Optional[str] = None,
) -> VoiceNoteAnchor:
    """Insert one voice_note_anchor row. Resolves chunk_id from the
    bbox at write time and stamps the current ``CHUNKER_VERSION``.

    Concurrency:
      Two simultaneous calls for the same ``voice_note_id`` → one
      wins, the other gets a unique-constraint violation
      (DuckDB ``ConstraintException``). NOT caught here — the
      caller decides whether to retry or surface as a UI error.

    Args:
      voice_note_id: the voice-note document_id (Sprint 13 voice
        notes live as documents with document_type='voice_note').
      document_id: the SOURCE document the user anchored to.
      page: 0-indexed page number on the source document.
      bbox: PDF user-space bounding box.
      anchor_id: optional override (mostly for tests); a UUID-based
        id is generated otherwise.

    Returns:
      The created ``VoiceNoteAnchor`` with chunk_id populated (or
      None if no chunk qualifies / chunks lack page+bbox geometry).
    """
    _assert_write_locked(con)
    if page < 0:
        raise ValueError(f"page must be >= 0, got {page}")
    aid = anchor_id or _new_anchor_id()
    chunk_id = resolve_chunk_for_bbox(
        con, document_id=document_id, page=page, bbox=bbox,
    )
    # Two-step insert is necessary because DuckDB doesn't return
    # the inserted row by default. We insert with the values we
    # know, then SELECT back to get the timestamp default.
    con.execute(
        "INSERT INTO voice_note_anchor "
        "(anchor_id, voice_note_id, document_id, page, bbox, "
        " chunk_id, chunker_version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            aid, voice_note_id, document_id, int(page), bbox.to_json(),
            chunk_id, CHUNKER_VERSION,
        ],
    )
    row = con.execute(
        f"SELECT {_SELECT_COLS} FROM voice_note_anchor "
        "WHERE anchor_id = ?",
        [aid],
    ).fetchone()
    if row is None:  # pragma: no cover — INSERT just succeeded
        raise RuntimeError(
            f"voice_note_anchor row missing after insert: {aid}"
        )
    return _row_to_anchor(row)


def get_anchors_on_page(
    con: Any, *, document_id: str, page: int,
) -> list[VoiceNoteAnchor]:
    """List all anchors on a (document_id, page). Read-only;
    accepts any DuckDB-style connection (including LockedConnection
    via __getattr__).

    Returned in stable order: created_at ascending, anchor_id as a
    tiebreaker so two anchors created in the same microsecond have
    a deterministic order.
    """
    rows = con.execute(
        f"SELECT {_SELECT_COLS} FROM voice_note_anchor "
        "WHERE document_id = ? AND page = ? "
        "ORDER BY created_at ASC, anchor_id ASC",
        [document_id, int(page)],
    ).fetchall()
    return [_row_to_anchor(r) for r in rows]


def get_anchor_by_voice_note(
    con: Any, *, voice_note_id: str,
) -> Optional[VoiceNoteAnchor]:
    """Fetch the anchor for one voice note. ``None`` if the voice
    note is unanchored (per Sprint 13 it may have no anchor at all)."""
    row = con.execute(
        f"SELECT {_SELECT_COLS} FROM voice_note_anchor "
        "WHERE voice_note_id = ? LIMIT 1",
        [voice_note_id],
    ).fetchone()
    if row is None:
        return None
    return _row_to_anchor(row)
