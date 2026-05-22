-- ============================================================
-- 0002_notebook_blocks.sql
-- Wrestle Evolution SPR-08 · M6 · Block-event provenance index
--
-- 0001 created per_doc_notebook_blocks with the source_event_ids JSON column.
-- This migration adds:
--
--   1. notebook_block_events — a normalised many-to-many table so
--      the reward_medium join in substrate/behavior/REWARD_PROXY.md
--      can avoid parsing the source_event_ids JSON array on every
--      pass.  The auto-populator writes to both this table AND
--      keeps source_event_ids on per_doc_notebook_blocks (denormalisation
--      for renderer convenience — the API responses ship the array
--      in-line).
--
--   2. notebook_save_log — minimal observability for the persistence
--      layer; every save (auto-debounced + Cmd+S explicit) writes a
--      single row. Used by tests + ops to verify the debounce isn't
--      flapping.
-- ============================================================

CREATE TABLE IF NOT EXISTS notebook_block_events (
    notebook_id     TEXT NOT NULL,
    block_id        TEXT NOT NULL,
    event_id        TEXT NOT NULL,    -- FK into behavior_events
    event_type      TEXT NOT NULL,    -- denormalised; matches behavior_events.event_type
    PRIMARY KEY (block_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_notebook_block_events_notebook
    ON notebook_block_events (notebook_id);

CREATE INDEX IF NOT EXISTS idx_notebook_block_events_event
    ON notebook_block_events (event_id);


CREATE TABLE IF NOT EXISTS notebook_save_log (
    notebook_id     TEXT NOT NULL,
    saved_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    save_kind       TEXT NOT NULL,    -- 'auto' | 'explicit' | 'auto_populate'
    block_count     INTEGER NOT NULL,
    bytes           INTEGER NOT NULL,
    PRIMARY KEY (notebook_id, saved_at)
);
