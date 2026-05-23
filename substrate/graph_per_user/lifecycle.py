"""Per-user graph lifecycle — create / open / close / delete.

Per master-spec §13.2: each user has ONE personal graph (their
memory) with public-facing and private-facing partitions. The
lifecycle:

    create_user_graph(user_id) → PerUserStorage
        - allocates a per-user DuckDB file path via the catalog
        - generates a per-graph data-encryption key via KeyProvider
        - records the (user_id, db_path, key_id) tuple in the catalog
        - emits PerUserStorageEvent(kind='created')

    open_user_graph(user_id) → PerUserStorage
        - looks up the catalog entry
        - returns a handle (does not create the file if missing)

    close_user_graph(user_id) → None
        - no-op for the file (DuckDB connection lifecycle is the
          caller's responsibility via runtime.db_lock)
        - emits 'closed' event

    delete_user_graph(user_id) → None
        - revokes the encryption key in KeyProvider
        - deregisters the catalog entry
        - the actual file deletion is the deletion_worker's job
          (Sprint 22 Phase 6) because deletion has a 30-day SLA
        - emits 'delete_scheduled' event

This is the spec's `per_user_storage.py` deliverable.
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from substrate.ducklake.catalog import DuckLakeCatalog
from substrate.ducklake.routing import ShardingStrategy

from .key_provider import KeyMaterial, KeyProvider, KeyProviderError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PerUserStorageEventKind(str, enum.Enum):
    CREATED = "created"
    OPENED = "opened"
    CLOSED = "closed"
    DELETE_SCHEDULED = "delete_scheduled"
    KEY_ROTATED = "key_rotated"


@dataclass(frozen=True)
class PerUserStorageEvent:
    """An event emitted by the lifecycle. Caller can subscribe via
    the substrate event_log; this module just produces them."""

    kind: PerUserStorageEventKind
    user_id: str
    db_path: str
    key_id: Optional[str]
    at: str = field(default_factory=_now_iso)


@dataclass(frozen=True)
class PerUserStorage:
    """A handle to one user's personal graph."""

    user_id: str
    db_path: str
    key_material: KeyMaterial
    created_at: str


def _safe_user_id(user_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in user_id)
    if not safe:
        raise ValueError(f"invalid user_id: {user_id!r}")
    return safe


def create_user_graph(
    *,
    user_id: str,
    catalog: DuckLakeCatalog,
    key_provider: KeyProvider,
    strategy: ShardingStrategy,
    root_dir: str,
) -> tuple[PerUserStorage, PerUserStorageEvent]:
    """Allocate a per-user DuckDB + generate its encryption key.

    Idempotent on user_id: if the catalog already has an entry, raises
    KeyProviderError to force the caller to use open_user_graph for
    re-open (or delete_user_graph + retry for re-create).
    """
    safe = _safe_user_id(user_id)
    existing = catalog.lookup(safe)
    if existing is not None:
        raise KeyProviderError(
            f"user_id {user_id!r} already has a catalog entry at "
            f"{existing.db_path!r}; use open_user_graph or delete_user_graph",
        )

    db_path = strategy.db_path_for(safe, root_dir=root_dir)
    key_material = key_provider.generate_data_key(graph_id=safe)
    catalog.register(
        user_id=safe,
        db_path=db_path,
        encryption_key_ref=key_material.key_id,
    )
    # Ensure the parent dir exists; the DuckDB file itself is created
    # by the first connect_write (substrate uses lazy creation).
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    storage = PerUserStorage(
        user_id=safe,
        db_path=db_path,
        key_material=key_material,
        created_at=_now_iso(),
    )
    event = PerUserStorageEvent(
        kind=PerUserStorageEventKind.CREATED,
        user_id=safe,
        db_path=db_path,
        key_id=key_material.key_id,
    )
    return storage, event


def open_user_graph(
    *,
    user_id: str,
    catalog: DuckLakeCatalog,
    key_provider: KeyProvider,
) -> Optional[tuple[PerUserStorage, PerUserStorageEvent]]:
    """Return an open handle, or None if user has no graph yet.

    Looking up does NOT modify the catalog or key store. Caller
    holds the handle for the duration of their critical section;
    `runtime.db_lock.connect_write` acquires the file flock when
    they connect.
    """
    safe = _safe_user_id(user_id)
    entry = catalog.lookup(safe)
    if entry is None:
        return None
    key_material = key_provider.lookup(graph_id=safe)
    if key_material is None:
        # Catalog says the graph exists but the key provider does
        # not have a wrapped key. This happens in the KMSStub case
        # where wrapped keys live in the catalog row. Synthesize a
        # KeyMaterial from the catalog's encryption_key_ref so the
        # caller can still reach DuckDB.
        key_material = KeyMaterial(
            graph_id=safe,
            key_id=entry.encryption_key_ref or f"alias/antiek-graph-{safe}",
            wrapped_data_key=b"",
        )
    storage = PerUserStorage(
        user_id=safe,
        db_path=entry.db_path,
        key_material=key_material,
        created_at=entry.updated_at,
    )
    event = PerUserStorageEvent(
        kind=PerUserStorageEventKind.OPENED,
        user_id=safe,
        db_path=entry.db_path,
        key_id=key_material.key_id,
    )
    return storage, event


def close_user_graph(
    *,
    user_id: str,
    catalog: DuckLakeCatalog,
) -> PerUserStorageEvent:
    """Emit a 'closed' event. File deletion is delete_user_graph's
    job; closing is currently just a no-op observability event."""
    safe = _safe_user_id(user_id)
    entry = catalog.lookup(safe)
    return PerUserStorageEvent(
        kind=PerUserStorageEventKind.CLOSED,
        user_id=safe,
        db_path=entry.db_path if entry else "",
        key_id=entry.encryption_key_ref if entry else None,
    )


def delete_user_graph(
    *,
    user_id: str,
    catalog: DuckLakeCatalog,
    key_provider: KeyProvider,
) -> PerUserStorageEvent:
    """Schedule deletion: revoke the key + deregister the catalog
    entry. The actual file removal is the deletion_worker's job
    (it has a 30-day SLA per §13.3).

    Returns the 'delete_scheduled' event so the caller can enqueue
    the cascade-delete work."""
    safe = _safe_user_id(user_id)
    entry = catalog.lookup(safe)
    if entry is None:
        return PerUserStorageEvent(
            kind=PerUserStorageEventKind.DELETE_SCHEDULED,
            user_id=safe,
            db_path="",
            key_id=None,
        )
    try:
        key_provider.revoke(graph_id=safe)
    except KeyProviderError:
        # Revocation failure shouldn't block the catalog deregister;
        # the deletion worker re-tries. We just record the path.
        pass
    catalog.deregister(safe)
    return PerUserStorageEvent(
        kind=PerUserStorageEventKind.DELETE_SCHEDULED,
        user_id=safe,
        db_path=entry.db_path,
        key_id=entry.encryption_key_ref,
    )
