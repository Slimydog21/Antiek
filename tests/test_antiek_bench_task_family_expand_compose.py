"""Pure tests for Antiek-bench task-family expand compose."""

from __future__ import annotations

import pytest

from substrate.antiek_bench_task_family_expand_compose import (
    AntiekBenchTaskFamilyExpandComposeError,
    compose_antiek_bench_task_family_expand,
    format_antiek_bench_task_family_expand_summary,
)


def test_expand_ready():
    c = compose_antiek_bench_task_family_expand(
        week_id="2026-W28",
        existing_tasks=["deep_research", "twin_notes"],
        proposed_new_tasks=[
            {"task": "marketplace_port", "description": "HTML book host quality"}
        ],
        events=[
            {
                "event_id": "e1",
                "task": "deep_research",
                "model_id": "gpt-5",
                "outcome": "failed",
            },
            {
                "event_id": "e2",
                "task": "deep_research",
                "model_id": "gpt-5",
                "outcome": "failed",
            },
            {
                "event_id": "e3",
                "task": "deep_research",
                "model_id": "composer",
                "outcome": "failed",
            },
            {
                "event_id": "e4",
                "task": "twin_notes",
                "model_id": "gpt-5",
                "outcome": "worked",
            },
            {
                "event_id": "e5",
                "task": "twin_notes",
                "model_id": "gpt-5",
                "outcome": "worked",
            },
            {
                "event_id": "e6",
                "task": "twin_notes",
                "model_id": "gpt-5",
                "outcome": "worked",
            },
        ],
        operator_ack=True,
        min_events_per_task=3,
    )
    assert c.expand_ready is True
    assert c.new_proposed_count == 1
    assert c.backlog_mutated is False
    assert c.store_mutated is False
    assert c.suite_rewritten is False
    assert any(f.task == "marketplace_port" for f in c.families)
    s = format_antiek_bench_task_family_expand_summary(c)
    assert "suite_rewritten=false" in s
    assert c.to_dict()["suite_rewritten"] is False


def test_ack_false():
    c = compose_antiek_bench_task_family_expand(
        week_id="w",
        existing_tasks=["deep_research"],
        proposed_new_tasks=[{"task": "chase_swarm"}],
        events=[],
        operator_ack=False,
    )
    assert c.expand_ready is False
    assert c.suite_rewritten is False


def test_no_expand():
    c = compose_antiek_bench_task_family_expand(
        week_id="w",
        existing_tasks=["deep_research"],
        events=[
            {
                "event_id": "e1",
                "task": "deep_research",
                "model_id": "m",
                "outcome": "worked",
            }
        ],
        operator_ack=True,
        min_events_per_task=3,
    )
    assert c.expand_ready is False


def test_duplicate_existing():
    with pytest.raises(
        AntiekBenchTaskFamilyExpandComposeError, match="duplicate"
    ):
        compose_antiek_bench_task_family_expand(
            week_id="w",
            existing_tasks=["a", "a"],
            events=[],
            operator_ack=True,
        )
