"""Hermetic tests for pure Midnight Oil swarm brief."""

from __future__ import annotations

import pytest

from substrate.midnight_oil_swarm_brief import (
    MidnightOilSwarmBriefError,
    build_midnight_oil_swarm_brief,
)

GOALS = [
    {"goal_id": "g1", "statement": "Map arxiv", "priority": 2},
    {"goal_id": "g2", "statement": "Substack", "priority": 1},
]


def test_builds_lanes_never_live() -> None:
    b = build_midnight_oil_swarm_brief(
        operator_id="op-1",
        work_minutes=120,
        goals=GOALS,
        price_ceiling_usd=5,
        recommended_ceiling_usd=4,
        operator_approved=True,
    )
    assert len(b.lanes) == 2
    assert abs(b.lanes[0].time_share - 2 / 3) < 1e-9
    assert b.dispatch_ready is True
    assert b.live_execution_authorized is False
    assert b.to_dict()["live_execution_authorized"] is False


def test_no_approval() -> None:
    b = build_midnight_oil_swarm_brief(
        operator_id="op",
        work_minutes=60,
        goals=GOALS,
        price_ceiling_usd=5,
        operator_approved=False,
    )
    assert b.dispatch_ready is False


def test_null_ceiling() -> None:
    b = build_midnight_oil_swarm_brief(
        operator_id="op",
        work_minutes=60,
        goals=GOALS,
        price_ceiling_usd=None,
        operator_approved=True,
    )
    assert b.dispatch_ready is False
    assert b.price_ceiling_usd is None


def test_zero_ceiling_dry() -> None:
    b = build_midnight_oil_swarm_brief(
        operator_id="op",
        work_minutes=30,
        goals=[GOALS[0]],
        price_ceiling_usd=0,
        operator_approved=True,
    )
    assert b.dispatch_ready is True
    assert b.live_execution_authorized is False


def test_strict_bool() -> None:
    with pytest.raises(MidnightOilSwarmBriefError, match="operator_approved"):
        build_midnight_oil_swarm_brief(
            operator_id="op",
            work_minutes=10,
            goals=GOALS,
            price_ceiling_usd=1,
            operator_approved="true",  # type: ignore[arg-type]
        )


def test_rejects_empty_goals() -> None:
    with pytest.raises(MidnightOilSwarmBriefError, match="goals"):
        build_midnight_oil_swarm_brief(
            operator_id="op",
            work_minutes=10,
            goals=[],
            price_ceiling_usd=1,
            operator_approved=True,
        )
