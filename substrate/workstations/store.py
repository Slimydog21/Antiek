"""Connection-taking persistence for workstations (workstation-tabs SPR-01).

Row CRUD under LockedConnection, the unit-1 conventions: frozen dataclasses,
every write through one method, the idempotent schema ensured on write entry
points. Concurrency is optimistic throughout: a full-replace carries the
revision the client last saw (a stale revision returns None → the API's
409, never a silent clobber), and the tab-tree save carries the expected
version (the corpus TabTreeAdapter's save contract).

The allocate counter is server-side, monotonic, NEVER reused — a closed
tab's number is retired, never re-issued (the corpus tabTree contract:
numbers never change, never get taken twice).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.workstations.schema import (
    SqlExecutor,
    init_workstations_schema,
    workstations_tables_exist,
)


def mint_workstation_id() -> str:
    return f"ws-{secrets.token_hex(8)}"


def mint_tab_id() -> str:
    return f"tab-{secrets.token_hex(8)}"


@dataclass(frozen=True, slots=True)
class WorkstationRow:
    workstation_id: str
    owner_user_id: str
    name: str
    color_token: str
    position: int
    revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class WorkstationTabRow:
    tab_id: str
    workstation_id: str
    position: int
    surface_kind: str
    surface_payload_json: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class WorkstationWithTabs:
    workstation: WorkstationRow
    tabs: tuple[WorkstationTabRow, ...]


@dataclass(frozen=True, slots=True)
class TabTreeRow:
    workstation_id: str
    owner_user_id: str
    tree_json: str
    version: int
    next_public_number: int
    updated_at: str


def _to_workstation(r: Any) -> WorkstationRow:
    return WorkstationRow(
        workstation_id=str(r[0]),
        owner_user_id=str(r[1]),
        name=str(r[2]),
        color_token=str(r[3]),
        position=int(r[4]),
        revision=int(r[5]),
        created_at=str(r[6]),
        updated_at=str(r[7]),
    )


def _to_tab(r: Any) -> WorkstationTabRow:
    return WorkstationTabRow(
        tab_id=str(r[0]),
        workstation_id=str(r[1]),
        position=int(r[2]),
        surface_kind=str(r[3]),
        surface_payload_json=str(r[4]),
        created_at=str(r[5]),
        updated_at=str(r[6]),
    )


class WorkstationStore:
    """Persist and read workstations + their tabs + tab trees."""

    def create_workstation(
        self,
        con: LockedConnection,
        *,
        owner_user_id: str,
        name: str,
        color_token: str,
        position: int,
    ) -> WorkstationRow:
        init_workstations_schema(con)
        wid = mint_workstation_id()
        con.execute(
            "INSERT INTO workstations (workstation_id, owner_user_id, name, "
            "color_token, position, revision) VALUES (?, ?, ?, ?, ?, 1)",
            [wid, owner_user_id, name, color_token, position],
        )
        row = self.get_for_owner(con, owner_user_id=owner_user_id, workstation_id=wid)
        assert row is not None  # the insert above just landed
        return row

    def get_for_owner(
        self, con: SqlExecutor, *, owner_user_id: str, workstation_id: str
    ) -> WorkstationRow | None:
        """One workstation, owner-scoped (another owner's id is a None)."""
        if not workstations_tables_exist(con):
            return None
        row = con.execute(
            "SELECT workstation_id, owner_user_id, name, color_token, position, "
            "revision, created_at, updated_at FROM workstations "
            "WHERE owner_user_id = ? AND workstation_id = ? LIMIT 1",
            [owner_user_id, workstation_id],
        ).fetchone()
        return None if row is None else _to_workstation(row)

    def list_for_owner(self, con: SqlExecutor, *, owner_user_id: str) -> list[WorkstationWithTabs]:
        """The owner's full set, position-ordered, tabs position-ordered."""
        if not workstations_tables_exist(con):
            return []
        ws_rows = con.execute(
            "SELECT workstation_id, owner_user_id, name, color_token, position, "
            "revision, created_at, updated_at FROM workstations "
            "WHERE owner_user_id = ? ORDER BY position ASC, workstation_id ASC",
            [owner_user_id],
        ).fetchall()
        out: list[WorkstationWithTabs] = []
        for raw in ws_rows:
            ws = _to_workstation(raw)
            tab_rows = con.execute(
                "SELECT tab_id, workstation_id, position, surface_kind, "
                "surface_payload_json, created_at, updated_at FROM workstation_tabs "
                "WHERE workstation_id = ? ORDER BY position ASC, tab_id ASC",
                [ws.workstation_id],
            ).fetchall()
            out.append(
                WorkstationWithTabs(
                    workstation=ws, tabs=tuple(_to_tab(r) for r in tab_rows)
                )
            )
        return out

    def replace_workstation(
        self,
        con: LockedConnection,
        *,
        owner_user_id: str,
        workstation_id: str,
        name: str,
        color_token: str,
        tabs: list[tuple[str, int, str, str]],  # (tab_id, position, kind, payload_json)
        expected_revision: int,
    ) -> WorkstationRow | None:
        """FULL-REPLACE name/color + the tab list, optimistic on the revision.
        Returns the updated row, or None when expected_revision is STALE
        (the API maps None → 409 — never a silent clobber). The tab list
        replaces wholesale inside the caller's transaction."""
        init_workstations_schema(con)
        row = self.get_for_owner(
            con, owner_user_id=owner_user_id, workstation_id=workstation_id
        )
        if row is None:
            return None  # the API's 404 (not the requester's)
        if expected_revision != row.revision:
            return None  # stale — the API's 409 distinguishes by its own read
        con.execute(
            "UPDATE workstations SET name = ?, color_token = ?, "
            "revision = revision + 1, updated_at = CURRENT_TIMESTAMP "
            "WHERE workstation_id = ?",
            [name, color_token, workstation_id],
        )
        con.execute(
            "DELETE FROM workstation_tabs WHERE workstation_id = ?",
            [workstation_id],
        )
        if tabs:
            con.executemany(
                "INSERT INTO workstation_tabs (tab_id, workstation_id, position, "
                "surface_kind, surface_payload_json) VALUES (?, ?, ?, ?, ?)",
                [
                    (tab_id, workstation_id, position, kind, payload_json)
                    for tab_id, position, kind, payload_json in tabs
                ],
            )
        out = self.get_for_owner(
            con, owner_user_id=owner_user_id, workstation_id=workstation_id
        )
        assert out is not None
        return out

    def delete_workstation(
        self, con: LockedConnection, *, owner_user_id: str, workstation_id: str
    ) -> bool:
        """Delete the workstation + its tabs + its tab tree. Idempotent:
        deleting a missing (or another owner's) workstation returns False —
        the API's 404/204 decision."""
        init_workstations_schema(con)
        row = self.get_for_owner(
            con, owner_user_id=owner_user_id, workstation_id=workstation_id
        )
        if row is None:
            return False
        con.execute(
            "DELETE FROM workstation_tabs WHERE workstation_id = ?", [workstation_id]
        )
        con.execute(
            "DELETE FROM workstation_tab_trees WHERE workstation_id = ?",
            [workstation_id],
        )
        con.execute("DELETE FROM workstations WHERE workstation_id = ?", [workstation_id])
        return True


class TabTreeStore:
    """The corpus tabTree's server side (the TabTreeAdapter contract):
    load · save(expected_version) · allocate."""

    def load_tree(
        self, con: SqlExecutor, *, owner_user_id: str, workstation_id: str
    ) -> TabTreeRow | None:
        """The tree snapshot + version — None when no tree exists yet (the
        caller serves the empty tree at version 0)."""
        if not workstations_tables_exist(con):
            return None
        row = con.execute(
            "SELECT workstation_id, owner_user_id, tree_json, version, "
            "next_public_number, updated_at FROM workstation_tab_trees "
            "WHERE owner_user_id = ? AND workstation_id = ? LIMIT 1",
            [owner_user_id, workstation_id],
        ).fetchone()
        if row is None:
            return None
        return TabTreeRow(
            workstation_id=str(row[0]),
            owner_user_id=str(row[1]),
            tree_json=str(row[2]),
            version=int(row[3]),
            next_public_number=int(row[4]),
            updated_at=str(row[5]),
        )

    def save_tree(
        self,
        con: LockedConnection,
        *,
        owner_user_id: str,
        workstation_id: str,
        tree_json: str,
        expected_version: int,
    ) -> TabTreeRow | None:
        """Save with optimistic concurrency: None when expected_version is
        stale (the client rebases — never a silent clobber)."""
        init_workstations_schema(con)
        existing = self.load_tree(
            con, owner_user_id=owner_user_id, workstation_id=workstation_id
        )
        if existing is None:
            if expected_version != 0:
                return None
            con.execute(
                "INSERT INTO workstation_tab_trees (workstation_id, "
                "owner_user_id, tree_json, version) VALUES (?, ?, ?, 1)",
                [workstation_id, owner_user_id, tree_json],
            )
        else:
            if expected_version != existing.version:
                return None
            con.execute(
                "UPDATE workstation_tab_trees SET tree_json = ?, "
                "version = version + 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE workstation_id = ?",
                [tree_json, workstation_id],
            )
        out = self.load_tree(
            con, owner_user_id=owner_user_id, workstation_id=workstation_id
        )
        assert out is not None
        return out

    def allocate_number(
        self, con: LockedConnection, *, owner_user_id: str, workstation_id: str
    ) -> int:
        """The server-allocated public number: workstation-wide, monotonic,
        NEVER reused — a closed tab's number is retired, never re-issued."""
        init_workstations_schema(con)
        existing = self.load_tree(
            con, owner_user_id=owner_user_id, workstation_id=workstation_id
        )
        if existing is None:
            con.execute(
                "INSERT INTO workstation_tab_trees (workstation_id, "
                "owner_user_id, tree_json, version, next_public_number) "
                "VALUES (?, ?, ?, 0, 2)",
                [workstation_id, owner_user_id, "{}"],
            )
            return 1
        n = existing.next_public_number
        con.execute(
            "UPDATE workstation_tab_trees SET next_public_number = next_public_number + 1, "
            "updated_at = CURRENT_TIMESTAMP WHERE workstation_id = ?",
            [workstation_id],
        )
        return n


# Re-export so consumers read the vocabulary from one place.
__all__ = [
    "TabTreeRow",
    "TabTreeStore",
    "WorkstationRow",
    "WorkstationStore",
    "WorkstationTabRow",
    "WorkstationWithTabs",
    "mint_tab_id",
    "mint_workstation_id",
]
