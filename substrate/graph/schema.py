"""Antiek knowledge-graph schema (Sprint 3 Day 1-2 migration).

Subset of the Researchmaxx v2 schema, restricted to the four core
tables the graph layer needs:

- ``documents`` — primary sources, tier-classified
- ``chunks``    — content-addressed text chunks with optional embeddings
- ``nodes``     — typed graph entities
- ``edges``     — directed relationships with temporal validity

What's deferred from the Researchmaxx schema (and why):

- ``syntheses`` + ``synthesis_substrate_manifest`` — landed Sprint 10
  day 4-5 (backtest DB closure). ``middleware/archive/`` writes these.
- ``outcomes`` — landed Sprint 10 day 4-5. ``middleware/outcomes/``
  writes these.
- ``chunk_tier_overrides`` — landed Sprint 10 day 4-5. Recorded by
  the source_tier override emit path; backtest reads from here.
- ``investigations`` — DEFERRED. Investigations are reconstructable
  from the typed event stream (``investigation.start_requested`` +
  trajectory walk); a dedicated table is redundant until a query
  pattern forces it.
- ``chunks_effective_tier`` view — DEFERRED until a downstream
  consumer needs the override+document tier join inline.
- ``embeddings_meta`` — diagnostic; add when needed.

VARIANT vs TEXT: Researchmaxx uses ``VARIANT`` (DuckDB v1.5.0+ storage)
for metadata columns to enable JSON SQL queries. Antiek uses ``TEXT``
for v1 — every metadata read goes through application code that
``json.loads`` it, so we don't pay the VARIANT storage-version dance
yet. Upgrade lands when middleware needs JSON-shaped WHERE clauses.

Storage discipline: every write must go through
``runtime/db_lock.connect_write`` per architecture_notes §2.3
(the only-writer invariant). ``init_database`` enforces this — pass a
``LockedConnection`` or use ``init_database_at_path``.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import duckdb

# Import the canonical write-locker from Sprint 1 day-2. Same flock
# discipline; this is the Quack v2.0 swap point.
try:
    from ...runtime.db_lock import LockedConnection, connect_write
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection, connect_write  # type: ignore[no-redef]


# The schema script. Idempotent — every CREATE uses IF NOT EXISTS so
# rerunning is safe. CHECK constraints make malformed inserts fail
# loudly at the DB layer; the typed Pydantic payloads enforce the same
# constraints at the application layer.
ANTIEK_GRAPH_SCHEMA_V1_SQL = """
-- ============================================================
-- Documents — primary sources at ingestion time
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    document_id      TEXT PRIMARY KEY,
    source_uri       TEXT,
    title            TEXT,
    author           TEXT,
    published_at     TIMESTAMP,
    acquired_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_tier      INTEGER NOT NULL CHECK (source_tier BETWEEN 1 AND 5),
    document_type    TEXT NOT NULL,
    investigation_id TEXT,
    raw_text         TEXT,
    metadata         TEXT          -- JSON string; VARIANT upgrade deferred
);

-- ============================================================
-- Chunks — content-addressed text segments
-- ============================================================
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id      TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL REFERENCES documents(document_id),
    chunk_index   INTEGER NOT NULL,
    section_path  TEXT,
    text          TEXT NOT NULL,
    embedding     FLOAT[],          -- nullable; populated by processing/embedding
    token_count   INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- Nodes — typed graph entities
-- ============================================================
CREATE TABLE IF NOT EXISTS nodes (
    node_id          TEXT PRIMARY KEY,
    canonical_label  TEXT NOT NULL,
    node_type        TEXT NOT NULL CHECK (node_type IN (
        'entity', 'organization', 'person', 'property',
        'metric', 'mechanism', 'claim', 'method', 'constraint'
    )),
    embedding        FLOAT[],
    graph_scope      TEXT NOT NULL CHECK (graph_scope IN (
        'depth', 'cross_domain', 'constraint'
    )),
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    degree_cached    INTEGER NOT NULL DEFAULT 0,
    metadata         TEXT
);

