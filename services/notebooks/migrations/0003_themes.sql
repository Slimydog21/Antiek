-- ============================================================
-- 0003_themes.sql
-- Wrestle Evolution SPR-11 · M1 · Per-theme notebook schema
--
-- Tier-3 of the locked three-tier notes model (master spec
-- §13.6, locked 2026-05-21):
--   Tier 1 = behavior_events (substrate)
--   Tier 2 = notebook_documents + per_doc_notebook_blocks (SPR-08, 0001/0002)
--   Tier 3 = themes + theme_blocks (this migration)
--
-- A theme is a hand-curated rollup across multiple per-doc notebooks.
-- The operator promotes Tier-2 blocks into a theme; promoted rows
-- become theme_blocks that reference back to the source Tier-2 row.
-- Prose blocks (operator framing between promoted blocks) are also
-- allowed — Tier-3 IS the curatorial-framing tier (the SPR-08 no-
-- authoring rule was Tier-2-only; see BLOCK_TAXONOMY.md).
--
-- Auto-suggest clustering is OUT of scope here. SPR-11 ships the
-- hand-curation flow; auto-suggest activates when Tier-2 count ≥ 10k
-- + a topic model passes operator review (services/notebooks/
-- AUTO_SUGGEST.md documents the unlock criteria + feature flag).
--
-- Idempotent: every CREATE uses IF NOT EXISTS. Safe to re-run on a
-- fresh DB and on a production-shape DB.
-- ============================================================

-- ----------------------------------------------------------------
-- themes — one row per (user_id, slug)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS themes (
    theme_id        TEXT PRIMARY KEY,           -- thm-<12hex>-<ms>
    user_id         TEXT NOT NULL,

    -- URL-safe slug, unique per user. The route at
    -- /wrestle/themes/<slug> resolves on (user_id, slug). The
    -- ascii-only / lowercase / hyphen-only invariant is enforced by
    -- services.notebooks.theme_persistence.slugify; the DB only
    -- enforces uniqueness.
    slug            TEXT NOT NULL,

    title           TEXT NOT NULL,

    -- Optional cover snippet — a short prose lede shown on the index
    -- card. Populated by the operator; defaults to NULL.
    cover_snippet   TEXT,

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_edited_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (user_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_themes_user
    ON themes (user_id, last_edited_at DESC);


-- ----------------------------------------------------------------
-- theme_blocks — children of a theme; promoted Tier-2 blocks or
-- operator-authored prose
-- ----------------------------------------------------------------
--
-- source_block_id is a soft FK into per_doc_notebook_blocks. We deliberately
-- do NOT declare a foreign-key constraint here:
--
--   1. The per-doc notebook's auto-populator may delete + re-insert
--      a block in some merge paths (highlight_removed -> rebuild).
--      A hard cascade would silently nuke theme references.
--   2. The product behavior on delete is "stale placeholder", not
--      "cascade". The renderer reads source_block_id, joins LEFT,
--      and detects NULL by surfacing the cached last-known content
--      held inline in content_json.
--
-- Test coverage for stale placeholders lives in
-- services/notebooks/tests/test_theme_persistence.py
-- ("stale_block_handling") and apps/reading/src/modes/Notebook/
-- __tests__/theme.test.tsx ("stale-block placeholder").
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS theme_blocks (
    theme_block_id      TEXT PRIMARY KEY,       -- tbk-<12hex>-<ms>
    theme_id            TEXT NOT NULL,          -- soft FK -> themes

    -- Source per-doc notebook block. NULL for prose blocks authored
    -- inside the theme itself (Tier-3 framing). Non-NULL otherwise.
    source_block_id     TEXT,                   -- soft FK -> per_doc_notebook_blocks
    source_notebook_id  TEXT,                   -- soft FK -> notebook_documents
    source_document_id  TEXT,                   -- denormalised for back-link rendering

    -- Block type at promote time. Mirrors per_doc_notebook_blocks.block_type
    -- vocabulary (the 6 closed-set Tier-2 types) plus 'prose' for
    -- operator-authored theme-internal framing.
    block_type          TEXT NOT NULL,

    -- For promoted blocks, this carries a CACHE of the Tier-2
    -- content_json at promote time. If the source block is later
    -- deleted, the cache is what powers the stale-placeholder
    -- rendering. For prose blocks, this is the operator's TipTap
    -- node payload.
    content_json        TEXT NOT NULL DEFAULT '{}',

    -- Fractional ordering. Drag-to-reorder rewrites this; nothing
    -- else mutates it. Two blocks may briefly share a position
    -- during a pending write — the renderer treats ties as
    -- insertion-order stable (same convention as per_doc_notebook_blocks).
    sort_order          DOUBLE NOT NULL DEFAULT 0.0,

    -- When the operator dismisses a stale placeholder, we soft-
    -- delete by stamping dismissed_at rather than removing the row;
    -- behaviour-store joins still see the historical promotion.
    dismissed_at        TIMESTAMP,

    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Order-by selector for the per-theme list view.
CREATE INDEX IF NOT EXISTS idx_theme_blocks_theme_order
    ON theme_blocks (theme_id, sort_order);

-- Reverse lookup: "what themes is this Tier-2 block in?" used by the
-- per-doc notebook surface to render the "in theme: <title>"
-- indicator on a promoted source block (SPR-11 M2 acceptance).
CREATE INDEX IF NOT EXISTS idx_theme_blocks_source
    ON theme_blocks (source_block_id);
