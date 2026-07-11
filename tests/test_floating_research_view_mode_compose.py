"""Pure tests for floating research view-mode compose."""

from __future__ import annotations

import pytest

from substrate.floating_deep_research import (
    mark_floating_completed,
    spawn_floating_from_highlight,
)
from substrate.floating_research_view_mode_compose import (
    FloatingResearchViewModeComposeError,
    assess_floating_view_mode_capabilities,
    compose_floating_research_view_mode,
    format_floating_view_mode_compose_summary,
)


def _base():
    return spawn_floating_from_highlight(
        parent_asset_id="asset-read-1",
        highlight="scaling laws under noise",
        gated=False,
    )


def test_capabilities_proposed():
    caps = assess_floating_view_mode_capabilities(_base())
    assert caps.can_float is True
    assert caps.can_fullscreen is True
    assert caps.can_draft_merge is True
    assert caps.can_full_merge is False


def test_capabilities_completed_allows_full():
    caps = assess_floating_view_mode_capabilities(mark_floating_completed(_base()))
    assert caps.can_full_merge is True


def test_fullscreen_then_float_honesty():
    c = compose_floating_research_view_mode(instance=_base(), action="fullscreen")
    assert c.view_mode == "fullscreen"
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.merge_intent is None
    assert c.action_applied is True
    assert c.authority == "floating_research_view_mode_compose_advisory"
    back = compose_floating_research_view_mode(instance=c.instance, action="float")
    assert back.view_mode == "floating"
    assert back.live_dispatched is False
    assert back.merge_executed is False
    assert "live_dispatched=false" in format_floating_view_mode_compose_summary(back)
    d = c.to_dict()
    assert d["live_dispatched"] is False
    assert d["merge_executed"] is False


def test_draft_merge_intent_only():
    c = compose_floating_research_view_mode(
        instance=_base(), action="propose_draft_merge"
    )
    assert c.merge_intent is not None
    assert c.merge_intent.kind == "draft_merge"
    assert c.merge_intent.merge_executed is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.view_mode not in ("merged_draft", "merged_full")


def test_full_merge_requires_completed_and_ack():
    with pytest.raises(FloatingResearchViewModeComposeError, match="completed"):
        compose_floating_research_view_mode(
            instance=_base(),
            action="propose_full_merge",
            operator_ack=True,
        )
    completed = mark_floating_completed(_base())
    with pytest.raises(FloatingResearchViewModeComposeError, match="operator_ack"):
        compose_floating_research_view_mode(
            instance=completed,
            action="propose_full_merge",
            operator_ack=False,
        )
    with pytest.raises(FloatingResearchViewModeComposeError, match="operator_ack"):
        compose_floating_research_view_mode(
            instance=completed,
            action="propose_full_merge",
        )
    c = compose_floating_research_view_mode(
        instance=completed,
        action="propose_full_merge",
        operator_ack=True,
    )
    assert c.merge_intent is not None
    assert c.merge_intent.kind == "full_merge"
    assert c.merge_intent.merge_executed is False
    assert c.merge_executed is False
    assert c.live_dispatched is False


def test_rejects_invalid_action():
    with pytest.raises(FloatingResearchViewModeComposeError, match="action must be"):
        compose_floating_research_view_mode(instance=_base(), action="teleport")
