"""Residual (qy): deep_research_session + research_progress_complete bench feed."""

from __future__ import annotations

from substrate.antiek_bench import (
    KNOWN_USAGE_FEED_SOURCES,
    TWIN_WRITE_SEED_USAGE_SOURCES,
    InMemoryBenchStore,
    record_twin_write_seed_usage,
    settings_usage_summary_payload,
    weekly_usage_summary,
)


def test_known_sources_include_dr_write_seeds() -> None:
    assert "deep_research_session" in KNOWN_USAGE_FEED_SOURCES
    assert "research_progress_complete" in KNOWN_USAGE_FEED_SOURCES
    assert TWIN_WRITE_SEED_USAGE_SOURCES == frozenset(
        {"deep_research_session", "research_progress_complete"}
    )


def test_record_twin_write_seed_usage_by_source() -> None:
    store = InMemoryBenchStore()
    assert (
        record_twin_write_seed_usage(
            store=store,
            seed_source="twin_draft_selected",
            prompt_hint="ignore",
        )
        is None
    )
    row = record_twin_write_seed_usage(
        store=store,
        seed_source="deep_research_session",
        prompt_hint="Selection seed",
        research_tier="wrestle",
    )
    assert row is not None
    assert row["source"] == "deep_research_session"
    assert row["task_class"] == "wrestle"
    assert row["outcome"] == "worked"

    row2 = record_twin_write_seed_usage(
        store=store,
        seed_source="research_progress_complete",
        prompt_hint="Terminal cite",
        research_tier="deep",
    )
    assert row2 is not None
    assert row2["source"] == "research_progress_complete"
    assert row2["task_class"] == "synthesize"

    summary = weekly_usage_summary(store=store)
    assert summary["by_source"]["deep_research_session"] == 1
    assert summary["by_source"]["research_progress_complete"] == 1
    assert "deep_research_session" in summary["known_sources"]
    assert "research_progress_complete" in summary["known_sources"]

    payload = settings_usage_summary_payload(store=store, include_html=True)
    assert payload["by_source"]["deep_research_session"] == 1
    assert "deep_research_session" in payload["known_sources"]
