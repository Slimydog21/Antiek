"""Synquery API client + adapter tests (Sprint 21)."""

from __future__ import annotations

import pytest

from tools.synquery import (
    MockSynqueryClient,
    SynqueryAPIError,
    SynqueryAdapter,
    SynqueryExpert,
    SynqueryRequest,
)
from tools.synquery.client import feature_flag_enabled


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
