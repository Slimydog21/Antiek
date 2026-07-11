"""Hermetic tests for research workstation session compose."""

from __future__ import annotations

import pytest

from substrate.research_workstation_session_compose import (
    ResearchWorkstationSessionComposeError,
    compose_research_workstation_session,
)


def _ready(**kwargs: object):
    base = dict(
        session_id="sess-1",
        parent_asset_id="asset-1",
        floating_instance_count=1,
        twin_bound=True,
        source_family_count=2,
        quality_overall=0.8,
        quality_floor=0.5,
        would_exceed=False,
        cohesive_pack_ready=False,
        operator_override=False,
    )
    base.update(kwargs)
    return compose_research_workstation_session(**base)  # type: ignore[arg-type]


def test_ready_without_live_dispatch() -> None:
    s = _ready()
    assert s.session_ready is True
    assert s.live_dispatch_authorized is False
    assert s.to_dict()["live_dispatch_authorized"] is False
    assert s.authority == "research_workstation_session_compose_advisory"


def test_cohesive_required_for_two_floating() -> None:
    s = _ready(floating_instance_count=2, cohesive_pack_ready=False)
    assert s.session_ready is False
    assert s.live_dispatch_authorized is False
    ready = _ready(floating_instance_count=2, cohesive_pack_ready=True)
    assert ready.session_ready is True
    assert ready.live_dispatch_authorized is False


def test_would_exceed_null_honesty() -> None:
    s = _ready(would_exceed=None)
    assert s.budget_ready is False
    assert s.session_ready is False
    over = _ready(would_exceed=None, operator_override=True)
    assert over.budget_ready is True
    assert over.live_dispatch_authorized is False


def test_quality_unknown() -> None:
    s = _ready(quality_overall=None)
    assert s.quality_ready is False
    assert any("no invent" in n for n in s.notes)


def test_rejects_blank_and_bad_types() -> None:
    with pytest.raises(ResearchWorkstationSessionComposeError, match="session_id"):
        _ready(session_id="  ")
    with pytest.raises(
        ResearchWorkstationSessionComposeError, match="floating_instance_count"
    ):
        _ready(floating_instance_count=-1)
    with pytest.raises(ResearchWorkstationSessionComposeError, match="twin_bound"):
        compose_research_workstation_session(
            session_id="s",
            parent_asset_id="p",
            floating_instance_count=1,
            twin_bound="yes",  # type: ignore[arg-type]
            source_family_count=1,
            quality_overall=0.9,
            would_exceed=False,
        )