-- ============================================================
-- Edges — directed relationships, temporal validity
-- ============================================================
CREATE TABLE IF NOT EXISTS edges (
    edge_id                TEXT PRIMARY KEY,
    source_node_id         TEXT NOT NULL REFERENCES nodes(node_id),
    target_node_id         TEXT NOT NULL REFERENCES nodes(node_id),
    relation               TEXT NOT NULL,
    chunk_id               TEXT REFERENCES chunks(chunk_id),
    source_document_id     TEXT REFERENCES documents(document_id),
    source_tier            INTEGER NOT NULL
        CHECK (source_tier BETWEEN 1 AND 5),
    extraction_confidence  FLOAT NOT NULL
        CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1),
    extracted_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_from             TIMESTAMP NOT NULL DEFAULT '1970-01-01',
    valid_until            TIMESTAMP,
    superseded_by          TEXT REFERENCES edges(edge_id),
    graph_scope            TEXT NOT NULL CHECK (graph_scope IN (
        'depth', 'cross_domain', 'constraint'
    )),
    investigation_id       TEXT,
    metadata               TEXT
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_documents_tier ON documents(source_tier);
CREATE INDEX IF NOT EXISTS idx_documents_inv  ON documents(investigation_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type    ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_scope   ON nodes(graph_scope);
CREATE INDEX IF NOT EXISTS idx_nodes_label   ON nodes(canonical_label);
CREATE INDEX IF NOT EXISTS idx_nodes_degree  ON nodes(degree_cached);
CREATE INDEX IF NOT EXISTS idx_edges_source  ON edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_target  ON edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_scope   ON edges(graph_scope);
CREATE INDEX IF NOT EXISTS idx_edges_valid   ON edges(valid_from, valid_until);
CREATE INDEX IF NOT EXISTS idx_edges_chunk   ON edges(chunk_id);
CREATE INDEX IF NOT EXISTS idx_edges_document ON edges(source_document_id);
CREATE INDEX IF NOT EXISTS idx_edges_confidence ON edges(extraction_confidence);
CREATE INDEX IF NOT EXISTS idx_edges_tier    ON edges(source_tier);

-- ============================================================
-- Syntheses — archived Loop 1 outputs (Sprint 10 day 4-5)
-- ============================================================
-- The SOLE writer is middleware/archive/archive_synthesis_via_db.
-- The status + implicit_recommendation CHECK lists MUST agree with
-- the Pydantic SynthesisStatus + SynthesisRecommendation literals
-- (drift test in tests/test_backtest_db.py).
CREATE TABLE IF NOT EXISTS syntheses (
    synthesis_id              TEXT PRIMARY KEY,
    investigation_id          TEXT,
    target_question           TEXT NOT NULL,
    synthesis_timestamp       TIMESTAMP NOT NULL,
    status                    TEXT NOT NULL CHECK (status IN (
        'draft', 'passed', 'regressed',
        'max_iterations_reached', 'escalated'
    )),
    implicit_recommendation   TEXT NOT NULL CHECK (implicit_recommendation IN (
        'proceed', 'pass', 'conditional',
        'undetermined', 'insufficient_evidence'
    )),
    thesis_text               TEXT,
    thesis_token_count        INTEGER NOT NULL DEFAULT 0,
    has_constraint_check_result BOOLEAN NOT NULL DEFAULT FALSE,
    -- JSON columns (TEXT for now; VARIANT upgrade deferred).
    model_versions            TEXT,
    decomposition             TEXT,
    evidence                  TEXT,
    parameters                TEXT,
    substrate                 TEXT,
    thesis                    TEXT,
    agent_trace               TEXT,
    constraint_history        TEXT,
    constraint_check_result   TEXT,
    archived_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Substrate manifest — what each synthesis pinned (per-entity rows)
-- ============================================================
CREATE TABLE IF NOT EXISTS synthesis_substrate_manifest (
    synthesis_id   TEXT NOT NULL REFERENCES syntheses(synthesis_id),
    entity_kind    TEXT NOT NULL CHECK (entity_kind IN (
        'document', 'chunk', 'node', 'edge'
    )),
    entity_id      TEXT NOT NULL,
    pinned_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (synthesis_id, entity_kind, entity_id)
);

-- ============================================================
-- Outcomes — observer-recorded post-hoc analysis of a synthesis
-- ============================================================
-- The SOLE writer is middleware/outcomes/record_outcome_via_db.
-- The sub-list/object payloads ride as TEXT-JSON columns; the typed
-- Pydantic OutcomeRecordedPayload is the canonical schema (drift
-- test enforces parity).
CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id                  TEXT PRIMARY KEY,
    synthesis_id                TEXT NOT NULL REFERENCES syntheses(synthesis_id),
    observer                    TEXT NOT NULL,
    observed_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    thesis_outcomes             TEXT,    -- JSON array
    falsification_outcomes      TEXT,    -- JSON array
    execution_risk_outcomes     TEXT,    -- JSON array
    decision_alignment          TEXT,    -- JSON object (nullable)
    notes                       TEXT
);

-- ============================================================
-- Chunk tier overrides — append-only audit of post-ingestion retiering
-- ============================================================
CREATE TABLE IF NOT EXISTS chunk_tier_overrides (
    chunk_id         TEXT NOT NULL REFERENCES chunks(chunk_id),
    original_tier    INTEGER NOT NULL CHECK (original_tier BETWEEN 1 AND 5),
    override_tier    INTEGER NOT NULL CHECK (override_tier BETWEEN 1 AND 5),
    reason           TEXT NOT NULL,
    set_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    set_by           TEXT,
    PRIMARY KEY (chunk_id, set_at)
);

-- ============================================================
-- Indexes for backtest query patterns
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_syntheses_timestamp ON syntheses(synthesis_timestamp);
CREATE INDEX IF NOT EXISTS idx_syntheses_investigation ON syntheses(investigation_id);
CREATE INDEX IF NOT EXISTS idx_manifest_kind ON synthesis_substrate_manifest(entity_kind);
CREATE INDEX IF NOT EXISTS idx_manifest_entity ON synthesis_substrate_manifest(entity_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_synthesis ON outcomes(synthesis_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_observed ON outcomes(observed_at);
CREATE INDEX IF NOT EXISTS idx_tier_overrides_set_at ON chunk_tier_overrides(set_at);
CREATE INDEX IF NOT EXISTS idx_edges_extracted ON edges(extracted_at);
"""


# Tables this schema creates. Used by tests + the diagnostic CLI.
SCHEMA_TABLES: tuple[str, ...] = (
    "documents", "chunks", "nodes", "edges",
    "syntheses", "synthesis_substrate_manifest",
    "outcomes", "chunk_tier_overrides",
)


def init_database(con: LockedConnection) -> None:
    """Initialize the Antiek graph schema on a write-locked connection.

    Idempotent. Pass a ``LockedConnection`` from
    ``runtime/db_lock.connect_write`` — the architecture_notes §2.3
    only-writer invariant requires every DDL pass through the same
    coordinator that DML passes through."""
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"init_database requires a LockedConnection (got {type(con).__name__}). "
            "Use runtime.db_lock.connect_write(db_path) or pass the result of "
            "connect_write into this function."
        )
    con.execute(ANTIEK_GRAPH_SCHEMA_V1_SQL)


def init_database_at_path(db_path: str) -> None:
    """Convenience: acquire a write lock on ``db_path`` and run
    ``init_database``. Used by tests + the CLI; production callers
    should manage their own lock lifecycles."""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = connect_write(db_path, purpose="graph_schema_init")
    try:
        init_database(con)
    finally:
        con.close()


def list_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Return the table names in main schema. Read-only diagnostic."""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Initialize the Antiek graph schema")
    p.add_argument("--db-path", required=True, help="Path to DuckDB file")
    args = p.parse_args()
    init_database_at_path(args.db_path)
    con = duckdb.connect(args.db_path, read_only=True)
    try:
        for t in list_tables(con):
            print(f"  {t}")
    finally:
        con.close()
