"""Additive DuckDB schema for workstations (workstation-tabs SPR-01).

Three tables, following the substrate/books/highlights/schema.py
conventions: one DDL constant, CREATE TABLE IF NOT EXISTS throughout
(idempotent), CHECK constraints mirroring the application-layer validation,
initialized on an existing writer connection (every write goes through
runtime/db_lock.connect_write).

The REFS-ONLY contract at rest: a tab's surface_payload_json carries ids
and small locators, NEVER content — a payload over the byte cap violates
the CHECK (the backstop for writers that skip the API's 422). NO window
geometry anywhere — rects/z/order are session-scoped by design (the spec's
replay-open rule), so no column exists to hold them.

The color_token vocabulary is the design palette's NAMED ACCENTS
(apps/reading/src/design/tokens.ts — sun/aurora/emperor + success + the
muted state tone), closed; the surface_kind vocabulary is the window-page
kinds (WINDOW_PAGES, openWindow.ts) + "route" + the corpus tabTree's
TabKind values (reader/research/document/companion/thread/flags —
tabTree.ts:54, the reconciliation note's D6).
"""

from __future__ import annotations

from typing import Any, Protocol

from runtime.db_lock import LockedConnection


class SqlExecutor(Protocol):
    """The one call every connection in this package needs (the unit-1
    convention): write side (LockedConnection) and read side
    (connect_read's DuckDBPyConnection) both satisfy it structurally."""

    def execute(self, sql: str, parameters: Any = None) -> Any: ...


#: The design palette's named accents (tokens.ts) — the workstation color
#: vocabulary, closed.
WORKSTATION_COLOR_TOKENS = ("sun", "aurora", "emperor", "success", "muted")

#: The eligible surface vocabulary: the WINDOW_PAGES kinds (openWindow.ts)
#: + "route" + the corpus tabTree's TabKind values (tabTree.ts:54).
WINDOW_PAGE_KINDS = ("stats", "library", "subaction", "researchArtifactReceipt", "reader")
CORPUS_TAB_KINDS = ("reader", "research", "document", "companion", "thread", "flags")
SURFACE_KINDS = tuple(
    dict.fromkeys([*WINDOW_PAGE_KINDS, "route", *CORPUS_TAB_KINDS])
)

#: The small-title cap (a workstation name is a label, never content).
WORKSTATION_NAME_MAX_CHARS = 80
#: The refs-only backstop: a tab payload beyond this is content smuggling.
TAB_PAYLOAD_MAX_BYTES = 2000

DDL = f"""
CREATE TABLE IF NOT EXISTS workstations (
  workstation_id VARCHAR PRIMARY KEY,
  owner_user_id VARCHAR NOT NULL,
  name VARCHAR NOT NULL CHECK (
    char_length(name) BETWEEN 1 AND {WORKSTATION_NAME_MAX_CHARS}
  ),
  color_token VARCHAR NOT NULL CHECK (
    color_token IN ('sun', 'aurora', 'emperor', 'success', 'muted')
  ),
  position INTEGER NOT NULL CHECK (position >= 0),
  revision INTEGER NOT NULL CHECK (revision >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workstation_tabs (
  tab_id VARCHAR PRIMARY KEY,
  workstation_id VARCHAR NOT NULL REFERENCES workstations(workstation_id),
  position INTEGER NOT NULL CHECK (position >= 0),
  surface_kind VARCHAR NOT NULL CHECK (
    surface_kind IN ({", ".join(f"'{k}'" for k in SURFACE_KINDS)})
  ),
  surface_payload_json VARCHAR NOT NULL CHECK (
    char_length(surface_payload_json) <= {TAB_PAYLOAD_MAX_BYTES}
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workstation_tabs_workstation
  ON workstation_tabs(workstation_id, position);

CREATE TABLE IF NOT EXISTS workstation_tab_trees (
  workstation_id VARCHAR PRIMARY KEY REFERENCES workstations(workstation_id),
  owner_user_id VARCHAR NOT NULL,
  tree_json VARCHAR NOT NULL,
  version INTEGER NOT NULL CHECK (version >= 0),
  -- The allocate counter: monotonic, NEVER reused — a closed tab's number
  -- is retired, never re-issued (the corpus tabTree contract).
  next_public_number INTEGER NOT NULL DEFAULT 1 CHECK (next_public_number >= 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_workstations_schema(con: LockedConnection) -> None:
    """Create the additive workstation schema on an existing writer
    connection (idempotent)."""
    con.execute(DDL)


def workstations_tables_exist(con: object) -> bool:
    """Whether the tables are present (read paths never run DDL)."""
    row = con.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM duckdb_tables() WHERE table_name = 'workstation_tab_trees' LIMIT 1"
    ).fetchone()
    return row is not None
