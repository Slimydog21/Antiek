"""Runtime routing for physically isolated personal graph files."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def owner_graph_db_path(
    owner_id: str,
    *,
    root: Path | str | None = None,
    create_parent: bool = True,
) -> str:
    """Resolve one owner's graph without exposing identity in the filesystem.

    The historical operator keeps the canonical graph. Authenticated accounts
    never fall back to that shared file: they receive a domain-hashed path
    beneath ``ANTIEK_USER_GRAPH_DIR`` (or the local Antiek data directory).
    """
    owner = (owner_id or "").strip()
    if not owner:
        raise ValueError("owner_id is required")
    if owner == "__operator__":
        from substrate.graph import default_db_path

        return default_db_path()
    base = Path(
        root
        if root is not None
        else os.environ.get("ANTIEK_USER_GRAPH_DIR")
        or Path.home() / ".antiek" / "user-graphs"
    ).expanduser()
    digest = hashlib.sha256(
        b"antiek.owner-graph.path.v1\0" + owner.encode("utf-8")
    ).hexdigest()
    path = base / digest[:2] / f"{digest}.duckdb"
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def existing_owner_graph_db_path(
    owner_id: str, *, root: Path | str | None = None
) -> str | None:
    """Resolve an existing owner graph without mutating the filesystem.

    Personal reads must never initialize storage or fall back to the operator
    graph.  The explicit ``None`` result is the honest unmaterialized state.
    """
    path = owner_graph_db_path(owner_id, root=root, create_parent=False)
    return path if Path(path).is_file() else None


def owner_graph_readiness(
    owner_id: str, *, root: Path | str | None = None
) -> dict[str, str | bool | None]:
    """Return non-sensitive routing truth for one authenticated owner."""
    path = owner_graph_db_path(owner_id, root=root, create_parent=False)
    materialized = Path(path).is_file()
    return {
        "owner_graph_scope": (
            "operator_canonical"
            if owner_id == "__operator__"
            else "physically_isolated"
            if materialized
            else "unmaterialized"
        ),
        "materialized": materialized,
        "graph_path_sha256": owner_graph_path_sha256(path),
    }


def owner_graph_path_sha256(db_path: str) -> str:
    """Non-reversible path identity for durable promotion receipts."""
    return hashlib.sha256(
        b"antiek.owner-graph.path-revision.v1\0" + str(db_path).encode("utf-8")
    ).hexdigest()


def owner_graph_events_dir(owner_id: str, db_path: str) -> str | None:
    """Keep authenticated graph events beside their private graph partition."""
    if owner_id == "__operator__":
        return None
    path = Path(db_path).with_suffix(".events")
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
