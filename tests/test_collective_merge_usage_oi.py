"""Residual (oi): collective merge usage events for Antiek-bench rewrite feed."""

from __future__ import annotations

from substrate.antiek_bench import (
    KNOWN_USAGE_FEED_SOURCES,
    InMemoryBenchStore,
    record_collective_merge_usage,
    weekly_usage_summary,
)


def test_record_collective_merge_usage_prefers_research_tier() -> None:
    store = InMemoryBenchStore()
    row = record_collective_merge_usage(
        store=store,
        spawn_count=2,
        research_tier="wrestle",
        prompt_hint="cohesive unit",
        mode="draft_combined",
    )
    assert row["source"] == "collective_merge"
    assert row["task_class"] == "wrestle"
    assert row["outcome"] == "worked"
    assert row["prompt_hint_present"] is True
    assert "prompt_hint" not in row
    assert "collective_merge" in KNOWN_USAGE_FEED_SOURCES
    summary = weekly_usage_summary(store=store)
    assert summary["by_source"]["collective_merge"] == 1


def test_record_collective_merge_usage_defaults_to_synthesize() -> None:
    store = InMemoryBenchStore()
    row = record_collective_merge_usage(
        store=store,
        spawn_count=3,
        research_tier=None,
        prompt_hint="unit",
        mode="prompt_unit",
    )
    assert row["task_class"] == "synthesize"
