"""Sharding strategies for the catalog.

Stage 1: NoSharding — every user has a flat-directory file.
Stage 2: HashPrefixSharding — shard by first hex chars of sha256(user_id).
         16 shards by default (one hex char); 256 shards by config (two
         hex chars) when per-shard file count approaches OS handle limit.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Optional, Protocol

from .catalog import CatalogEntry, DuckLakeCatalog


class ShardingStrategy(Protocol):
    """Resolves user_id → (shard_id, db_path) for a configured root."""

    def shard_id_for(self, user_id: str) -> Optional[str]: ...
    def db_path_for(self, user_id: str, *, root_dir: str) -> str: ...


@dataclass(frozen=True)
class NoSharding:
    """Stage 1 default — flat layout under root_dir."""

    def shard_id_for(self, user_id: str) -> Optional[str]:
        return None

    def db_path_for(self, user_id: str, *, root_dir: str) -> str:
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in user_id)
        if not safe:
            raise ValueError(f"invalid user_id: {user_id!r}")
        return os.path.join(root_dir, f"{safe}.duckdb")


@dataclass(frozen=True)
class HashPrefixSharding:
    """Stage 2 — sharded by sha256(user_id)[:hex_chars]."""

    hex_chars: int = 1  # 1 → 16 shards; 2 → 256 shards.

    def shard_id_for(self, user_id: str) -> str:
        h = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
        return h[: self.hex_chars]

    def db_path_for(self, user_id: str, *, root_dir: str) -> str:
        shard = self.shard_id_for(user_id)
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in user_id)
        if not safe:
            raise ValueError(f"invalid user_id: {user_id!r}")
        return os.path.join(root_dir, shard, f"{safe}.duckdb")


def resolve_db_path(
    user_id: str,
    *,
    catalog: Optional[DuckLakeCatalog] = None,
    strategy: ShardingStrategy,
    root_dir: str,
) -> str:
    """Catalog-first resolution.

    If catalog has an entry for user_id, return its db_path (this lets
    migrations move files without breaking already-registered users).
    Otherwise compute the canonical path from the strategy.
    """
    if catalog is not None:
        entry = catalog.lookup(user_id)
        if entry is not None:
            return entry.db_path
    return strategy.db_path_for(user_id, root_dir=root_dir)
