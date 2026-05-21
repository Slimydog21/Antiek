-- Sprint SPR-02 (Wrestle Evolution Wave 1) — voice_note_anchor.
--
-- Adds a 1:1 region-anchor for a voice note. Idempotent: every
-- statement uses IF NOT EXISTS so re-running on an already-migrated
-- DB is a no-op.
--
-- Prerequisite: documents + chunks tables exist (substrate.graph
-- v1 schema). The migration runner asserts this before applying.
--
-- The Python source of truth for this SQL is
-- substrate/voice/anchor_schema.py:VOICE_NOTE_ANCHOR_SCHEMA_SQL.
-- This .sql file is kept in sync (the runner reads the Python
-- constant; this file documents the migration for operators who
-- want to inspect it without grepping Python).

-- ============================================================
-- voice_note_anchor — 1:1 region anchor for a voice note
-- ============================================================
CREATE TABLE IF NOT EXISTS voice_note_anchor (
    anchor_id         TEXT PRIMARY KEY,
    voice_note_id     TEXT NOT NULL UNIQUE
                          REFERENCES documents(document_id),
    document_id       TEXT NOT NULL REFERENCES documents(document_id),
    page              INTEGER NOT NULL CHECK (page >= 0),
    bbox              TEXT NOT NULL,
    chunk_id          TEXT REFERENCES chunks(chunk_id),
    chunker_version   TEXT NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_voice_note_anchor_page
    ON voice_note_anchor(document_id, page);
CREATE INDEX IF NOT EXISTS idx_voice_note_anchor_chunk
    ON voice_note_anchor(chunk_id);
CREATE INDEX IF NOT EXISTS idx_voice_note_anchor_version
    ON voice_note_anchor(chunker_version);
