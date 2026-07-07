"""Research folders / block repository (specs/write/ SPR-03).

The operator's outlining workflow is "heavily reliant on the research
folders to drag insights into the outline." Today notes are scoped only by
``investigation_id`` — there is no cross-investigation collection. This
module adds folders.

The load-bearing invariant: **folders are views/edges over graph nodes,
not copies.** A block in two folders is ONE underlying node — adding it to
a folder records a membership edge (``write_folder_members``), never a
content copy. If folders copied content, provenance and edits would
diverge from the source node, which is the exact moat Write protects. A
maintainer must not later "fix" folders into a copy-store.

Folders span investigations (cross-investigation grouping is the whole
point — writing draws across investigations), so membership keys on
``node_id`` alone, independent of which investigation produced the node.

Schema note: the two tables are created by an idempotent
``ensure_folders_schema(con)`` rather than folded into
``graph/schema.py``'s ``init_database`` here, because that file is under
heavy concurrent edit by a sibling spec's parallel instance and a second
writer risks a mid-write collision. The DDL is identical in spirit to the
V1–V8 blocks there; folding it in as a V9 block is a safe one-line
follow-up once the parallel stream settles (recorded in the handoff). All
writes still go through ``runtime/db_lock.connect_write`` (single-writer
invariant intact); membership writes emit a typed folder event.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

try:
    from ...runtime.db_lock import LockedConnection
    from ..event_log import emit_typed
    from ..graph.ops import new_random_id
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.graph.ops import new_random_id  # type: ignore[no-redef]

# Folder events are typed when available (codegen-registered). The import
# is defensive: if the sibling stream's concurrent events.py edits have not
# yet landed the payloads, folders still function (membership is recorded
# via db_lock writes) and emit falls back to an untyped event.
try:
    from substrate.schemas.events import (
        FolderBlockAddedPayload,
        FolderBlockRemovedPayload,
        FolderCreatedPayload,
    )
    _TYPED_FOLDER_EVENTS = True
except ImportError:  # pragma: no cover — payloads not yet registered
    _TYPED_FOLDER_EVENTS = False


FOLDERS_SCHEMA_SQL = """
-- Research folders — cross-investigation collections of blocks.
CREATE TABLE IF NOT EXISTS write_folders (
    folder_id      TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    owner_user_id  TEXT NOT NULL DEFAULT '__operator__',
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata       TEXT
);

-- Membership edges — a folder groups node references. node_id is a SOFT
-- reference (a view over the node, NOT a copy); the SAME node can belong
-- to many folders (one underlying node, many memberships). The composite
-- PK makes membership idempotent and forbids duplicate edges.
CREATE TABLE IF NOT EXISTS write_folder_members (
    folder_id   TEXT NOT NULL REFERENCES write_folders(folder_id),
    node_id     TEXT NOT NULL,
    added_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (folder_id, node_id)
);

CREATE INDEX IF NOT EXISTS idx_write_folder_members_node
    ON write_folder_members(node_id);
