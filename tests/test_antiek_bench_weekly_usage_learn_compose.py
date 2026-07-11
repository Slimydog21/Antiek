"""Pure tests for Antiek-bench weekly usage-learn compose."""

from __future__ import annotations

import pytest

from substrate.antiek_bench_weekly_usage_learn_compose import (
    AntiekBenchWeeklyUsageLearnComposeError,
    compose_antiek_bench_weekly_usage_learn,
)


def test_proposals_without_mutation():
    c = compose_antiek_bench_weekly_usage_learn(
        week_id="2026-W28",
        operator_ack=True,
        min_events_per_task=2,
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
                "task": "twin_notes",
                "model_id": "claude",
                "outcome": "worked",
            },
            {
                "event_id": "e4",
                "task": "twin_notes",
                "model_id": "claude",
                "outcome": "worked",
            },
        ],
    )
    assert c.learn_ready is True
    assert c.proposal_count == 2
    assert c.backlog_mutated is False
    assert c.store_mutated is False
    by_task = {p.task: p for p in c.proposals}
    assert by_task["deep_research"].emphasis == "expand_failure_cases"
    assert by_task["twin_notes"].emphasis == "hold_stable"
    assert c.to_dict()["backlog_mutated"] is False


def test_not_ready_paths():
    no_ack = compose_antiek_bench_weekly_usage_learn(
        week_id="w",
        operator_ack=False,
        min_events_per_task=2,
        events=[
            {
                "event_id": "e1",
                "task": "t",
                "model_id": "m",
                "outcome": "failed",
            },
            {
                "event_id": "e2",
                "task": "t",
                "model_id": "m",
                "outcome": "failed",
            },
        ],
    )
    assert no_ack.learn_ready is False
    sparse = compose_antiek_bench_weekly_usage_learn(
        week_id="w",
        operator_ack=True,
        min_events_per_task=5,
        events=[
            {
                "event_id": "e1",
                "task": "t",
                "model_id": "m",
                "outcome": "worked",
            }
        ],
    )
    assert sparse.proposal_count == 0
    assert sparse.learn_ready is False


def test_rejects_duplicate():
    with pytest.raises(AntiekBenchWeeklyUsageLearnComposeError, match="duplicate"):
        compose_antiek_bench_weekly_usage_learn(
            week_id="w",
            operator_ack=True,
            events=[
                {
                    "event_id": "e1",
                    "task": "t",
                    "model_id": "m",
                    "outcome": "worked",
                },
                {
                    "event_id": "e1",
                    "task": "t",
                    "model_id": "m",
                    "outcome": "failed",
                },
            ],
        )
