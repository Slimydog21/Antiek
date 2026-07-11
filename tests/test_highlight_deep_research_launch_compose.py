"""Pure tests for highlight deep research launch compose."""

from __future__ import annotations

import pytest

from substrate.highlight_deep_research_launch_compose import (
    HighlightDeepResearchLaunchComposeError,
    compose_highlight_deep_research_launch,
)


def test_launch_ready_no_dispatch():
    c = compose_highlight_deep_research_launch(
        parent_asset_id="asset-read-1",
        highlight="scaling laws under noise",
        gated=False,
        preferred_view_mode="fullscreen",
        would_exceed=False,
        selected_model_id="gpt-5",
        source_families=["arxiv", "substack"],
        operator_ack=True,
    )
    assert c.launch_ready is True
    assert c.preferred_view_mode == "fullscreen"
    assert c.instance.view_mode == "fullscreen"
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.source_family_count == 2
    assert c.to_dict()["live_dispatched"] is False


def test_budget_unknown_fails_closed():
    unk = compose_highlight_deep_research_launch(
        parent_asset_id="a",
        highlight="h",
        gated=False,
        would_exceed=None,
        operator_ack=True,
    )
    assert unk.budget_ready is False
    assert unk.launch_ready is False
    ov = compose_highlight_deep_research_launch(
        parent_asset_id="a",
        highlight="h",
        gated=False,
        would_exceed=None,
        operator_override=True,
        operator_ack=True,
    )
    assert ov.budget_ready is True
    assert ov.launch_ready is True
    assert ov.live_dispatched is False


def test_rejects_gated_and_secret_model():
    with pytest.raises(HighlightDeepResearchLaunchComposeError, match="gated"):
        compose_highlight_deep_research_launch(
            parent_asset_id="a",
            highlight="h",
            gated=True,
            would_exceed=False,
            operator_ack=True,
        )
    with pytest.raises(
        HighlightDeepResearchLaunchComposeError, match="secret|model id"
    ):
        compose_highlight_deep_research_launch(
            parent_asset_id="a",
            highlight="h",
            gated=False,
            would_exceed=False,
            selected_model_id="sk-secretkey",
            operator_ack=True,
        )


def test_no_ack_not_ready():
    c = compose_highlight_deep_research_launch(
        parent_asset_id="a",
        highlight="h",
        gated=False,
        would_exceed=False,
        operator_ack=False,
    )
    assert c.launch_ready is False
    assert c.live_dispatched is False
