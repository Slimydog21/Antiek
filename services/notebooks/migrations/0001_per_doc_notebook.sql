-- ============================================================
-- 0001_per_doc_notebook.sql
-- Wrestle Evolution SPR-08 · M1 · Per-document notebook schema
--
-- Two tables:
--   notebook_documents — one row per (user_id, document_id)
--   notebook_blocks    — children of a notebook; created by the
--                        auto-populator from Tier-1 events
--
-- Distinct from the Sprint 18 Wedge 2 ``notebooks`` table the
-- existing /notebook/<notebook_id> surface writes to. The per-doc
-- table is keyed on (user_id, document_id) — there is exactly one
-- notebook per document per user. SPR-11 (per-theme rollups) reads
-- from this table.
--
-- Idempotent: every CREATE uses IF NOT EXISTS. Safe to re-run on a
-- fresh DB and on a production-shape DB.
-- ============================================================

-- ----------------------------------------------------------------
-- notebook_documents — one notebook per (user_id, document_id)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notebook_documents (
    notebook_id     TEXT PRIMARY KEY,           -- nbk-<12hex>-<ms>
    user_id         TEXT NOT NULL,
    document_id     TEXT NOT NULL,
    title           TEXT,                       -- nullable; defaults to doc title at first save

    -- TipTap document JSON. Source of truth for the rich-text
    -- envelope; ``notebook_blocks`` is the structured per-block
    -- index used by the auto-populator + reward join. The two MUST
    -- stay consistent — persistence.py is the only writer.
    content_json    TEXT NOT NULL DEFAULT '{}',

    -- Stamped from services.notebooks.blocks.BLOCK_TAXONOMY_VERSION
    -- on every save. Bumps when block shapes change.
    format_version  INTEGER NOT NULL DEFAULT 1,

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_saved_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint enforces the "one per (user, document)"
    -- invariant. DuckDB doesn't support partial unique indexes; we
    -- accept that demoted notebooks still occupy this slot (there
    -- is no notebook-level demote — blocks are demoted individually).
    UNIQUE (user_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_notebook_documents_user_doc
    ON notebook_documents (user_id, document_id);


-- ----------------------------------------------------------------
-- notebook_blocks — child rows; auto-populator + reward join read
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notebook_blocks (
    block_id        TEXT PRIMARY KEY,           -- blk-<12hex>-<ms>
    notebook_id     TEXT NOT NULL,
    block_type      TEXT NOT NULL,              -- closed set; see services/notebooks/blocks.py

    -- The behavior_events.event_id values this block is sourced from.
    -- At least one entry; the merge rule for highlight edits keeps
    -- the array sorted. JSON-encoded TEXT[] (DuckDB list type is
    -- avoided here to keep cross-engine portability for the later
    -- DuckLake swap; same convention as substrate/behavior/schema).
    source_event_ids TEXT NOT NULL,             -- JSON-encoded array

    -- Optional FK into the documents table (post-SPR-03). Denormalised
    -- here so reward_medium's join can scope without traversing
    -- notebook_documents.
    document_id     TEXT,

    -- TipTap node payload for this block. Block-type-specific shape;
    -- see ``apps/reading/src/modes/Notebook/blocks/``.
    content_json    TEXT NOT NULL DEFAULT '{}',

    -- Fractional ordering. Reordering rewrites this; nothing else
    -- mutates it. Two blocks may briefly share a position during a
    -- pending write — the renderer treats ties as insertion-order
    -- stable.
    position        DOUBLE NOT NULL DEFAULT 0.0,

    -- Soft-delete: demote moves the block into the bottom collapsed
    -- section. ``reward_medium`` includes demoted blocks (the demote
    -- itself is signal, not deletion).
    demoted_at      TIMESTAMP,                  -- NULL means visible

    -- Operator-edit timestamp; bumps on a notebook_block_edited
    -- event so renderers can show "edited" badges.
    edited_at       TIMESTAMP,

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Order-by selector for the per-notebook list view.
CREATE INDEX IF NOT EXISTS idx_notebook_blocks_notebook_pos
    ON notebook_blocks (notebook_id, position);

-- Reward-join selector (used by substrate/behavior/workers/reward_medium.py).
-- The canonical join in REWARD_PROXY.md scans by (user_id, document_id);
-- the join walks notebook_documents on the user/doc keys and then this
-- table on notebook_id. The document_id denormalisation lets a single-
-- table scan find candidate blocks first.
CREATE INDEX IF NOT EXISTS idx_notebook_blocks_doc
    ON notebook_blocks (document_id);
