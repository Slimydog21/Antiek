"""Embedding metadata pinning for chunk vectors.

The ``chunks.embedding`` column only stores floats. This module records which
provider/model/dimension produced those floats and rejects vector search when
the query model is incompatible with stored metadata.
"""

from __future__ import annotations

from typing import Any

from processing.embedding import (
    embedding_model_name,
    embedding_provider_fingerprint,
    embedding_provider_name,
)
from runtime.db_lock import LockedConnection


def _identity(provider: Any) -> tuple[str, str, int, str]:
    return (
        embedding_provider_name(provider),
        embedding_model_name(provider),
        int(provider.dimension),
        embedding_provider_fingerprint(provider),
    )


def record_chunk_embedding_meta(
    con: LockedConnection,
    *,
    chunk_id: str,
    provider: Any,
) -> None:
    """Record the provider identity that produced a chunk embedding."""
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"record_chunk_embedding_meta requires a LockedConnection "
            f"(got {type(con).__name__})."
        )
    provider_name, model_name, dimension, fingerprint = _identity(provider)
    con.execute("DELETE FROM embeddings_meta WHERE chunk_id = ?", [chunk_id])
    con.execute(
        "INSERT INTO embeddings_meta "
        "(chunk_id, provider, model_name, dimension, fingerprint) "
        "VALUES (?, ?, ?, ?, ?)",
        [chunk_id, provider_name, model_name, dimension, fingerprint],
    )


def assert_embedding_compatible(con: Any, provider: Any) -> None:
    """Fail search if persisted chunk embeddings use a different provider.

    Legacy databases remain readable: if the metadata table is absent or empty,
    this check is a no-op. Once metadata exists, any mismatched fingerprint is
    treated as unsafe because vector-space equality cannot be inferred from
    equal dimensions alone.
    """
    provider_name, model_name, dimension, fingerprint = _identity(provider)
    try:
        row = con.execute(
            "SELECT provider, model_name, dimension, fingerprint "
            "FROM embeddings_meta "
            "WHERE fingerprint != ? OR dimension != ? "
            "LIMIT 1",
            [fingerprint, dimension],
        ).fetchone()
    except Exception as exc:
        if exc.__class__.__name__ in {"CatalogException", "BinderException"}:
            return
        raise
    if row is None:
        return

    stored_provider, stored_model, stored_dim, stored_fingerprint = row
    raise ValueError(
        "Stored chunk embeddings are pinned to "
        f"{stored_provider}/{stored_model} dim={stored_dim} "
        f"({stored_fingerprint}), but search is using "
        f"{provider_name}/{model_name} dim={dimension} ({fingerprint}). "
        "Re-run tools/reembed_chunks.py with the current provider or search "
        "with the provider that created the stored vectors."
    )
