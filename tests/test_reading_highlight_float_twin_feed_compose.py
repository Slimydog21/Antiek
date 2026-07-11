"""Pure tests for reading highlight float + twin feed compose."""

from __future__ import annotations

import pytest

from substrate.reading_highlight_float_twin_feed_compose import (
    ReadingHighlightFloatTwinFeedComposeError,
    compose_reading_highlight_float_twin_feed,
    format_reading_highlight_float_twin_feed_summary,
)


def test_spawn_only_with_twin():
    c = compose_reading_highlight_float_twin_feed(
        session_id="sess-1",
        parent_asset_id="book-1",
        highlight="scaling laws under noise",
        gated=False,
        would_exceed=False,
        surface_action="spawn_only",
        operator_ack=True,
        source_families=["arxiv"],
        twin_findings=[
            {
                "source_id": "extra-1",
                "body": "claim A supported",
                "kind": "insight",
            }
        ],
        mark_for_prompt_context=True,
    )
    assert c.surface.surface_ready is True
    assert c.twin_feed is not None and c.twin_feed.feed_ready is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.pack_dispatched is False
    assert c.twin_written is False
    assert c.record_persisted is False
    assert "twin_written=false" in format_reading_highlight_float_twin_feed_summary(
        c
    )
    assert c.to_dict()["live_dispatched"] is False


def test_gated_fails():
    with pytest.raises(ReadingHighlightFloatTwinFeedComposeError, match="gated"):
        compose_reading_highlight_float_twin_feed(
            session_id="s",
            parent_asset_id="b",
            highlight="secret",
            gated=True,
            would_exceed=False,
            surface_action="spawn_only",
            operator_ack=True,
        )


def test_skip_twin():
    c = compose_reading_highlight_float_twin_feed(
        session_id="s",
        parent_asset_id="b",
        highlight="claim",
        gated=False,
        would_exceed=False,
        surface_action="spawn_only",
        operator_ack=True,
        include_twin_feed=False,
    )
    assert c.twin_feed is None
    assert c.surface.surface_ready is True
    assert c.pack_ready is True


def test_ack_false():
    c = compose_reading_highlight_float_twin_feed(
        session_id="s",
        parent_asset_id="b",
        highlight="claim",
        gated=False,
        would_exceed=False,
        surface_action="spawn_only",
        operator_ack=False,
    )
    assert c.surface.surface_ready is False
    assert c.pack_ready is False


def test_fullscreen():
    c = compose_reading_highlight_float_twin_feed(
        session_id="s",
        parent_asset_id="b",
        highlight="claim A",
        gated=False,
        would_exceed=False,
        surface_action="spawn_and_fullscreen",
        operator_ack=True,
    )
    assert c.surface.tray is not None
    assert c.surface.tray.action == "fullscreen_one"
    assert c.pack_ready is True
    assert c.merge_executed is False
