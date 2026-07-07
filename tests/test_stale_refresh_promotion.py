from __future__ import annotations

import hashlib
import os

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_write
from substrate.event_log import trajectory
from substrate.graph.insight_question import knowledge_unit_of
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database_at_path
from substrate.schemas import StaleReuseRefreshPromotionCandidatePayload
from substrate.stale_refresh import (
    promote_refresh_candidate,
    validate_promotion_candidate,
)


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in digest[: self.dimension]]


@pytest.fixture(autouse=True)
def _hash_embeddings():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


def _graph(tmp_path):
    db_path = os.path.join(tmp_path, "graph.duckdb")
    init_database_at_path(db_path)
    return connect_write(db_path, purpose="test/stale-refresh-promotion")


def _seed_refresh_chunk(con):
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


def test_promotion_candidate_ready_when_all_supporting_chunks_resolve(tmp_path):
    con = _graph(tmp_path)
    try:
        _seed_refresh_chunk(con)
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
        _seed_refresh_chunk(con)

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


def test_promote_refresh_candidate_deposits_grounded_insight_and_result_event(
    tmp_path,
    monkeypatch,
):
    events_dir = os.path.join(tmp_path, "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    con = _graph(tmp_path)
    try:
        _seed_refresh_chunk(con)
        attempt = promote_refresh_candidate(
            con,
            investigation_id="inv-parent",
            candidate=StaleReuseRefreshPromotionCandidatePayload(
                unit_id="unit-stale",
                source_investigation_id="inv-source",
                refresh_investigation_id="inv-refresh",
                summary="Source claim remains current after refresh.",
                supporting_chunk_ids=["chunk-refresh-1"],
            ),
            candidate_event_id="evt-candidate",
            events_dir=events_dir,
        )
        node_row = con.execute(
            "SELECT canonical_label FROM nodes WHERE node_id = ?",
            [attempt.deposited_node_id],
        ).fetchone()
        unit = knowledge_unit_of(
            con,
            attempt.deposited_node_id,
            content_class="public_domain",
        )
    finally:
        con.close()

    assert attempt.validation.depositable is True
    assert attempt.deposited_node_id is not None
    assert node_row == ("Source claim remains current after refresh.",)
    assert unit.provenance.source_document_id == "doc-refresh"
    assert unit.provenance.chunk_id == "chunk-refresh-1"
    assert unit.investigation_id == "inv-parent"
    result_events = [
        e for e in trajectory("inv-parent", events_dir=events_dir)
        if e["action_type"] == "stale_reuse.refresh.promotion_result"
    ]
    assert len(result_events) == 1
    payload = result_events[0]["payload"]
    assert payload["status"] == "deposited"
    assert payload["reason"] == "ready"
    assert payload["deposited_node_id"] == attempt.deposited_node_id
    assert payload["primary_chunk_id"] == "chunk-refresh-1"
    assert payload["candidate_event_id"] == "evt-candidate"


def test_promote_refresh_candidate_records_non_depositability_without_node(
    tmp_path,
    monkeypatch,
):
    events_dir = os.path.join(tmp_path, "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    con = _graph(tmp_path)
    try:
        attempt = promote_refresh_candidate(
            con,
            investigation_id="inv-parent",
            candidate=StaleReuseRefreshPromotionCandidatePayload(
                unit_id="unit-stale",
                source_investigation_id="inv-source",
                refresh_investigation_id="inv-refresh",
                summary="Source claim remains current after refresh.",
                supporting_chunk_ids=["missing-chunk"],
            ),
            candidate_event_id="evt-candidate",
            events_dir=events_dir,
        )
        node_count = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    finally:
        con.close()

    assert attempt.validation.depositable is False
    assert attempt.deposited_node_id is None
    assert node_count == 0
    result_events = [
        e for e in trajectory("inv-parent", events_dir=events_dir)
        if e["action_type"] == "stale_reuse.refresh.promotion_result"
    ]
    assert len(result_events) == 1
    payload = result_events[0]["payload"]
    assert payload["status"] == "not_depositable"
    assert payload["reason"] == "unresolved_supporting_chunks"
    assert payload["unresolved_chunk_ids"] == ["missing-chunk"]
    assert payload["deposited_node_id"] is None
