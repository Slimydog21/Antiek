"""Additive DuckDB schema for anchored highlights (anchor-first SPR-01).

One table, following the substrate/feedback/schema.py conventions: a single
DDL constant, CREATE TABLE IF NOT EXISTS throughout (idempotent), CHECK
constraints mirroring the application-layer validation, initialized on an
existing writer connection (the write-lock discipline of
substrate/graph/schema.py — every write goes through
runtime/db_lock.connect_write).

The anchor column set is the proven NodeTextAnchor persistence shape
(substrate/feedback/schema.py:8-26) with ONE deliberate difference per the
spec: anchor_quote / anchor_prefix / anchor_suffix are NULLABLE, and the
final CHECK ties their NULL-ness to `servable_at_pin` — a non-servable
book's body text is never persisted in an anchor row (rights truth at rest;
the §9.0 no-leak chokepoint extended from transit to rest).
"""

from __future__ import annotations

from typing import Any, Protocol

from runtime.db_lock import LockedConnection


class SqlExecutor(Protocol):
    """The one call every connection in this package needs. Both the write
    side (runtime.db_lock.LockedConnection) and the read side
    (connect_read's DuckDBPyConnection) satisfy it structurally, so read
    paths (GET) and write paths (POST/DELETE/re-resolution) share the store
    without lying to the type checker about which they hold."""

    def execute(self, sql: str, parameters: Any = None) -> Any: ...


DDL = """
CREATE TABLE IF NOT EXISTS anchored_highlights (
  anchor_id VARCHAR PRIMARY KEY,
  owner_user_id VARCHAR NOT NULL,
  document_id VARCHAR NOT NULL,
  normalization VARCHAR NOT NULL CHECK (normalization = 'unicode-nfc-v1'),
  anchor_node_id VARCHAR NOT NULL,
  anchor_node_text_sha256 VARCHAR NOT NULL,
  anchor_start_scalar INTEGER NOT NULL CHECK (anchor_start_scalar >= 0),
  anchor_end_scalar INTEGER NOT NULL CHECK (anchor_end_scalar > anchor_start_scalar),
  servable_at_pin BOOLEAN NOT NULL,
  anchor_quote VARCHAR,
  anchor_prefix VARCHAR,
  anchor_suffix VARCHAR,
  selection_text_sha256 VARCHAR NOT NULL,
  page_index_hint INTEGER,
  source VARCHAR NOT NULL CHECK (source IN (
    'floatmenu_note', 'floatmenu_dialogue', 'floatmenu_search',
    'floatmenu_deep_research', 'pin'
  )),
  status VARCHAR NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'drifted', 'orphaned')),
  investigation_id VARCHAR,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (
    (servable_at_pin = TRUE
      AND anchor_quote IS NOT NULL
      AND anchor_prefix IS NOT NULL
      AND anchor_suffix IS NOT NULL)
    OR
    (servable_at_pin = FALSE
      AND anchor_quote IS NULL
      AND anchor_prefix IS NULL
      AND anchor_suffix IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_anchored_highlights_document
  ON anchored_highlights(document_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_anchored_highlights_owner
  ON anchored_highlights(owner_user_id, created_at);
"""


def init_highlights_schema(con: LockedConnection) -> None:
    """Create the additive highlights schema on an existing writer connection."""
    con.execute(DDL)


def highlights_table_exists(con: object) -> bool:
    """Whether the table is present (read paths must not run DDL — a CREATE
    on a read connection fails, and a GET acquires no write lock for this)."""
    row = con.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM duckdb_tables() WHERE table_name = 'anchored_highlights' LIMIT 1"
    ).fetchone()
    return row is not None