"""


@dataclass(frozen=True)
class Folder:
    folder_id: str
    name: str
    owner_user_id: str
    member_count: int = 0


def _assert_write_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"folder writes require a LockedConnection (got {type(con).__name__}). "
            "Acquire via runtime.db_lock.connect_write(db_path, purpose=...)."
        )


def _folders_schema_exists(con: Any) -> bool:
    """Read-only probe: are the folder tables present yet? A fresh/warm graph
    that has never had a folder created has NOT run ensure_folders_schema, so
    the read paths must degrade to empty rather than raise OperationalError."""
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='write_folders'"
    ).fetchone()
    return row is not None


def ensure_folders_schema(con: LockedConnection) -> None:
    """Idempotent: create the folder tables if absent. Safe to call on
    every folder write."""
    _assert_write_locked(con)
    con.execute(FOLDERS_SCHEMA_SQL)


def create_folder(
    con: LockedConnection, *, name: str,
    owner_user_id: str = "__operator__",
    folder_id: str | None = None,
    investigation_id: str = "__operator__",
) -> str:
    """Create a folder. Returns its folder_id."""
    _assert_write_locked(con)
    ensure_folders_schema(con)
    fid = folder_id or new_random_id("fld")
    con.execute(
        "INSERT INTO write_folders (folder_id, name, owner_user_id) VALUES (?, ?, ?)",
        [fid, name, owner_user_id],
    )
    if _TYPED_FOLDER_EVENTS:
        emit_typed(
            investigation_id, FolderCreatedPayload(folder_id=fid, name=name),
            role="write_repository",
        )
    return fid


def add_block_to_folder(
    con: LockedConnection, *, folder_id: str, node_id: str,
    investigation_id: str = "__operator__",
) -> bool:
    """Add a node reference to a folder (a membership edge, NOT a copy).
    Idempotent — re-adding the same node is a no-op. Returns True if a new
    membership was created."""
    _assert_write_locked(con)
    ensure_folders_schema(con)
    exists = con.execute(
        "SELECT 1 FROM write_folder_members WHERE folder_id = ? AND node_id = ?",
        [folder_id, node_id],
    ).fetchone() is not None
    if exists:
        return False
    con.execute(
        "INSERT INTO write_folder_members (folder_id, node_id) VALUES (?, ?)",
        [folder_id, node_id],
    )
    if _TYPED_FOLDER_EVENTS:
        emit_typed(
            investigation_id,
            FolderBlockAddedPayload(folder_id=folder_id, node_id=node_id),
            role="write_repository",
        )
    return True


def remove_block_from_folder(
    con: LockedConnection, *, folder_id: str, node_id: str,
    investigation_id: str = "__operator__",
) -> bool:
    """Remove a node reference from a folder. The node itself is untouched
    (the folder is a view). Returns True if a membership was removed."""
    _assert_write_locked(con)
    ensure_folders_schema(con)
    exists = con.execute(
        "SELECT 1 FROM write_folder_members WHERE folder_id = ? AND node_id = ?",
        [folder_id, node_id],
    ).fetchone() is not None
    if not exists:
        return False
    con.execute(
        "DELETE FROM write_folder_members WHERE folder_id = ? AND node_id = ?",
        [folder_id, node_id],
    )
    if _TYPED_FOLDER_EVENTS:
        emit_typed(
            investigation_id,
            FolderBlockRemovedPayload(folder_id=folder_id, node_id=node_id),
            role="write_repository",
        )
    return True


def list_folders(con: Any) -> list[Folder]:
    """All folders with their member counts. Read-only; deterministic."""
    if not _folders_schema_exists(con):
        return []
    rows = con.execute(
        "SELECT f.folder_id, f.name, f.owner_user_id, "
        "       COUNT(m.node_id) AS member_count "
        "FROM write_folders f "
        "LEFT JOIN write_folder_members m ON f.folder_id = m.folder_id "
        "GROUP BY f.folder_id, f.name, f.owner_user_id "
        "ORDER BY f.name, f.folder_id"
    ).fetchall()
    return [Folder(folder_id=r[0], name=r[1], owner_user_id=r[2], member_count=int(r[3])) for r in rows]


def list_folder_node_ids(con: Any, folder_id: str) -> list[str]:
    """The node ids in a folder (deterministic order)."""
    if not _folders_schema_exists(con):
        return []
    rows = con.execute(
        "SELECT node_id FROM write_folder_members WHERE folder_id = ? ORDER BY node_id",
        [folder_id],
    ).fetchall()
    return [r[0] for r in rows]


def folders_for_node(con: Any, node_id: str) -> list[str]:
    """Every folder a node belongs to — demonstrates multi-membership over
    ONE underlying node (not copies)."""
    if not _folders_schema_exists(con):
        return []
    rows = con.execute(
        "SELECT folder_id FROM write_folder_members WHERE node_id = ? ORDER BY folder_id",
        [node_id],
    ).fetchall()
    return [r[0] for r in rows]


def is_block_in_folder(con: Any, *, folder_id: str, node_id: str) -> bool:
    """Read-only: whether ``node_id`` is a member of ``folder_id``."""
    if not _folders_schema_exists(con):
        return False
    return (
        con.execute(
            "SELECT 1 FROM write_folder_members WHERE folder_id = ? AND node_id = ?",
            [folder_id, node_id],
        ).fetchone()
        is not None
    )
