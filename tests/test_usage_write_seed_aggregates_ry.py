"""Residual (ry): weekly usage summary exposes Write-seed aggregates (SSOT)."""

from __future__ import annotations

from substrate.antiek_bench import (
    TWIN_WRITE_SEED_USAGE_SOURCES,
    InMemoryBenchStore,
    UsageEvent,
    record_twin_write_seed_usage,
    record_usage_event,
    settings_usage_summary_payload,
    weekly_usage_summary,
)


def test_weekly_usage_write_seed_aggregates() -> None:
    store = InMemoryBenchStore()
    record_twin_write_seed_usage(
        store=store,
        seed_source="twin_promote_context",
        prompt_hint="promote → write",
    )
    record_twin_write_seed_usage(
        store=store,
        seed_source="deep_research_session",
        prompt_hint="dr → write",
    )
    record_usage_event(
        UsageEvent(
            task_class="wrestle",
            outcome="worked",
            prompt_hint="chase",
            source="twin_chase",
        ),
        store=store,
    )
    summary = weekly_usage_summary(store=store)
    assert summary["write_seed_source_count"] == 2
    assert summary["write_seed_event_count"] == 2
    assert summary["write_seed_by_source"]["twin_promote_context"] == 1
    assert summary["write_seed_by_source"]["deep_research_session"] == 1
    assert "twin_chase" not in summary["write_seed_by_source"]
    # known catalog includes all twin write seeds
    assert summary["write_seed_known_count"] == len(TWIN_WRITE_SEED_USAGE_SOURCES)

    payload = settings_usage_summary_payload(store=store, include_html=True)
    assert payload["write_seed_source_count"] == 2
    assert payload["write_seed_event_count"] == 2
    assert payload["write_seed_known_count"] == len(TWIN_WRITE_SEED_USAGE_SOURCES)
    assert "Write seed feeds" in (payload.get("html") or "")
