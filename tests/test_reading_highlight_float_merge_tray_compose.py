"""Pure tests for reading highlight float merge tray compose."""

from __future__ import annotations

import pytest

from substrate.reading_highlight_float_merge_tray_compose import (
    ReadingHighlightFloatMergeTrayComposeError,
    compose_reading_highlight_float_merge_tray,
    format_reading_highlight_float_merge_tray_summary,
)


def test_spawn_only_ready_without_dispatch_or_merge():
    c = compose_reading_highlight_float_merge_tray(
        parent_asset_id="book-1",
        highlight="scaling laws under noise",
        gated=False,
        would_exceed=False,
        preferred_view_mode="floating",
        source_families=["arxiv"],
        surface_action="spawn_only",
        operator_ack=True,
    )
    assert c.surface_ready is True
    assert c.launch.launch_ready is True
    assert c.tray is None
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.pack_dispatched is False
    assert c.authority == "reading_highlight_float_merge_tray_compose_advisory"
    assert c.to_dict()["live_dispatched"] is False
    assert c.to_dict()["pack_dispatched"] is False
    summary = format_reading_highlight_float_merge_tray_summary(c)
    assert "live_dispatched=false" in summary
    assert "merge_executed=false" in summary
    assert "pack_dispatched=false" in summary


def test_spawn_and_fullscreen_and_draft_merge():
    fs = compose_reading_highlight_float_merge_tray(
        parent_asset_id="book-1",
        highlight="claim A",
        gated=False,
        would_exceed=False,
        surface_action="spawn_and_fullscreen",
        operator_ack=True,
    )
    assert fs.surface_ready is True
    assert fs.tray is not None
    assert fs.tray.action == "fullscreen_one"
    assert fs.tray.pack_dispatched is False

    draft = compose_reading_highlight_float_merge_tray(
        parent_asset_id="book-1",
        highlight="claim B",
        gated=False,
        would_exceed=False,
        surface_action="spawn_and_draft_merge",
        operator_ack=True,
    )
    assert draft.tray is not None
    assert draft.tray.action == "draft_merge_one"
    assert draft.merge_executed is False


def test_spawn_and_full_merge_not_ready_until_completed():
    c = compose_reading_highlight_float_merge_tray(
        parent_asset_id="book-1",
        highlight="claim C",
        gated=False,
        would_exceed=False,
        surface_action="spawn_and_full_merge",
        operator_ack=True,
    )
    assert c.tray is not None
    assert c.tray.tray_ready is False
    assert c.surface_ready is False
    assert c.live_dispatched is False
    assert c.merge_executed is False


def test_tray_collective_with_existing_completed_members():
    c = compose_reading_highlight_float_merge_tray(
        parent_asset_id="book-1",
        highlight="new highlight",
        gated=False,
        would_exceed=False,
        surface_action="tray_collective",
        operator_ack=True,
        existing_members=[
            {
                "instance_id": "existing-1",
                "parent_asset_id": "book-1",
                "status": "completed",
                "live_dispatched": False,
                "merge_executed": False,
            }
        ],
        selected_instance_ids=["existing-1"],
    )
    assert c.tray is not None
    assert c.tray.selected_count >= 2
    assert c.tray.action == "collective_pack"
    assert c.pack_dispatched is False
    assert c.live_dispatched is False


def test_tray_cohesive():
    c = compose_reading_highlight_float_merge_tray(
        parent_asset_id="book-1",
        highlight="new highlight",
        gated=False,
        would_exceed=False,
        surface_action="tray_cohesive",
        operator_ack=True,
        existing_members=[
            {
                "instance_id": "existing-1",
                "parent_asset_id": "book-1",
                "status": "completed",
                "live_dispatched": False,
                "merge_executed": False,
            }
        ],
        selected_instance_ids=["existing-1"],
    )
    assert c.tray is not None
    assert c.tray.action == "cohesive_prompt"
    assert c.pack_dispatched is False
    assert c.surface_ready is True


def test_rejects_gated_highlights():
    with pytest.raises(ReadingHighlightFloatMergeTrayComposeError, match="gated"):
        compose_reading_highlight_float_merge_tray(
            parent_asset_id="book-1",
            highlight="secret",
            gated=True,
            would_exceed=False,
            surface_action="spawn_only",
            operator_ack=True,
        )


def test_operator_ack_false_not_ready():
    c = compose_reading_highlight_float_merge_tray(
        parent_asset_id="book-1",
        highlight="claim",
        gated=False,
        would_exceed=False,
        surface_action="spawn_only",
        operator_ack=False,
    )
    assert c.launch.launch_ready is False
    assert c.surface_ready is False
    assert c.live_dispatched is False


def test_would_exceed_blocks_without_override():
    c = compose_reading_highlight_float_merge_tray(
        parent_asset_id="book-1",
        highlight="claim",
        gated=False,
        would_exceed=True,
        surface_action="spawn_only",
        operator_ack=True,
    )
    assert c.launch.budget_ready is False
    assert c.surface_ready is False
    assert c.live_dispatched is False
