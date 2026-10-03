"""The project registry over ``write_folders`` (THREAD-CONTRACT §1.5).

A project IS a folder row: ``/write/folders`` stays Write's alias over the
same rows, and a folder's ``name`` is the project's title. Every read and
write is scoped to the requesting owner; another owner's project is
indistinguishable from a missing one.

A standalone book is ``kind: reading`` with a ``primary_document_id``. It is
promoted in place to ``kind: project`` (same id, members and threads); a
project is never demoted back.

Members are soft references, as folder members always were: a membership
edge, never a copy. ``member_kind`` says what the id names. The primary key
stays ``(folder_id, node_id)``, so one id is one member of a project, and
adding it again under a different kind is refused rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.graph.ops import new_random_id
from substrate.projects.schema import MEMBER_KINDS, PROJECT_KINDS, column_exists, table_exists

TITLE_MAX = 200
MEMBER_ID_MAX = 256


class ProjectError(Exception):
    """A refusal the API maps to an HTTP status. ``code`` is the wire detail."""

    status = 422

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class ProjectNotFound(ProjectError):
    status = 404

    def __init__(self) -> None:
        super().__init__("project_not_found")


class MemberKindConflict(ProjectError):
    status = 409

    def __init__(self, existing: str) -> None:
        super().__init__("member_kind_conflict", f"this id is already a member as {existing}")


@dataclass(frozen=True, slots=True)
class Project:
    project_id: str
    title: str
    kind: str
    order: float
    pinned: bool
    archived_at: str | None
    primary_document_id: str | None
    created_at: str
    updated_at: str | None
    member_count: int


@dataclass(frozen=True, slots=True)
class Member:
    member_kind: str
    member_id: str
    added_at: str


def iso(value: Any) -> str | None:
    """A stored timestamp as UTC ISO 8601 with a ``Z``. A naive value is a
    legacy ``TIMESTAMP`` column written in UTC."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    text: str = value.astimezone(UTC).isoformat(timespec="microseconds")
    return text.replace("+00:00", "Z")


def _select(con: Any) -> str:
    """The project SELECT, over the extended columns when they exist and over
    their defaults when the first write since deploy has not added them."""
    member_count = "(SELECT COUNT(*) FROM write_folder_members m WHERE m.folder_id = f.folder_id)"
    if column_exists(con, "write_folders", "kind"):
        return (
            "SELECT f.folder_id, f.name, COALESCE(f.kind, 'project'), COALESCE(f.sort_order, 0), "
            "COALESCE(f.pinned, FALSE), f.archived_at, f.primary_document_id, f.created_at, "
            f"f.updated_at, {member_count} FROM write_folders f"
        )
    return (
        "SELECT f.folder_id, f.name, 'project', 0, FALSE, NULL, NULL, f.created_at, NULL, "
        f"{member_count} FROM write_folders f"
    )


def _to_project(r: Any) -> Project:
    return Project(
        project_id=str(r[0]),
        title=str(r[1]),
        kind=str(r[2]),
        order=float(r[3]),
        pinned=bool(r[4]),
        archived_at=iso(r[5]),
        primary_document_id=None if r[6] is None else str(r[6]),
        created_at=iso(r[7]) or "",
        updated_at=iso(r[8]),
        member_count=int(r[9]),
    )


def list_projects(con: Any, *, owner_user_id: str, include_archived: bool = False) -> list[Project]:
    """The owner's projects: pinned first, then by order, then oldest first."""
    if not table_exists(con, "write_folders"):
        return []
    sql = _select(con) + " WHERE f.owner_user_id = ?"
    if not include_archived and column_exists(con, "write_folders", "archived_at"):
        sql += " AND f.archived_at IS NULL"
    sql += " ORDER BY 5 DESC, 4, f.created_at, f.folder_id"
    return [_to_project(r) for r in con.execute(sql, [owner_user_id]).fetchall()]


def get_project(con: Any, *, owner_user_id: str, project_id: str) -> Project | None:
    """The owner's project, or None (missing and not-yours read the same)."""
    if not table_exists(con, "write_folders"):
        return None
    row = con.execute(
        _select(con) + " WHERE f.folder_id = ? AND f.owner_user_id = ?",
        [project_id, owner_user_id],
    ).fetchone()
    return None if row is None else _to_project(row)


def require_project(con: Any, *, owner_user_id: str, project_id: str) -> Project:
    project = get_project(con, owner_user_id=owner_user_id, project_id=project_id)
    if project is None:
        raise ProjectNotFound()
    return project


def _clean_title(title: Any) -> str:
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > TITLE_MAX:
        raise ProjectError("project_title_invalid", f"a title is 1 to {TITLE_MAX} characters")
    return title.strip()


def _document_exists(con: Any, document_id: str) -> bool:
    if not table_exists(con, "documents"):
        return False
    return con.execute(
        "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1", [document_id]
    ).fetchone() is not None


def create_project(
    con: LockedConnection,
    *,
    owner_user_id: str,
    title: Any,
    kind: Any = "project",
    primary_document_id: Any = None,
    now: datetime | None = None,
) -> Project:
    """Create a project. A ``reading`` project names the book it is for."""
    clean = _clean_title(title)
    if kind not in PROJECT_KINDS:
        raise ProjectError("project_kind_invalid", f"kind is one of {', '.join(PROJECT_KINDS)}")
    if kind == "reading":
        if not isinstance(primary_document_id, str) or not _document_exists(con, primary_document_id):
            raise ProjectError("primary_document_invalid", "a reading project names an existing document")
    elif primary_document_id is not None:
        raise ProjectError("primary_document_invalid", "only a reading project has a primary document")
    stamp = now or datetime.now(UTC)
    project_id = new_random_id("fld")
    con.execute(
        "INSERT INTO write_folders (folder_id, name, owner_user_id, kind, sort_order, pinned, "
        "primary_document_id, updated_at) VALUES (?, ?, ?, ?, 0, FALSE, ?, ?)",
        [project_id, clean, owner_user_id, kind, primary_document_id, stamp],
    )
    return require_project(con, owner_user_id=owner_user_id, project_id=project_id)


