-- Integration follow-up 2026-05-22 — close three substrate gaps named
-- by SPR-02 / SPR-07 / SPR-10 handoffs:
--
-- 1. chunks.page (nullable INTEGER) — PDF page the chunk sits on. SPR-02
--    voice anchor's resolve_chunk_for_bbox returns NULL on the live
--    substrate today because chunks have no page geometry; SPR-07
--    gutter cite-jump hardcodes page=1 in services/cross_doc/query.py
--    for the same reason. Adding the column lets both queries populate
--    correctly when an ingestion pipeline (or a backfill worker) writes
--    real values.
--
-- 2. chunks.bbox (nullable JSON-as-TEXT) — bounding box on the page, in
--    PDF user-space coordinates. Format: {"x0":..,"y0":..,"x1":..,"y1":..}.
--    TEXT not native JSON because DuckDB's JSON support is still
--    landing; we follow the same VARIANT-deferral convention as
--    documents.metadata. The 30% overlap threshold in SPR-02 anchor
--    resolution can finally be exercised against real geometry.
--
-- 3. documents.raw_bytes_path (nullable TEXT) — filesystem path or URI
--    where the raw source bytes are stored. SPR-10 share-bundle needs
--    this to bundle the original PDF alongside the .antiek sidecar; the
--    extracted-text-only model breaks for URL-imported PDFs where the
--    user no longer has the source. The substrate stays content-
--    addressed (the path can point at a per-document directory keyed
--    by document_id); we don't store bytes inline.
--
-- Why ALTER TABLE rather than CREATE TABLE IF NOT EXISTS: the chunks
-- and documents tables already exist (substrate/graph/schema.py
-- ANTIEK_GRAPH_SCHEMA_V1_SQL). Re-running the v1 DDL would no-op the
-- column additions because CREATE TABLE IF NOT EXISTS only takes effect
-- when the table is absent.
--
-- Idempotency: DuckDB's ALTER TABLE ... ADD COLUMN IF NOT EXISTS is the
-- right form. If the worktree's DuckDB version doesn't support the
-- IF NOT EXISTS clause, the migrate.py runner catches the
-- ConstraintException / CatalogException and treats already-present as
-- success. See substrate/graph/migrate.py.

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS page INTEGER;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS bbox TEXT;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS raw_bytes_path TEXT;

-- Index the page column so the gutter cross-doc query's "page=?" lookup
-- doesn't full-table-scan. The (document_id, page) compound matches
-- the most-common access pattern: "list chunks on this page of this doc."
CREATE INDEX IF NOT EXISTS chunks_document_page_idx
    ON chunks (document_id, page);
