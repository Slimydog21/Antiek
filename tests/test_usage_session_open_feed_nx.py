"""Residual (nx): twin_chase / floating_deep_research appear in usage by_source."""

from __future__ import annotations

from substrate.antiek_bench import (
    KNOWN_USAGE_FEED_SOURCES,
    InMemoryBenchStore,
    UsageEvent,
    record_usage_event,
    settings_usage_summary_payload,
    weekly_usage_summary,
)


def test_weekly_usage_summary_includes_twin_chase_and_floating_dr() -> None:
    store = InMemoryBenchStore()
    record_usage_event(
        UsageEvent(
            task_class="synthesize",
            outcome="worked",
            source="twin_chase",
            prompt_hint="Twin chase on paper",
        ),
        store=store,
    )
    record_usage_event(
        UsageEvent(
            task_class="wrestle",
            outcome="worked",
            source="floating_deep_research",
            prompt_hint="Highlight passage",
        ),
        store=store,
    )
    summary = weekly_usage_summary(store=store)
    assert summary["by_source"]["twin_chase"] == 1
    assert summary["by_source"]["floating_deep_research"] == 1
    assert "twin_chase" in summary["known_sources"]
    assert "floating_deep_research" in summary["known_sources"]
    assert "twin_chase" in KNOWN_USAGE_FEED_SOURCES

    payload = settings_usage_summary_payload(store=store, include_html=True)
    assert payload["by_source"]["twin_chase"] == 1
    assert "twin_chase" in payload["known_sources"]
    html = payload.get("html") or ""
    assert "Known feed sources" in html or "twin_chase" in html
