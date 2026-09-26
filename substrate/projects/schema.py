"""Schema and vocabulary for projects and tab trees (THREAD-CONTRACT §1.5, §1.6).

The vocabularies below are the server's validated sets. Contract rev 9 (the
per-product projects: Books, Converse, Speak, Autonomous Research) extends
them here, in one place, without a table migration: every column that holds
one of these values is plain VARCHAR, checked in code.

The project registry extends ``write_folders`` and ``write_folder_members``
in place with additive ``ALTER … ADD COLUMN IF NOT EXISTS``. DuckDB cannot
add a column with a NOT NULL constraint, so readers COALESCE the new columns
to their defaults, and a folder row written before this schema still reads
as a project.

The tab tables:

- ``project_tabs``: one tree per (owner, project, mothership), with a version
  for compare-and-set.
- ``project_tab_counters``: the project-wide ``next_public_number``, on its
  own row, because public numbers span every mothership of a project.
- ``tab_public_numbers`` and ``tab_hier_numbers``: the number registers.
  A row is written once, in the transaction that issues its number, and is
  never updated or deleted, so a dropped tab never frees a number.
- ``project_tab_retirements``: a row per close, holding the whole node.
  ``restored_at`` is its only mutable column, and it moves once, from null
  to the restoring PUT's time.
"""

from __future__ import annotations

from typing import Any

from runtime.db_lock import LockedConnection
from substrate.write.folders import ensure_folders_schema

#: The motherships a tab tree may belong to (contract §1.6, rev 7).
MOTHERSHIPS: tuple[str, ...] = ("research", "writing", "reading")

#: Project kinds (contract §1.5). A ``reading`` project is a standalone book
#: with a ``primary_document_id``, promoted in place to ``project``.
PROJECT_KINDS: tuple[str, ...] = ("project", "reading")

#: What a project member may be (contract §1.5).
MEMBER_KINDS: tuple[str, ...] = ("node", "investigation", "document", "deliverable")

#: Tab kinds by pane side (contract Part 2 §2.2, rev 7). Left tabs are
#: documents; right tabs are agent tabs (each a view of one thread), the
#: Findings and flags tabs, and Writing's block outline. ``research`` is on
#: both sides: left is a deep research spawned from a document, opened as
#: core material (R3, and §2.2's side inheritance); right is a research as
#: an agent you talk to (R6, R18).
TAB_KINDS_BY_SIDE: dict[str, tuple[str, ...]] = {
    "left": ("reader", "document", "research"),
    "right": ("research", "dialogue", "reformat", "diligence", "island", "findings", "flags", "block"),
}

#: ``branch_origin.kind`` values (contract §1.6, rev 7). "island" is the UI
#: name of ``selection``; it is never a wire value.
BRANCH_ORIGIN_KINDS: tuple[str, ...] = (
    "footnote", "reference", "citation", "selection", "research", "manual", "agent", "derivation",
)

#: How a tab left its tree (contract §1.6).
CLOSE_MODES: tuple[str, ...] = ("close", "prune", "lift_children")

TABS_DDL = """
CREATE TABLE IF NOT EXISTS project_tabs (
  owner_user_id VARCHAR NOT NULL,
  project_id VARCHAR NOT NULL,
  mothership VARCHAR NOT NULL,
  tree_json VARCHAR NOT NULL,
  active_left VARCHAR,
  active_right VARCHAR,
  next_child_index_json VARCHAR NOT NULL,
  version BIGINT NOT NULL CHECK (version >= 1),
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (owner_user_id, project_id, mothership)
);
CREATE TABLE IF NOT EXISTS project_tab_counters (
  owner_user_id VARCHAR NOT NULL,
  project_id VARCHAR NOT NULL,
  next_public_number BIGINT NOT NULL CHECK (next_public_number >= 1),
  PRIMARY KEY (owner_user_id, project_id)
);
CREATE TABLE IF NOT EXISTS tab_public_numbers (
  owner_user_id VARCHAR NOT NULL,
  project_id VARCHAR NOT NULL,
  public_number BIGINT NOT NULL CHECK (public_number >= 1),
  tab_id VARCHAR NOT NULL,
  mothership VARCHAR NOT NULL,
  issued_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (owner_user_id, project_id, public_number),
  UNIQUE (owner_user_id, project_id, tab_id)
);
CREATE TABLE IF NOT EXISTS tab_hier_numbers (
  owner_user_id VARCHAR NOT NULL,
  project_id VARCHAR NOT NULL,
  mothership VARCHAR NOT NULL,
  hier_number VARCHAR NOT NULL,
  tab_id VARCHAR NOT NULL,
  issued_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (owner_user_id, project_id, mothership, hier_number),
  UNIQUE (owner_user_id, project_id, mothership, tab_id)
);
CREATE TABLE IF NOT EXISTS project_tab_retirements (
  owner_user_id VARCHAR NOT NULL,
  project_id VARCHAR NOT NULL,
  mothership VARCHAR NOT NULL,
  tab_id VARCHAR NOT NULL,
  closed_at TIMESTAMPTZ NOT NULL,
  close_mode VARCHAR NOT NULL CHECK (close_mode IN ('close', 'prune', 'lift_children')),
  node_json VARCHAR NOT NULL,
  restored_at TIMESTAMPTZ,
  PRIMARY KEY (owner_user_id, project_id, mothership, tab_id, closed_at)
);
"""

#: The project columns ``write_folders`` gains. The folder's ``name`` is the
#: project's title (one column, so Write's ``/write/folders`` alias and
#: ``/projects`` can never disagree about it).
_FOLDER_COLUMNS = (
    "ALTER TABLE write_folders ADD COLUMN IF NOT EXISTS kind VARCHAR DEFAULT 'project'",
    "ALTER TABLE write_folders ADD COLUMN IF NOT EXISTS sort_order DOUBLE DEFAULT 0",
    "ALTER TABLE write_folders ADD COLUMN IF NOT EXISTS pinned BOOLEAN DEFAULT FALSE",
    "ALTER TABLE write_folders ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ",
    "ALTER TABLE write_folders ADD COLUMN IF NOT EXISTS primary_document_id VARCHAR",
    "ALTER TABLE write_folders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
    "ALTER TABLE write_folder_members ADD COLUMN IF NOT EXISTS member_kind VARCHAR DEFAULT 'node'",
)


def init_projects_schema(con: LockedConnection) -> None:
    """Create or extend every table this package uses (idempotent). Run it
    on a writer connection before opening a transaction."""
    ensure_folders_schema(con)
    for statement in _FOLDER_COLUMNS:
        con.execute(statement)
    con.execute(TABS_DDL)


def table_exists(con: Any, table: str) -> bool:
    """Whether ``table`` exists. Read paths use this instead of running DDL:
    a read connection cannot create, and a GET takes no write lock."""
    row = con.execute(
        "SELECT 1 FROM duckdb_tables() WHERE table_name = ? LIMIT 1", [table]
    ).fetchone()
    return row is not None


def column_exists(con: Any, table: str, column: str) -> bool:
    """Whether ``table.column`` exists (the project columns arrive with the
    first write after deploy; a read before that sees the legacy shape)."""
    row = con.execute(
        "SELECT 1 FROM duckdb_columns() WHERE table_name = ? AND column_name = ? LIMIT 1",
        [table, column],
    ).fetchone()
    return row is not None
