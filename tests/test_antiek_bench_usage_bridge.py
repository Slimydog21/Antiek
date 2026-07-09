"""Engagement → Antiek-bench usage bridge for recursive suite rewrite."""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.antiek_bench import (  # noqa: E402
    InMemoryBenchStore,
    classify_engagement_task,
    list_usage_events,
    propose_from_recorded_usage,
    record_session_flywheel_usage,
    record_usage_event,
    weekly_usage_summary,
)
from substrate.antiek_bench.usage_bridge import UsageEvent  # noqa: E402


def test_classify_engagement_task():
    assert classify_engagement_task(is_book_asset=True) == "book_qa"
    assert classify_engagement_task(is_collective=True) == "synthesize"
    assert classify_engagement_task(has_twins=True, has_source_refs=True) == "wrestle"
    assert classify_engagement_task(has_twins=True) == "distill"


def test_record_and_propose_from_usage():
    store = InMemoryBenchStore()
    record_session_flywheel_usage(
        store=store,
        twin_count=2,
        ref_count=1,
        status="complete",
        model_id="glm-test",
        prompt_hint="attention mechanism failure modes",
    )
    record_usage_event(
        UsageEvent(
            task_class="book_qa",
            outcome="failed",
            prompt_hint="long-context book chapter QA failed",
        ),
        store=store,
    )
    events = list_usage_events(store=store)
    assert len(events) == 2
    summary = weekly_usage_summary(store=store)
    assert summary["event_count"] == 2
    assert summary["view_format"] == "html"
    assert "wrestle" in summary["by_task_class"] or "distill" in summary["by_task_class"]

    proposal = propose_from_recorded_usage(store=store)
    assert proposal.status == "proposed"
    assert proposal.proposal_id.startswith("prop_")
    assert proposal.rationale  # non-empty


def test_record_usage_requires_fields():
    store = InMemoryBenchStore()
    with pytest.raises(ValueError):
        record_usage_event({"outcome": "worked"}, store=store)
