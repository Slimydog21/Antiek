"""Additive DuckDB schema for the diligence queue (autonomous-diligence
SPR-01).

One table, following the substrate/books/highlights/schema.py conventions:
a single DDL constant, CREATE TABLE IF NOT EXISTS throughout (idempotent),
CHECK constraints mirroring the application-layer validation, initialized
on an existing writer connection (every write goes through
runtime/db_lock.connect_write).

The REFS-ONLY contract, enforced at rest: a queue row carries the flag's
kind, the object's stable ref (a distilled node id, or a normalized concept
key), an optional SHORT note (length-capped by CHECK), the source
investigation/document ids, and its lifecycle status — never the object's
text beyond its ref, never book body, never thread content. The queue is
the one new store this pillar adds; letting it carry content would make it
a shadow copy of distilled nodes (and a withheld-text side channel) — the
CHECKs are the backstop for any writer that skips the API's 422s.
"""

from __future__ import annotations

from typing import Any, Protocol

from runtime.db_lock import LockedConnection


class SqlExecutor(Protocol):
    """The one call every connection in this package needs (the highlights
    convention): write side (LockedConnection) and read side
    (connect_read's DuckDBPyConnection) both satisfy it structurally."""

    def execute(self, sql: str, parameters: Any = None) -> Any: ...


#: The flag vocabulary (the spec's closed set). open_question/insight flags
#: reference a distilled graph node; a concept flag carries a normalized
#: concept key.
FLAG_KINDS = ("concept", "open_question", "insight")

#: The lifecycle (the spec's closed set). queued → spawned (SPR-02 writes
#: the spawned_investigation_id) → done (SPR-03's lazy projection); dismissed
#: is the operator's own terminal.
FLAG_STATUSES = ("queued", "spawned", "dismissed", "done")

#: The note cap — a short operator remark, never content.
NOTE_MAX_CHARS = 280

#: The ref cap — a node id or a normalized concept key, bounded.
OBJECT_REF_MAX_CHARS = 200

DDL = f"""
CREATE TABLE IF NOT EXISTS diligence_queue (
  flag_id VARCHAR PRIMARY KEY,
  owner_user_id VARCHAR NOT NULL,
  kind VARCHAR NOT NULL CHECK (kind IN ('concept', 'open_question', 'insight')),
  object_ref VARCHAR NOT NULL CHECK (
    char_length(object_ref) BETWEEN 1 AND {OBJECT_REF_MAX_CHARS}
  ),
  note VARCHAR CHECK (note IS NULL OR char_length(note) <= {NOTE_MAX_CHARS}),
  source_investigation_id VARCHAR,
  source_document_id VARCHAR,
  status VARCHAR NOT NULL DEFAULT 'queued' CHECK (
    status IN ('queued', 'spawned', 'dismissed', 'done')
  ),
  spawned_investigation_id VARCHAR,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_diligence_queue_owner
  ON diligence_queue(owner_user_id, status, created_at);
"""


def init_diligence_schema(con: LockedConnection) -> None:
    """Create the additive diligence schema on an existing writer connection."""
    con.execute(DDL)


def diligence_table_exists(con: object) -> bool:
    """Whether the table is present (read paths must not run DDL — a CREATE
    on a read connection fails, and a GET acquires no write lock for this)."""
    row = con.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM duckdb_tables() WHERE table_name = 'diligence_queue' LIMIT 1"
    ).fetchone()
    return row is not None
