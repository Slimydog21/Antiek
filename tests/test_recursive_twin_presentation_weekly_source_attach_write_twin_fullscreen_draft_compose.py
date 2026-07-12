"""Pure tests for recursive twin presentation over weekly source-attach write twin."""

from __future__ import annotations

from substrate.recursive_twin_presentation_weekly_source_attach_write_twin_fullscreen_draft_compose import (
    compose_recursive_twin_presentation_weekly_source_attach_write_twin_fullscreen_draft,
    format_recursive_twin_presentation_weekly_source_attach_write_twin_fullscreen_draft_summary,
)
from tests.test_antiek_bench_weekly_source_attach_write_twin_fullscreen_draft_compose import (
    SOURCE_PACK,
    WEEKLY_LEARN,
)

TWIN = {
    "parent_asset_id": "book-1",
    "source_excerpt": (
        "<p>Scaling laws hold under noise in compute-optimal regimes.</p>"
    ),
    "focus_questions": ["Where does it break?", "What residual gaps?"],
    "existing_twin_asset_id": "twin-book-1",
}

PRESENTATION = {
    "view_mode": "side_panel",
    "open_requested": True,
    "merge_to_parent_preview": False,
    "presented_insights": [
        "scaling laws hold under noise in compute-optimal regimes",
    ],
    "presented_questions": [
        "Where does scaling break under distribution shift?",
    ],
}

WEEKLY_PACK = {
    "weekly_learn": WEEKLY_LEARN,
    "source_pack": SOURCE_PACK,
}


def test_twin_presentation_weekly_source_attach_ready():
    c = compose_recursive_twin_presentation_weekly_source_attach_write_twin_fullscreen_draft(
        twin=TWIN,
        presentation=PRESENTATION,
        weekly_pack=WEEKLY_PACK,
        operator_ack=True,
    )
    assert c.twin.twin_propose_ready is True
    assert c.presentation.presentation_ready is True
    assert c.weekly_pack.pack_ready is True
    assert c.weekly_pack.learn_ready is True
    assert c.parent_aligned is True
    assert c.session_aligned is True
    assert c.pack_ready is True
    assert c.twin_written is False
    assert c.prompts_injected is False
    assert c.merge_executed is False
    assert c.backlog_mutated is False
    assert c.suite_rewritten is False
    assert c.remote_fetched is False
    assert c.pdf_primary is False
    assert c.draft_written is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "recursive_twin_presentation_weekly_source_attach_write_twin_fullscreen_draft_compose_advisory"
    )
    assert "twin_written=false" in (
        format_recursive_twin_presentation_weekly_source_attach_write_twin_fullscreen_draft_summary(
            c
        )
    )


def test_operator_ack_false_blocks():
    c = compose_recursive_twin_presentation_weekly_source_attach_write_twin_fullscreen_draft(
        twin=TWIN,
        presentation=PRESENTATION,
        weekly_pack=WEEKLY_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.presentation.presentation_ready is False
    assert c.twin_written is False
    assert c.backlog_mutated is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_open_requested_false_blocks():
    c = compose_recursive_twin_presentation_weekly_source_attach_write_twin_fullscreen_draft(
        twin=TWIN,
        presentation={**PRESENTATION, "open_requested": False},
        weekly_pack=WEEKLY_PACK,
        operator_ack=True,
    )
    assert c.presentation.presentation_ready is False
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.backlog_mutated is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    c = compose_recursive_twin_presentation_weekly_source_attach_write_twin_fullscreen_draft(
        twin={**TWIN, "parent_asset_id": "book-other"},
        presentation=PRESENTATION,
        weekly_pack=WEEKLY_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"
