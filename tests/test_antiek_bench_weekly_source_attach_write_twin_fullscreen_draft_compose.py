"""Pure tests for Antiek-bench weekly learn over source-attach write twin pack."""

from __future__ import annotations

from substrate.antiek_bench_weekly_source_attach_write_twin_fullscreen_draft_compose import (
    compose_antiek_bench_weekly_source_attach_write_twin_fullscreen_draft,
    format_antiek_bench_weekly_source_attach_write_twin_fullscreen_draft_summary,
)
from tests.test_source_attach_write_twin_fullscreen_draft_before_merge_compose import (
    SOURCES,
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

SOURCE_PACK = {
    "sources": SOURCES,
    "write_pack": WRITE_PACK,
}


def test_weekly_learn_source_attach_write_twin_ready():
    c = compose_antiek_bench_weekly_source_attach_write_twin_fullscreen_draft(
        weekly_learn=WEEKLY_LEARN,
        source_pack=SOURCE_PACK,
        operator_ack=True,
    )
    assert c.weekly_learn.learn_ready is True
    assert c.learn_ready is True
    assert c.source_pack.pack_ready is True
    assert c.attach_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.backlog_mutated is False
    assert c.store_mutated is False
    assert c.suite_rewritten is False
    assert c.remote_fetched is False
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.twin_written is False
    assert c.live_dispatched is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "antiek_bench_weekly_source_attach_write_twin_fullscreen_draft_compose_advisory"
    )
    assert "backlog_mutated=false" in (
        format_antiek_bench_weekly_source_attach_write_twin_fullscreen_draft_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_antiek_bench_weekly_source_attach_write_twin_fullscreen_draft(
        weekly_learn=WEEKLY_LEARN,
        source_pack=SOURCE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.backlog_mutated is False
    assert c.remote_fetched is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_antiek_bench_weekly_source_attach_write_twin_fullscreen_draft(
        weekly_learn=WEEKLY_LEARN,
        source_pack={
            "sources": {**SOURCES, "session_id": "sess-other"},
            "write_pack": WRITE_PACK,
        },
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.production_router_verdict == "REJECT"


def test_sparse_events_block_learn():
    c = compose_antiek_bench_weekly_source_attach_write_twin_fullscreen_draft(
        weekly_learn={
            **WEEKLY_LEARN,
            "events": [
                {
                    "event_id": "e1",
                    "task": "deep_research",
                    "model_id": "gpt-5",
                    "outcome": "failed",
                }
            ],
        },
        source_pack=SOURCE_PACK,
        operator_ack=True,
    )
    assert c.learn_ready is False
    assert c.pack_ready is False
    assert c.backlog_mutated is False
    assert c.suite_rewritten is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"
