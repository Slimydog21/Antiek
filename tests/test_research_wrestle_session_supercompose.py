"""Pure tests for research wrestle session super-compose."""

from __future__ import annotations

import pytest

from substrate.research_wrestle_session_supercompose import (
    ResearchWrestleSessionSupercomposeError,
    compose_research_wrestle_session,
    format_research_wrestle_session_summary,
)


def _ready(**kwargs):
    base = dict(
        session_id="ws-1",
        parent_asset_id="asset-1",
        floating_instance_count=2,
        completed_floating_count=1,
        twin_insight_count=3,
        twin_question_count=2,
        open_question_count=1,
        source_family_count=2,
        citation_pack_ready=True,
        quality_overall=0.8,
        would_exceed=False,
        preferred_view_mode="floating",
    )
    base.update(kwargs)
    return compose_research_wrestle_session(**base)


def test_wrestle_ready_never_dispatches():
    s = _ready()
    assert s.wrestle_ready is True
    assert s.live_dispatch_authorized is False
    assert s.authority == "research_wrestle_session_supercompose_advisory"
    assert s.to_dict()["live_dispatch_authorized"] is False
    assert "live_dispatch_authorized=false" in format_research_wrestle_session_summary(
        s
    )


def test_not_ready_without_sources_or_quality():
    assert _ready(source_family_count=0).wrestle_ready is False
    assert _ready(quality_overall=0.2, quality_floor=0.5).wrestle_ready is False
    assert _ready(source_family_count=0).live_dispatch_authorized is False


def test_budget_unknown_fails_closed_unless_override():
    s = _ready(would_exceed=None)
    assert s.budget_ready is False
    assert s.wrestle_ready is False
    ov = _ready(would_exceed=None, operator_override=True)
    assert ov.budget_ready is True
    assert ov.wrestle_ready is True
    assert ov.live_dispatch_authorized is False


def test_rejects_completed_gt_floating():
    with pytest.raises(
        ResearchWrestleSessionSupercomposeError, match="completed_floating_count"
    ):
        _ready(floating_instance_count=1, completed_floating_count=2)


def test_twin_substrate_without_floating():
    s = _ready(
        floating_instance_count=0,
        completed_floating_count=0,
        twin_insight_count=1,
        twin_question_count=0,
        open_question_count=0,
    )
    assert s.floating_ready is False
    assert s.twin_ready is True
    assert s.wrestle_ready is True
    assert s.live_dispatch_authorized is False
