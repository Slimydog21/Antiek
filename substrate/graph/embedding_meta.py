"""Embedding metadata pinning for chunk vectors.

The ``chunks.embedding`` column only stores floats. This module records which
provider/model/dimension produced those floats and rejects vector search when
the query model is incompatible with stored metadata.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import duckdb

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


def assert_embedding_compatible(
    con: Any,
    provider: Any,
    *,
    candidate_sql: str | None = None,
    candidate_params: Sequence[Any] = (),
) -> None:
    """Fail search if persisted chunk embeddings use a different provider.

    Search passes its pre-ranking candidate selection. Direct callers retain
    the historical global check. An absent metadata table remains readable;
    other SQL errors must surface.
    """
    provider_name, model_name, dimension, fingerprint = _identity(provider)
    sql = "SELECT m.provider, m.model_name, m.dimension, m.fingerprint FROM embeddings_meta m"
    params = list(candidate_params)
    if candidate_sql is not None:
        sql += f" JOIN ({candidate_sql}) eligible ON eligible.chunk_id = m.chunk_id"
    sql += " WHERE (m.fingerprint IS DISTINCT FROM ? OR m.dimension IS DISTINCT FROM ?) LIMIT 1"
    params.extend([fingerprint, dimension])
    try:
        row = con.execute(sql, params).fetchone()
    except duckdb.CatalogException:
        # A legacy DB may lack this table. Probe only on an error so an
        # unrelated missing candidate relation cannot masquerade as legacy.
        try:
            con.execute("SELECT 1 FROM embeddings_meta LIMIT 0")
        except duckdb.CatalogException:
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
