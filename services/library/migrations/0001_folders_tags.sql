-- SPR-06 / M3 — Folders + tags for the universal library.
--
-- Single-user today (every row carries an `owner_user_id` defaulting
-- to '__operator__', matching the substrate-wide multi-user prep
-- pattern from substrate/graph/schema.py). Multi-user lands by
-- swapping the application-layer filter without a schema change.
--
-- Why these tables live under services/library and not substrate/graph:
-- folders + tags are organisational surface, not substrate. They
-- carry no claim provenance, no source tier, no embedding. They are
-- the consumer surface's bookmarking ergonomics. If we ever ship a
-- public library, folders + tags stay private (per the out-of-scope
-- gate on SPR-06: public-library / shared-corpus discovery is gated
-- on Sprint 18 legal review).
--
-- Flat hierarchy by design (sprint scope: "no nested folders this
-- sprint"). If a future sprint needs nesting, add a `parent_folder_id`
-- nullable column rather than reshaping; the application layer already
-- assumes flat.
--
-- WARNING (SPR-06 closeout note): this DDL is the file the sprint
-- HTML page named. There is no runner under services/library/ that
-- applies it at process boot — services/ingestion/migrations/ has
-- the apply_all helper but it only scans its own directory. The
-- TS client (folders.ts, tags.ts) is therefore localStorage-backed
-- for SPR-06: this file is the canonical schema for when a
-- services/library/migrations/__init__.py runner lands in a later
-- sprint (or when this DDL is folded into substrate/graph/schema.py
-- if cross-mode access becomes needed). The shape is intentionally
-- the one the surface code already assumes so the wire-up is a flip,
-- not a refactor.

-- ============================================================
-- folders — user-created bookmark folders (flat, no nesting)
-- ============================================================
CREATE TABLE IF NOT EXISTS folders (
    folder_id        TEXT PRIMARY KEY,
    owner_user_id    TEXT NOT NULL DEFAULT '__operator__',
    name             TEXT NOT NULL,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS folders_owner_idx ON folders (owner_user_id, sort_order);

-- ============================================================
-- document_folders — many-to-many join (a doc can be in N folders)
-- ============================================================
CREATE TABLE IF NOT EXISTS document_folders (
    document_id   TEXT NOT NULL,
    folder_id     TEXT NOT NULL,
    added_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, folder_id)
);

CREATE INDEX IF NOT EXISTS document_folders_folder_idx ON document_folders (folder_id);

-- ============================================================
-- tags — user-created flat tags (no hierarchy)
-- ============================================================
-- We do NOT enforce a unique constraint on (owner_user_id, name)
-- here because DuckDB's CONSTRAINT semantics around UNIQUE on a
-- nullable composite are a moving target across versions; the
-- application layer dedupes on insert. Watch for drift if this
-- migration is ever folded into the substrate where the discipline
-- is stricter.
CREATE TABLE IF NOT EXISTS tags (
    tag_id           TEXT PRIMARY KEY,
    owner_user_id    TEXT NOT NULL DEFAULT '__operator__',
    name             TEXT NOT NULL,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS tags_owner_idx ON tags (owner_user_id, name);

-- ============================================================
-- document_tags — many-to-many join
-- ============================================================
CREATE TABLE IF NOT EXISTS document_tags (
    document_id   TEXT NOT NULL,
    tag_id        TEXT NOT NULL,
    added_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, tag_id)
);

CREATE INDEX IF NOT EXISTS document_tags_tag_idx ON document_tags (tag_id);
