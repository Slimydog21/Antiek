"""voice_note_anchor schema — DDL + table inventory.

Sprint SPR-02 (Wrestle Evolution, Wave 1). Adds a 1:1 anchor for a
voice-note row that fixes the user's attention to a specific
(document_id, page, bbox) region of the source material, plus an
optional ``chunk_id`` derived from the bbox at write time.

Why dual-keyed (coordinate AND semantic):
  - ``(document_id, page, bbox)`` is the canonical UI render key. It
    survives chunker upgrades — coordinates don't move when the
    chunker re-segments the text.
  - ``chunk_id`` gives semantic retrieval ("voice notes anchored
    where this chunk is cited") and is the join key for RL training.
  - The dual key means a chunker upgrade re-derives ``chunk_id`` via
    the re-chunk worker but never orphans the anchor.

Storage discipline:
  Every write must pass through ``runtime/db_lock.connect_write``
  (the only-writer invariant, architecture_notes §2.3). DDL too —
  the migration runner acquires the same flock.

The schema is idempotent (every CREATE uses IF NOT EXISTS).
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────
#
# Foreign keys:
#   voice_note_id → documents(document_id). Voice notes in Antiek are
#     stored as documents with document_type='voice_note' (per Sprint
#     13, acquisition/voice/adapter.py); there is no separate
#     ``voice_notes`` table. The FK target is ``documents`` and the
#     application layer filters on document_type when needed.
#     ⚠ The SPR-02 spec page describes a ``voice_notes`` table —
#     that's an inaccuracy in the spec; the substrate uses documents.
#     Surfaced in the handoff.
#
#   document_id → documents(document_id). The document the bbox lives
#     on. (NB: this is the SOURCE document the voice note anchors to,
#     NOT the voice note's own document_id.)
#
#   chunk_id → chunks(chunk_id) ON DELETE SET NULL. Chunks may be
#     re-derived on chunker upgrades; cascading DELETE would orphan
#     anchors. SET NULL preserves the row and the re-chunk worker
#     re-resolves it.
#
# Unique constraint on voice_note_id enforces the 1:1.
#
# Indexes:
#   idx_voice_note_anchor_page: serves "show all anchors on this page"
#     — the most common UI query (SPR-05 glyph layer).
#   idx_voice_note_anchor_chunk: serves "voice notes anchored at this
#     chunk" — semantic retrieval + RL training join.
#   idx_voice_note_anchor_version: scoped to the re-chunk worker so it
#     can scan stale rows quickly.

VOICE_NOTE_ANCHOR_SCHEMA_SQL = """
-- ============================================================
-- voice_note_anchor — 1:1 region anchor for a voice note
-- ============================================================
CREATE TABLE IF NOT EXISTS voice_note_anchor (
    anchor_id         TEXT PRIMARY KEY,
    voice_note_id     TEXT NOT NULL UNIQUE
                          REFERENCES documents(document_id),
    document_id       TEXT NOT NULL REFERENCES documents(document_id),
    page              INTEGER NOT NULL CHECK (page >= 0),
    -- JSON: {"x0": float, "y0": float, "x1": float, "y1": float}
    -- PDF user-space coordinates. Pydantic ``BBox`` enforces shape.
    -- VARIANT upgrade deferred — same convention as documents.metadata.
    bbox              TEXT NOT NULL,
    -- Optional FK; ON DELETE SET NULL via the application-layer
    -- chunk-deletion paths. DuckDB does not enforce the ON DELETE
    -- SET NULL referential action today, so the re-chunk worker also
    -- defensively clears chunk_id when a referenced chunk vanishes.
    chunk_id          TEXT REFERENCES chunks(chunk_id),
    -- The chunker version that produced this anchor's chunk_id.
    -- Source of truth: substrate.voice.CHUNKER_VERSION (see module
    -- docstring for bump rules). The re-chunk worker compares this
    -- against the live constant to find stale rows.
    chunker_version   TEXT NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_voice_note_anchor_page
    ON voice_note_anchor(document_id, page);
CREATE INDEX IF NOT EXISTS idx_voice_note_anchor_chunk
    ON voice_note_anchor(chunk_id);
CREATE INDEX IF NOT EXISTS idx_voice_note_anchor_version
    ON voice_note_anchor(chunker_version);
"""


# Tables this schema creates. Used by tests + the migration smoke
# check.
SCHEMA_TABLES: tuple[str, ...] = ("voice_note_anchor",)