def update_project(
    con: LockedConnection,
    *,
    owner_user_id: str,
    project_id: str,
    changes: dict[str, Any],
    now: datetime | None = None,
) -> Project:
    """Apply a PATCH. ``changes`` holds only the fields the client sent:
    ``title``, ``order``, ``pinned``, ``archived`` (bool) and ``kind`` (only
    the ``reading`` → ``project`` promotion)."""
    current = require_project(con, owner_user_id=owner_user_id, project_id=project_id)
    unknown = sorted(set(changes) - {"title", "order", "pinned", "archived", "kind"})
    if unknown:
        raise ProjectError("project_patch_invalid", f"unknown fields: {', '.join(unknown)}")
    stamp = now or datetime.now(UTC)
    sets: list[str] = []
    params: list[Any] = []
    if "title" in changes:
        sets.append("name = ?")
        params.append(_clean_title(changes["title"]))
    if "order" in changes:
        order = changes["order"]
        if isinstance(order, bool) or not isinstance(order, int | float) or order != order:
            raise ProjectError("project_patch_invalid", "order is a number")
        sets.append("sort_order = ?")
        params.append(float(order))
    if "pinned" in changes:
        if not isinstance(changes["pinned"], bool):
            raise ProjectError("project_patch_invalid", "pinned is a boolean")
        sets.append("pinned = ?")
        params.append(changes["pinned"])
    if "archived" in changes:
        if not isinstance(changes["archived"], bool):
            raise ProjectError("project_patch_invalid", "archived is a boolean")
        if changes["archived"] and current.archived_at is None:
            sets.append("archived_at = ?")
            params.append(stamp)
        elif not changes["archived"]:
            sets.append("archived_at = NULL")
    if "kind" in changes and changes["kind"] != current.kind:
        if not (current.kind == "reading" and changes["kind"] == "project"):
            raise ProjectError("project_kind_change_refused", "a reading project may only be promoted to a project")
        sets.append("kind = 'project'")
    if sets:
        sets.append("updated_at = ?")
        params.append(stamp)
        con.execute(
            f"UPDATE write_folders SET {', '.join(sets)} WHERE folder_id = ? AND owner_user_id = ?",
            [*params, project_id, owner_user_id],
        )
    return require_project(con, owner_user_id=owner_user_id, project_id=project_id)


def _clean_member_id(member_id: Any) -> str:
    if not isinstance(member_id, str) or not member_id.strip() or len(member_id) > MEMBER_ID_MAX:
        raise ProjectError("member_id_invalid", f"a member id is 1 to {MEMBER_ID_MAX} characters")
    return member_id


def add_member(
    con: LockedConnection,
    *,
    owner_user_id: str,
    project_id: str,
    member_kind: Any,
    member_id: Any,
    now: datetime | None = None,
) -> str:
    """Add a membership edge. Returns ``added`` or ``already_member``."""
    require_project(con, owner_user_id=owner_user_id, project_id=project_id)
    if member_kind not in MEMBER_KINDS:
        raise ProjectError("member_kind_invalid", f"member_kind is one of {', '.join(MEMBER_KINDS)}")
    clean = _clean_member_id(member_id)
    existing = con.execute(
        "SELECT COALESCE(member_kind, 'node') FROM write_folder_members WHERE folder_id = ? AND node_id = ?",
        [project_id, clean],
    ).fetchone()
    if existing is not None:
        if existing[0] != member_kind:
            raise MemberKindConflict(str(existing[0]))
        return "already_member"
    con.execute(
        "INSERT INTO write_folder_members (folder_id, node_id, member_kind) VALUES (?, ?, ?)",
        [project_id, clean, member_kind],
    )
    con.execute(
        "UPDATE write_folders SET updated_at = ? WHERE folder_id = ?", [now or datetime.now(UTC), project_id]
    )
    return "added"


def remove_member(
    con: LockedConnection,
    *,
    owner_user_id: str,
    project_id: str,
    member_id: str,
    now: datetime | None = None,
) -> str:
    """Remove a membership edge (the member itself is untouched). Returns
    ``removed`` or ``not_member``."""
    require_project(con, owner_user_id=owner_user_id, project_id=project_id)
    exists = con.execute(
        "SELECT 1 FROM write_folder_members WHERE folder_id = ? AND node_id = ?", [project_id, member_id]
    ).fetchone()
    if exists is None:
        return "not_member"
    con.execute("DELETE FROM write_folder_members WHERE folder_id = ? AND node_id = ?", [project_id, member_id])
    con.execute(
        "UPDATE write_folders SET updated_at = ? WHERE folder_id = ?", [now or datetime.now(UTC), project_id]
    )
    return "removed"


def list_members(con: Any, *, owner_user_id: str, project_id: str) -> list[Member]:
    """The project's members, oldest first."""
    require_project(con, owner_user_id=owner_user_id, project_id=project_id)
    kind = "COALESCE(member_kind, 'node')" if column_exists(con, "write_folder_members", "member_kind") else "'node'"
    rows = con.execute(
        f"SELECT {kind}, node_id, added_at FROM write_folder_members WHERE folder_id = ? "
        "ORDER BY added_at, node_id",
        [project_id],
    ).fetchall()
    return [Member(member_kind=str(r[0]), member_id=str(r[1]), added_at=iso(r[2]) or "") for r in rows]
