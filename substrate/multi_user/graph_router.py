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

    def personal_graph_path(self, user_id: str) -> str:
        """Per-user DuckDB file path. The user_id is sanitized (only
        alphanumeric + dash + underscore) to prevent path traversal.

        Note: the canonical operator user '__operator__' resolves to
        a file inside personal_graphs_dir like any other user; the
        existing operator-only graph at ANTIEK_DUCKDB_PATH is the
        Stage-0 single-graph baseline that Stage-1 migration moves
        from."""
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in user_id)
        if not safe:
            raise ValueError(f"invalid user_id: {user_id!r}")
        return os.path.join(self.personal_graphs_dir, f"{safe}.duckdb")


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
    return PersonalGraphHandle(
        user_id=user_id,
        db_path=router.personal_graph_path(user_id),
        encryption_key_ref=encryption_key_ref,
    )


def resolve_shared_substrate(router: GraphRouter) -> SharedSubstrateHandle:
    """Build a SharedSubstrateHandle. Only one writer at a time across
    the substrate; flock-coordinated."""
    return SharedSubstrateHandle(db_path=router.shared_substrate_path)
