"""Residual (act): twin_write_seed usage stamps has_body for recursive rewrite."""

from __future__ import annotations

from substrate.antiek_bench import (
    InMemoryBenchStore,
    record_twin_write_seed_usage,
    settings_usage_summary_payload,
    weekly_usage_summary,
)


def test_record_twin_write_seed_usage_has_body_true() -> None:
    store = InMemoryBenchStore()
    row = record_twin_write_seed_usage(
        store=store,
        seed_source="research_progress_complete",
        prompt_hint="Final synthesis body",
        has_body=True,
    )
    assert row is not None
    assert row["has_body"] is True
    assert row["outcome"] == "worked"
    assert row["source"] == "research_progress_complete"


def test_record_twin_write_seed_usage_has_body_false_failed() -> None:
    store = InMemoryBenchStore()
    row = record_twin_write_seed_usage(
        store=store,
        seed_source="marketplace_host",
        prompt_hint="Title only host",
        has_body=False,
    )
    assert row is not None
    assert row["has_body"] is False
    # Title-only Write seed is weak rewrite signal → failed outcome.
    assert row["outcome"] == "failed"


def test_weekly_usage_summary_write_seed_body_honesty_aggregates() -> None:
    store = InMemoryBenchStore()
    record_twin_write_seed_usage(
        store=store,
        seed_source="deep_research_session",
        prompt_hint="body",
        has_body=True,
    )
    record_twin_write_seed_usage(
        store=store,
        seed_source="midnight_oil_deposit",
        prompt_hint="title",
        has_body=False,
    )
    # Legacy caller: no has_body → unknown bucket.
    record_twin_write_seed_usage(
        store=store,
        seed_source="spawn_merge",
        prompt_hint="legacy",
    )

    summary = weekly_usage_summary(store=store)
    assert summary["write_seed_with_body_count"] == 1
    assert summary["write_seed_title_only_count"] == 1
    assert summary["write_seed_body_unknown_count"] == 1
    assert summary["write_seed_event_count"] == 3
    # Title-only contributes failed outcome for suite rewrite learning.
    failed_total = sum(
        int(b.get("failed") or 0) for b in summary["by_task_class"].values()
    )
    assert failed_total >= 1
    worked_total = sum(
        int(b.get("worked") or 0) for b in summary["by_task_class"].values()
    )
    assert worked_total >= 2

    payload = settings_usage_summary_payload(store=store, include_html=True)
    assert payload["write_seed_with_body_count"] == 1
    assert payload["write_seed_title_only_count"] == 1
    assert payload["write_seed_body_unknown_count"] == 1
    assert "with_body=1" in (payload.get("html") or "")
    assert "title_only=1" in (payload.get("html") or "")
