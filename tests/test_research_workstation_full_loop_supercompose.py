"""Pure tests for research workstation full-loop super-compose."""

from __future__ import annotations

import pytest

from substrate.research_workstation_full_loop_supercompose import (
    ResearchWorkstationFullLoopSupercomposeError,
    compose_research_workstation_full_loop,
)


def _wrestle_ready(**kwargs):
    base = dict(
        session_id="ws-1",
        parent_asset_id="asset-1",
        floating_instance_count=2,
        completed_floating_count=1,
        twin_insight_count=2,
        twin_question_count=1,
        open_question_count=1,
        source_family_count=2,
        citation_pack_ready=True,
        quality_overall=0.8,
        would_exceed=False,
        preferred_view_mode="floating",
    )
    base.update(kwargs)
    return base


def test_full_loop_ready():
    c = compose_research_workstation_full_loop(
        wrestle=_wrestle_ready(),
        source_attach={
            "attach_ready": True,
            "remote_fetched": False,
            "source_count": 2,
        },
        view_mode={"preferred_view_mode": "fullscreen", "floating_instance_count": 2},
        budget={"would_exceed": False, "selected_model_id": "gpt-5"},
    )
    assert c.full_loop_ready is True
    assert c.live_dispatch_authorized is False
    assert c.to_dict()["live_dispatch_authorized"] is False


def test_not_ready_without_sources():
    c = compose_research_workstation_full_loop(
        wrestle=_wrestle_ready(),
        source_attach={
            "attach_ready": False,
            "remote_fetched": False,
            "source_count": 0,
        },
        view_mode={"preferred_view_mode": "floating", "floating_instance_count": 1},
        budget={"would_exceed": False},
    )
    assert c.full_loop_ready is False
    assert c.live_dispatch_authorized is False


def test_rejects_remote_fetched_true():
    with pytest.raises(
        ResearchWorkstationFullLoopSupercomposeError, match="remote_fetched"
    ):
        compose_research_workstation_full_loop(
            wrestle=_wrestle_ready(),
            source_attach={
                "attach_ready": True,
                "remote_fetched": True,
                "source_count": 1,
            },
            view_mode={"preferred_view_mode": None, "floating_instance_count": 1},
            budget={"would_exceed": False},
        )
