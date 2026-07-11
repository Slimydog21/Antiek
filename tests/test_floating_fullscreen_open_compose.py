"""Pure tests for floating fullscreen open compose."""

from __future__ import annotations

import pytest

from substrate.floating_fullscreen_open_compose import (
    FloatingFullscreenOpenComposeError,
    compose_floating_fullscreen_open,
    format_floating_fullscreen_open_summary,
)


def test_spawn_and_fullscreen():
    c = compose_floating_fullscreen_open(
        session_id="sess-1",
        parent_asset_id="asset-1",
        highlight="Scaling laws claim from page 12",
        prompt="What evidence supports this?",
        gated=False,
        operator_ack=True,
    )
    assert c.instance.view_mode == "fullscreen"
    assert c.view_mode.action_applied is True
    assert c.tray.action == "fullscreen_one"
    assert c.tray.tray_ready is True
    assert c.fullscreen_ready is True
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.pack_dispatched is False
    assert "live_dispatched=false" in format_floating_fullscreen_open_summary(c)
    assert c.to_dict()["pack_dispatched"] is False


def test_existing_instance():
    c = compose_floating_fullscreen_open(
        session_id="sess-2",
        parent_asset_id="asset-1",
        existing_instance={
            "instance_id": "fdr_existing",
            "parent_asset_id": "asset-1",
            "highlight": "prior float",
            "prompt": "chase",
            "view_mode": "floating",
            "status": "open",
            "live_dispatched": False,
            "merge_executed": False,
            "notes": [],
            "authority": "operator_spawn_only",
        },
        operator_ack=True,
    )
    assert c.instance.instance_id == "fdr_existing"
    assert c.instance.view_mode == "fullscreen"
    assert c.fullscreen_ready is True
    assert c.live_dispatched is False


def test_gated_blocks():
    with pytest.raises(FloatingFullscreenOpenComposeError, match="gated"):
        compose_floating_fullscreen_open(
            session_id="s",
            parent_asset_id="a",
            highlight="secret",
            gated=True,
            operator_ack=True,
        )


def test_ack_false_blocks_ready():
    c = compose_floating_fullscreen_open(
        session_id="sess-3",
        parent_asset_id="asset-1",
        highlight="open claim",
        gated=False,
        operator_ack=False,
    )
    assert c.fullscreen_ready is False
    assert c.live_dispatched is False
    assert c.merge_executed is False


def test_closed_rejected():
    with pytest.raises(FloatingFullscreenOpenComposeError, match="closed"):
        compose_floating_fullscreen_open(
            session_id="s",
            parent_asset_id="asset-1",
            existing_instance={
                "instance_id": "fdr_closed",
                "parent_asset_id": "asset-1",
                "highlight": "done",
                "prompt": "p",
                "view_mode": "floating",
                "status": "closed",
                "live_dispatched": False,
                "merge_executed": False,
            },
            operator_ack=True,
        )


def test_spawn_requires_gated():
    with pytest.raises(FloatingFullscreenOpenComposeError, match="gated"):
        compose_floating_fullscreen_open(
            session_id="s",
            parent_asset_id="a",
            highlight="h",
            operator_ack=True,
        )
