"""Pure tests for Antiek-bench weekly learn over twin presentation write collective."""

from __future__ import annotations

from substrate.antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose import (
    compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective,
    format_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_summary,
)
from tests.test_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose import (
    PRESENTATION,
    TWIN,
    WRITE_PACK,
)

WEEKLY_LEARN = {
    "week_id": "2026-W28",
    "min_events_per_task": 2,
    "events": [
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
}

TWIN_PRESENTATION_PACK = {
    "twin": TWIN,
    "presentation": PRESENTATION,
    "write_pack": WRITE_PACK,
}


def test_weekly_learn_twin_presentation_write_collective_ready():
    c = compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective(
        weekly_learn=WEEKLY_LEARN,
        twin_presentation_pack=TWIN_PRESENTATION_PACK,
        operator_ack=True,
    )
    assert c.weekly_learn.learn_ready is True
    assert c.learn_ready is True
    assert c.twin_presentation_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.backlog_mutated is False
    assert c.store_mutated is False
    assert c.suite_rewritten is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.live_dispatched is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_advisory"
    )
    assert "backlog_mutated=false" in (
        format_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_summary(
            c
        )
    )


def test_operator_ack_false_blocks():
    c = compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective(
        weekly_learn=WEEKLY_LEARN,
        twin_presentation_pack=TWIN_PRESENTATION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.learn_ready is False
    assert c.backlog_mutated is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"


def test_sparse_events_block_learn():
    c = compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective(
        weekly_learn={**WEEKLY_LEARN, "min_events_per_task": 5},
        twin_presentation_pack=TWIN_PRESENTATION_PACK,
        operator_ack=True,
    )
    assert c.weekly_learn.learn_ready is False
    assert c.learn_ready is False
    assert c.pack_ready is False
    assert c.backlog_mutated is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"


def test_open_requested_false_blocks_twin_presentation():
    c = compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective(
        weekly_learn=WEEKLY_LEARN,
        twin_presentation_pack={
            **TWIN_PRESENTATION_PACK,
            "presentation": {**PRESENTATION, "open_requested": False},
        },
        operator_ack=True,
    )
    assert c.twin_presentation_pack.presentation.presentation_ready is False
    assert c.twin_presentation_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.backlog_mutated is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
