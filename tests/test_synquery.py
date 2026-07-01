"""Synquery API client + adapter tests (Sprint 21)."""

from __future__ import annotations

import json
import os
import tempfile

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from tools.synquery import (
    MockSynqueryClient,
    SynqueryAdapter,
    SynqueryAPIError,
    SynqueryExpert,
    SynqueryRequest,
    SynqueryTranscriptIngest,
)
from tools.synquery.client import feature_flag_enabled


@pytest.fixture
def temp_graph(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-synquery-test-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    init_database_at_path(db_path)
    yield db_path


# ── Client tests ────────────────────────────────────────────────────


def test_mock_client_returns_canned_experts():
    exp = SynqueryExpert(
        expert_id="e-1", display_name="Dr. X",
        credentials="PhD", rate_usd_per_hour=500.0,
        availability_summary="weekly",
    )
    client = MockSynqueryClient(canned_experts=[exp])
    results = client.search_experts(topic_query="quantum")
    assert len(results) == 1
    assert results[0].expert_id == "e-1"


def test_mock_client_generates_placeholder_experts():
    """With no canned list, the mock generates deterministic
    placeholder experts based on the topic_query."""
    client = MockSynqueryClient()
    results = client.search_experts(topic_query="neutral atom error correction")
    assert len(results) > 0
    assert "neutral atom" in results[0].display_name


def test_book_interview_returns_pending_handle():
    client = MockSynqueryClient()
    interview = client.book_interview(
        expert_id="e-1",
        duration_minutes=60,
        scheduling_window_iso="2026-06-15T15:00:00Z",
    )
    assert interview.booking_status == "pending"
    assert interview.duration_minutes == 60
    assert interview.expert_id == "e-1"


# ── Adapter tests ───────────────────────────────────────────────────


def test_feature_flag_default_off(monkeypatch):
    monkeypatch.delenv("ANTIEK_SYNQUERY_ENABLED", raising=False)
    assert feature_flag_enabled() is False


def test_feature_flag_enabled_when_one(monkeypatch):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "1")
    assert feature_flag_enabled() is True


def test_adapter_refuses_when_disabled(monkeypatch):
    monkeypatch.delenv("ANTIEK_SYNQUERY_ENABLED", raising=False)
    adapter = SynqueryAdapter(client=MockSynqueryClient())
    request = SynqueryRequest(
        question_id="q-1", question_text="quantum error correction?",
        investigation_id=None, operator_budget_usd=5000.0,
    )
    with pytest.raises(SynqueryAPIError):
        adapter.request_experts(request)


def test_adapter_filters_by_budget(monkeypatch):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "1")
    canned = [
        SynqueryExpert(
            expert_id="cheap", display_name="A", credentials="X",
            rate_usd_per_hour=300.0, availability_summary="x",
        ),
        SynqueryExpert(
            expert_id="expensive", display_name="B", credentials="X",
            rate_usd_per_hour=3000.0, availability_summary="x",
        ),
    ]
    adapter = SynqueryAdapter(client=MockSynqueryClient(canned_experts=canned))
    request = SynqueryRequest(
        question_id="q-1", question_text="x",
        investigation_id=None, operator_budget_usd=1000.0,
    )
    response = adapter.request_experts(request)
    expert_ids = [e.expert_id for e in response.matched_experts]
    assert "cheap" in expert_ids
    assert "expensive" not in expert_ids


def test_adapter_refuses_budget_above_hard_cap(monkeypatch):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "1")
    adapter = SynqueryAdapter(client=MockSynqueryClient())
    request = SynqueryRequest(
        question_id="q-cap",
        question_text="x",
        investigation_id=None,
        operator_budget_usd=5000.01,
    )

    with pytest.raises(SynqueryAPIError, match="hard cap"):
        adapter.request_experts(request)


def test_adapter_book_returns_pending_handle(monkeypatch):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "1")
    adapter = SynqueryAdapter(client=MockSynqueryClient())
    request = SynqueryRequest(
        question_id="q-1", question_text="x",
        investigation_id="inv-x", operator_budget_usd=5000.0,
    )
    response = adapter.book_expert_interview(
        request=request, expert_id="e-1",
        scheduling_window_iso="2026-06-15T14:00:00Z",
        duration_minutes=60,
    )
    assert response.booking_handle is not None
    assert response.booking_handle.booking_status == "pending"


def test_adapter_booking_blocks_estimated_cost_above_effective_cap(monkeypatch):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "1")
    adapter = SynqueryAdapter(client=MockSynqueryClient())
    request = SynqueryRequest(
        question_id="q-1",
        question_text="x",
        investigation_id="inv-x",
        operator_budget_usd=1000.0,
    )

    with pytest.raises(SynqueryAPIError, match="exceeds spend cap"):
        adapter.book_expert_interview(
            request=request,
            expert_id="e-pricey",
            scheduling_window_iso="2026-06-15T14:00:00Z",
            duration_minutes=90,
            expert_rate_usd_per_hour=800.0,
        )


