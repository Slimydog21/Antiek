from __future__ import annotations

import os

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database_at_path
from substrate.stale_refresh import validate_promotion_candidate


def _graph(tmp_path):
    db_path = os.path.join(tmp_path, "graph.duckdb")
    init_database_at_path(db_path)
    return connect_write(db_path, purpose="test/stale-refresh-promotion")


def test_promotion_candidate_ready_when_all_supporting_chunks_resolve(tmp_path):
    con = _graph(tmp_path)
    try:
        insert_document(
            con,
            document_id="doc-refresh",
            source_tier=2,
            document_type="paper",
            title="Refresh Evidence",
        )
        insert_chunk(
            con,
            document_id="doc-refresh",
            chunk_id="chunk-refresh-1",
            chunk_index=0,
            text="Refresh evidence one.",
        )
        insert_chunk(
            con,
            document_id="doc-refresh",
            chunk_id="chunk-refresh-2",
            chunk_index=1,
            text="Refresh evidence two.",
        )

        result = validate_promotion_candidate(
            con,
            supporting_chunk_ids=[
                "chunk-refresh-1",
                "chunk-refresh-2",
                "chunk-refresh-1",
            ],
        )
    finally:
        con.close()

    assert result.depositable is True
    assert result.reason == "ready"
    assert result.primary_chunk_id == "chunk-refresh-1"
    assert result.primary_source_document_id == "doc-refresh"
    assert [c.chunk_id for c in result.resolved_chunks] == [
        "chunk-refresh-1",
        "chunk-refresh-2",
    ]
    assert result.unresolved_chunk_ids == ()


def test_promotion_candidate_rejects_missing_supporting_chunks(tmp_path):
    con = _graph(tmp_path)
    try:
        result = validate_promotion_candidate(con, supporting_chunk_ids=[])
    finally:
        con.close()

    assert result.depositable is False
    assert result.reason == "missing_supporting_chunks"
    assert result.primary_chunk_id is None
    assert result.resolved_chunks == ()


def test_promotion_candidate_rejects_unresolved_chunks_without_hiding_resolved(
    tmp_path,
):
    con = _graph(tmp_path)
    try:
        insert_document(
            con,
            document_id="doc-refresh",
            source_tier=2,
            document_type="paper",
        )
        insert_chunk(
            con,
            document_id="doc-refresh",
            chunk_id="chunk-refresh-1",
            chunk_index=0,
            text="Refresh evidence.",
        )

        result = validate_promotion_candidate(
            con,
            supporting_chunk_ids=["chunk-refresh-1", "missing-chunk"],
        )
    finally:
        con.close()

    assert result.depositable is False
    assert result.reason == "unresolved_supporting_chunks"
    assert [c.chunk_id for c in result.resolved_chunks] == ["chunk-refresh-1"]
    assert result.unresolved_chunk_ids == ("missing-chunk",)
    assert result.primary_chunk_id is None
