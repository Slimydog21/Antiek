-- Deliverables substrate extensions (2026-05-22 follow-up).
--
-- Master spec §5.6 names the reward chain:
--   interaction → notebook → deliverable → publication
--
-- The first three nodes existed before this migration (behavior_events,
-- notebook_blocks, deliverables — the last from substrate/graph/schema.py).
-- What was missing for reward_deep:
--   (a) the `deliverables` table had no publication_uri / published_at
--       columns. SPR-01's documented join (REWARD_PROXY.md §Worker 3)
--       needs them to filter "published" status. The existing
--       `status` column has values ('draft','in_review','final');
--       there's no 'published' value, and `final` doesn't capture
--       the publication URI.
--   (b) deliverables linked to deliverable_sections + section_blocks
--       but not to notebooks. The reward join needs a notebook →
--       deliverable relation.
--
-- This migration:
--   1. Adds publication_uri, published_at columns to the existing
--      deliverables table (additive — old rows have NULLs, the
--      reward_deep filter on published_at IS NOT NULL handles them).
--   2. Creates deliverable_citations: a notebook → deliverable join
--      table. New table; no existing conflict.
--
-- Status values: the existing deliverables CHECK constraint allows
-- ('draft','in_review','final'). The reward_deep worker reads
-- published_at IS NOT NULL as the publication threshold rather than
-- adding a new status value (which would require dropping + recreating
-- the CHECK constraint — DuckDB doesn't support ALTER TABLE on
-- CHECK constraints today). This is the additive choice.

ALTER TABLE deliverables ADD COLUMN IF NOT EXISTS publication_uri TEXT;
ALTER TABLE deliverables ADD COLUMN IF NOT EXISTS published_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS deliverables_published_at_idx
    ON deliverables (published_at);

CREATE TABLE IF NOT EXISTS deliverable_citations (
    deliverable_id   TEXT NOT NULL,
    notebook_id      TEXT NOT NULL,
    -- Optional: a specific block within the notebook that was cited.
    -- NULL means "the whole notebook is the citation." Stored as a
    -- supplementary column rather than part of the PK because DuckDB
    -- treats PK columns as implicit NOT NULL — and we genuinely want
    -- block_id to be nullable. The (deliverable_id, notebook_id) PK
    -- means one deliverable can cite a notebook at most once; the
    -- block_id then records the most-specific citation (if any).
    -- Sprint-19's deliverable UX that wants to cite multiple blocks
    -- within the same notebook can change this to a non-PK
    -- composite uniquely keyed by all three.
    block_id         TEXT,
    cited_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (deliverable_id, notebook_id)
);

CREATE INDEX IF NOT EXISTS deliverable_citations_notebook_idx
    ON deliverable_citations (notebook_id);