def test_adapter_booking_allows_cost_under_operator_cap(monkeypatch):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "1")
    adapter = SynqueryAdapter(client=MockSynqueryClient())
    request = SynqueryRequest(
        question_id="q-1",
        question_text="x",
        investigation_id="inv-x",
        operator_budget_usd=1000.0,
    )

    response = adapter.book_expert_interview(
        request=request,
        expert_id="e-ok",
        scheduling_window_iso="2026-06-15T14:00:00Z",
        duration_minutes=60,
        expert_rate_usd_per_hour=800.0,
    )

    assert response.booking_handle is not None
    assert response.booking_handle.expert_id == "e-ok"


def test_adapter_ingests_completed_transcript_as_tier_2_source(monkeypatch, temp_graph):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "1")
    adapter = SynqueryAdapter(client=MockSynqueryClient())
    transcript = SynqueryTranscriptIngest(
        interview_id="interview-synquery-fixed",
        expert_id="expert-42",
        expert_display_name="Dr. Ada Fourier",
        question_id="q-synquery",
        investigation_id="inv-synquery",
        completed_at_iso="2026-06-15T15:30:00Z",
        transcript_text=(
            "The important practical distinction is that the substrate should "
            "treat the interview as informed testimony, not as a verified "
            "primary artifact. The expert can explain mechanisms and failure "
            "modes, while Antiek still needs corroborating sources before "
            "promotion into durable claims."
        ),
    )

    with connect_write(temp_graph, purpose="test_synquery_transcript") as con:
        result = adapter.ingest_completed_transcript(con, transcript)

    assert result.source_tier == 2
    assert result.document_type == "expert_interview_transcript"
    assert result.interview.booking_status == "completed"
    assert result.interview.transcript_document_id == result.document_id
    assert result.chunk_ids

    con = duckdb.connect(temp_graph, read_only=True)
    try:
        row = con.execute(
            "SELECT source_tier, document_type, source_uri, raw_text, metadata, "
            "content_class, ip_holder_id FROM documents WHERE document_id = ?",
            [result.document_id],
        ).fetchone()
        assert row is not None
        source_tier, document_type, source_uri, raw_text, metadata, content_class, ip_holder_id = row
        meta = json.loads(metadata)
    finally:
        con.close()

    assert source_tier == 2
    assert document_type == "expert_interview_transcript"
    assert source_uri == "synquery://interviews/interview-synquery-fixed/transcript"
    assert "informed testimony" in raw_text
    assert content_class == "user_owned"
    assert ip_holder_id == "__operator__"
    assert meta["synquery"]["interview_id"] == "interview-synquery-fixed"
    assert meta["synquery"]["question_id"] == "q-synquery"
    assert meta["synquery"]["document_kind"] == "interview"
    assert meta["synquery"]["source_tier"] == 2


def test_adapter_completed_transcript_ingest_is_idempotent(monkeypatch, temp_graph):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "1")
    adapter = SynqueryAdapter(client=MockSynqueryClient())
    transcript = SynqueryTranscriptIngest(
        interview_id="interview-synquery-repeat",
        expert_id="expert-repeat",
        question_id="q-repeat",
        investigation_id="inv-repeat",
        transcript_text=(
            "This transcript has enough words to pass the ingestion guard and "
            "prove repeated webhook delivery stays idempotent rather than "
            "creating duplicate document or chunk rows in the graph."
        ),
    )

    with connect_write(temp_graph, purpose="test_synquery_repeat") as con:
        first = adapter.ingest_completed_transcript(con, transcript)
        second = adapter.ingest_completed_transcript(con, transcript)

    assert first.document_id == second.document_id
    assert first.chunk_ids
    assert second.chunk_ids == ()

    con = duckdb.connect(temp_graph, read_only=True)
    try:
        doc_count = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [first.document_id],
        ).fetchone()[0]
        chunk_count = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [first.document_id],
        ).fetchone()[0]
    finally:
        con.close()

    assert doc_count == 1
    assert chunk_count == len(first.chunk_ids)


def test_adapter_transcript_ingest_refuses_when_disabled(monkeypatch, temp_graph):
    monkeypatch.delenv("ANTIEK_SYNQUERY_ENABLED", raising=False)
    adapter = SynqueryAdapter(client=MockSynqueryClient())
    transcript = SynqueryTranscriptIngest(
        interview_id="interview-disabled",
        expert_id="expert-disabled",
        question_id="q-disabled",
        transcript_text="This transcript is long enough to pass validation but flag is off.",
    )

    with connect_write(temp_graph, purpose="test_synquery_disabled") as con:
        with pytest.raises(SynqueryAPIError):
            adapter.ingest_completed_transcript(con, transcript)


def test_adapter_transcript_ingest_rejects_empty_transcript(monkeypatch, temp_graph):
    monkeypatch.setenv("ANTIEK_SYNQUERY_ENABLED", "1")
    adapter = SynqueryAdapter(client=MockSynqueryClient())
    transcript = SynqueryTranscriptIngest(
        interview_id="interview-empty",
        expert_id="expert-empty",
        question_id="q-empty",
        transcript_text="   ",
    )

    with connect_write(temp_graph, purpose="test_synquery_empty") as con:
        with pytest.raises(ValueError, match="empty"):
            adapter.ingest_completed_transcript(con, transcript)
