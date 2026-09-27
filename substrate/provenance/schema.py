"""Additive DuckDB schema for bite-level provenance (reformat-provenance
SPR-01).

Two tables, following the substrate/books/highlights/schema.py conventions:
one DDL constant, CREATE TABLE IF NOT EXISTS throughout (idempotent), CHECK
constraints mirroring the application-layer validation, initialized on an
existing writer connection (every write goes through
runtime/db_lock.connect_write).

THE CONTRACT at rest: a generation record is the derived asset's birth
certificate (prompt · model · source · params · when · owner); a
bite-provenance row is one derived bite's defensible contribution account —
its CLASS (author_verbatim byte-PROVEN by the two hashes matching ·
llm_compressed · llm_expanded · research_supplemented with its
investigation), the source span refs (unit-1 anchor payloads into the CORE
document, NULL only with the honest no-direct-source), and the two hashes.
Text never lands here — hashes and refs only.
"""

from __future__ import annotations

from typing import Any, Protocol

from runtime.db_lock import LockedConnection


class SqlExecutor(Protocol):
    """The one call every connection in this package needs (the unit-1
    convention): write side (LockedConnection) and read side
    (connect_read's DuckDBPyConnection) both satisfy it structurally."""

    def execute(self, sql: str, parameters: Any = None) -> Any: ...


#: The contribution vocabulary (the spec's closed set).
CONTRIBUTION_CLASSES = (
    "author_verbatim",
    "llm_compressed",
    "llm_expanded",
    "research_supplemented",
)

DDL = """
CREATE TABLE IF NOT EXISTS generation_records (
  generation_id VARCHAR PRIMARY KEY,
  owner_user_id VARCHAR NOT NULL,
  source_document_id VARCHAR NOT NULL,
  derived_document_id VARCHAR NOT NULL,
  prompt VARCHAR NOT NULL,
  model VARCHAR NOT NULL,
  params_json VARCHAR NOT NULL,
  mostly_generated BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bite_provenance (
  bite_id VARCHAR PRIMARY KEY,
  generation_id VARCHAR NOT NULL REFERENCES generation_records(generation_id),
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  contribution_class VARCHAR NOT NULL CHECK (contribution_class IN (
    'author_verbatim', 'llm_compressed', 'llm_expanded', 'research_supplemented'
  )),
  source_refs_json VARCHAR,
  investigation_id VARCHAR,
  derived_text_sha256 VARCHAR NOT NULL,
  source_span_sha256 VARCHAR,
  -- The byte-verification invariant, at rest: an author_verbatim bite's two
  -- hashes MUST match (the pipeline verifies at write; this CHECK is the
  -- backstop for any writer that skips it).
  CHECK (
    contribution_class != 'author_verbatim'
    OR (source_span_sha256 IS NOT NULL
        AND derived_text_sha256 = source_span_sha256)
  ),
  -- research_supplemented carries its investigation; other classes never do.
  CHECK (
    (contribution_class = 'research_supplemented')
    = (investigation_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_bite_provenance_generation
  ON bite_provenance(generation_id, ordinal);
"""


def init_provenance_schema(con: LockedConnection) -> None:
    """Create the additive provenance schema on an existing writer
    connection (idempotent)."""
    con.execute(DDL)


def provenance_tables_exist(con: object) -> bool:
    """Whether the tables are present (read paths never run DDL)."""
    row = con.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM duckdb_tables() WHERE table_name = 'bite_provenance' LIMIT 1"
    ).fetchone()
    return row is not None
