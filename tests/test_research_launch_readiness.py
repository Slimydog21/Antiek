"""Hermetic tests for pure research launch readiness."""

from __future__ import annotations

import pytest

from substrate.research_launch_readiness import (
    ResearchLaunchReadinessError,
    evaluate_research_launch_readiness,
)


def test_launch_ready() -> None:
    d = evaluate_research_launch_readiness(
        session_id="sess-1",
        source_family_count=2,
        quality_overall=0.8,
        quality_floor=0.5,
        would_exceed=False,
    )
    assert d.launch_ready is True
    assert d.live_dispatch_authorized is False
    assert d.to_dict()["live_dispatch_authorized"] is False


def test_sources_zero() -> None:
    d = evaluate_research_launch_readiness(
        session_id="sess-1",
        source_family_count=0,
        quality_overall=0.9,
        would_exceed=False,
    )
    assert d.sources_ready is False
    assert d.launch_ready is False


def test_would_exceed_null_fail_closed() -> None:
    d = evaluate_research_launch_readiness(
        session_id="sess-1",
        source_family_count=1,
        quality_overall=None,
        would_exceed=None,
    )
    assert d.budget_ready is False
    assert d.launch_ready is False


def test_override_allows() -> None:
    d = evaluate_research_launch_readiness(
        session_id="sess-1",
        source_family_count=1,
        quality_overall=None,
        would_exceed=None,
        operator_override=True,
    )
    assert d.budget_ready is True
    assert d.launch_ready is True
    assert d.live_dispatch_authorized is False


def test_quality_below_floor() -> None:
    d = evaluate_research_launch_readiness(
        session_id="sess-1",
        source_family_count=1,
        quality_overall=0.2,
        quality_floor=0.5,
        would_exceed=False,
    )
    assert d.quality_ready is False
    assert d.launch_ready is False


def test_rejects_bool_as_count() -> None:
    with pytest.raises(ResearchLaunchReadinessError, match="integer"):
        evaluate_research_launch_readiness(
            session_id="s",
            source_family_count=True,  # type: ignore[arg-type]
            quality_overall=None,
            would_exceed=False,
        )
