"""Runtime routing for physically isolated personal graph files."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def owner_graph_db_path(owner_id: str, *, root: Path | str | None = None) -> str:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


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
