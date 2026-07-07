"""Tests for tools/reembed_chunks metadata stamping."""

from __future__ import annotations

import os
import sys

import duckdb

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from processing.embedding import HashEmbedding, embedding_provider_fingerprint  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph import init_database_at_path, insert_chunk, insert_document  # noqa: E402
from tools import reembed_chunks  # noqa: E402


def test_reembed_chunks_records_embedding_metadata(tmp_path, monkeypatch):
    db_path = str(tmp_path / "reembed.duckdb")
    init_database_at_path(db_path)
    provider = HashEmbedding(dimension=8)

    with connect_write(db_path, purpose="seed") as con:
        insert_document(
            con,
            document_id="doc-1",
            source_tier=1,
            document_type="white_paper",
        )
        chunk_id = insert_chunk(
            con,
            document_id="doc-1",
            chunk_index=0,
            text="semantic vector metadata",
        )

    monkeypatch.setattr(reembed_chunks, "default_embedding_provider", lambda: provider)
    report = reembed_chunks.run(
        db_path,
        apply=True,
        force_hash=True,
    )

    assert report.applied is True
    assert report.vectors_rewritten == 1
    con = duckdb.connect(db_path, read_only=True)
    try:
        row = con.execute(
            "SELECT chunk_id, provider, model_name, dimension, fingerprint "
            "FROM embeddings_meta WHERE chunk_id = ?",
            [chunk_id],
        ).fetchone()
    finally:
        con.close()

    assert row == (
        chunk_id,
        "hash",
        "hash-dim-8",
        8,
        embedding_provider_fingerprint(provider),
    )
