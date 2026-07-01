"""Per-user graph routing (master-spec §13.2 + §13.6).

Per master-spec §13.6 substrate transition matrix:
- Stage 0: single DuckDB file (operator-only)
- Stage 1: DuckDB per user + shared substrate DuckLake
- Stage 2: DuckLake catalog routes per-user files
- Stage 3: Postgres-sharded

This router resolves a UserClaims to a per-user DuckDB file path
(Stages 1-2) or to the appropriate Postgres shard (Stage 3). The
SAME interface across stages; only the implementation behind it
changes.

The single-writer invariant becomes single-writer-per-personal-graph
plus single-writer-on-substrate. Both invariants enforced via
runtime.db_lock LockedConnection — the personal-graph file uses one
lock identifier, the shared substrate another.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from substrate.ducklake.catalog import DuckLakeCatalog, SqliteCatalogBackend
from substrate.ducklake.routing import (
    HashPrefixSharding,
    NoSharding,
    ShardingStrategy,
    resolve_db_path,
)


CATALOG_DB_ENV = "ANTIEK_DUCKLAKE_CATALOG_DB"
GRAPH_USER_ID_ENV = "ANTIEK_GRAPH_USER_ID"
SHARD_HEX_CHARS_ENV = "ANTIEK_DUCKLAKE_SHARD_HEX_CHARS"
DEFAULT_GRAPH_USER_ID = "__operator__"


@dataclass(frozen=True)
class PersonalGraphHandle:
    """Handle to a user's personal-graph DuckDB. The user_id is the
    flock identifier; multiple flock acquirers on the same user_id
    queue (single-writer-per-personal-graph)."""

    user_id: str
    db_path: str
    encryption_key_ref: str | None = None


@dataclass(frozen=True)
class SharedSubstrateHandle:
    """Handle to the shared substrate DuckDB. ONE writer at a time
    via a global flock; skill-patch propagation queues against it."""

    db_path: str


@dataclass
class GraphRouter:
    """Routes per-user graph accesses to the right file path.

    Sprint 22+ default: ~/.antiek/personal_graphs/{user_id}.duckdb
    + ~/.antiek/shared_substrate.duckdb. Operator override via env:
    - ANTIEK_PERSONAL_GRAPHS_DIR
    - ANTIEK_SHARED_SUBSTRATE_DB
    """

    personal_graphs_dir: str = field(
        default_factory=lambda: os.environ.get(
            "ANTIEK_PERSONAL_GRAPHS_DIR",
            os.path.expanduser("~/.antiek/personal_graphs"),
        )
    )
    shared_substrate_path: str = field(
        default_factory=lambda: os.environ.get(
            "ANTIEK_SHARED_SUBSTRATE_DB",
            os.path.expanduser("~/.antiek/shared_substrate.duckdb"),
        )
    )
    catalog: DuckLakeCatalog | None = None
    sharding_strategy: ShardingStrategy = field(default_factory=NoSharding)

    def personal_graph_path(self, user_id: str) -> str:
        """Per-user DuckDB file path. The user_id is sanitized (only
        alphanumeric + dash + underscore) to prevent path traversal.

        Note: the canonical operator user '__operator__' resolves to
        a file inside personal_graphs_dir like any other user; the
        existing operator-only graph at ANTIEK_DUCKDB_PATH is the
        Stage-0 single-graph baseline that Stage-1 migration moves
        from."""
        return resolve_db_path(
            user_id,
            catalog=self.catalog,
            strategy=self.sharding_strategy,
            root_dir=self.personal_graphs_dir,
        )


def resolve_personal_graph(
    router: GraphRouter,
    *,
    user_id: str,
    encryption_key_ref: str | None = None,
) -> PersonalGraphHandle:
    """Build a PersonalGraphHandle for the given user. The caller
    holds the handle for the duration of their critical section;
    db_lock.connect_write acquires the flock per master-spec §13.10
    substrate hygiene."""
    if encryption_key_ref is None and router.catalog is not None:
        entry = router.catalog.lookup(user_id)
        if entry is not None:
            encryption_key_ref = entry.encryption_key_ref
    return PersonalGraphHandle(
        user_id=user_id,
        db_path=router.personal_graph_path(user_id),
        encryption_key_ref=encryption_key_ref,
    )


def resolve_shared_substrate(router: GraphRouter) -> SharedSubstrateHandle:
    """Build a SharedSubstrateHandle. Only one writer at a time across
    the substrate; flock-coordinated."""
    return SharedSubstrateHandle(db_path=router.shared_substrate_path)


def configured_ducklake_catalog() -> DuckLakeCatalog | None:
    """Return the configured DuckLake catalog, if Stage-2 routing is enabled.

    ``ANTIEK_DUCKLAKE_CATALOG_DB`` points at the SQLite catalog created by the
    Stage 0 -> Stage 1 migration. Later Postgres promotion keeps this function as
    the single construction point for the router's catalog dependency.
    """
    catalog_db = os.environ.get(CATALOG_DB_ENV)
    if not catalog_db:
        return None
    return _sqlite_ducklake_catalog(os.path.expanduser(catalog_db))


@lru_cache(maxsize=8)
def _sqlite_ducklake_catalog(catalog_db: str) -> DuckLakeCatalog:
    return DuckLakeCatalog(backend=SqliteCatalogBackend(db_path=catalog_db))


def configured_sharding_strategy() -> ShardingStrategy:
    """Return the routing fallback strategy requested by env."""
    raw_hex_chars = os.environ.get(SHARD_HEX_CHARS_ENV)
    if not raw_hex_chars:
        return NoSharding()
    try:
        hex_chars = int(raw_hex_chars)
    except ValueError as exc:
        raise ValueError(
            f"{SHARD_HEX_CHARS_ENV} must be a positive integer"
        ) from exc
    if hex_chars <= 0:
        raise ValueError(f"{SHARD_HEX_CHARS_ENV} must be a positive integer")
    return HashPrefixSharding(hex_chars=hex_chars)


def build_graph_router_from_env() -> GraphRouter:
    """Build the production graph router from process configuration."""
    return GraphRouter(
        catalog=configured_ducklake_catalog(),
        sharding_strategy=configured_sharding_strategy(),
    )


def default_graph_user_id() -> str:
    """Resolve the graph user for legacy single-user API call paths."""
    return os.environ.get(GRAPH_USER_ID_ENV) or DEFAULT_GRAPH_USER_ID


def default_personal_graph_handle() -> PersonalGraphHandle:
    """Resolve the default personal graph through the configured router."""
    return resolve_personal_graph(
        build_graph_router_from_env(),
        user_id=default_graph_user_id(),
    )
