"""Hermetic tests for Midnight Oil launch package compose."""

from __future__ import annotations

import pytest

from substrate.midnight_oil_launch_package_compose import (
    MidnightOilLaunchPackageComposeError,
    compose_midnight_oil_launch_package,
    recommend_midnight_oil_price_ceiling,
)

GOALS = [
    {"goal_id": "g1", "statement": "Map arxiv scaling", "priority": 2},
    {"goal_id": "g2", "statement": "Substack contrast", "priority": 1},
]


def test_recommend_null_when_rate_unknown() -> None:
    r = recommend_midnight_oil_price_ceiling(
        work_minutes=60, goal_count=2, usd_per_hour=None
    )
    assert r.recommended_ceiling_usd is None
    assert any("no invent" in n for n in r.notes)


def test_recommend_from_rate() -> None:
    r = recommend_midnight_oil_price_ceiling(
        work_minutes=60, goal_count=1, usd_per_hour=10
    )
    assert r.recommended_ceiling_usd == 10.0
    assert r.work_hours == 1.0


def test_package_ready_without_live_exec() -> None:
    p = compose_midnight_oil_launch_package(
        operator_id="op-1",
        work_minutes=60,
        goals=GOALS,
        price_ceiling_usd=15,
        usd_per_hour=10,
        operator_approved=True,
        unattended_ack=True,
        spend_consent=True,
    )
    assert p.live_execution_authorized is False
    assert p.to_dict()["live_execution_authorized"] is False
    assert p.brief.live_execution_authorized is False
    assert p.readiness.live_execution_authorized is False
    assert p.package_ready is True
    assert p.authority == "midnight_oil_launch_package_compose_advisory"


def test_not_ready_without_ack() -> None:
    p = compose_midnight_oil_launch_package(
        operator_id="op-1",
        work_minutes=60,
        goals=GOALS,
        price_ceiling_usd=10,
        recommended_ceiling_usd=8,
        operator_approved=True,
        unattended_ack=False,
        spend_consent=True,
    )
    assert p.package_ready is False
    assert p.live_execution_authorized is False


def test_zero_ceiling_dry() -> None:
    p = compose_midnight_oil_launch_package(
        operator_id="op-1",
        work_minutes=30,
        goals=[GOALS[0]],
        price_ceiling_usd=0,
        recommended_ceiling_usd=0,
        operator_approved=True,
        unattended_ack=True,
        spend_consent=False,
    )
    assert p.package_ready is True
    assert p.live_execution_authorized is False


def test_rejects_empty_goals() -> None:
    with pytest.raises(MidnightOilLaunchPackageComposeError, match="goals"):
        compose_midnight_oil_launch_package(
            operator_id="op-1",
            work_minutes=60,
            goals=[],
            price_ceiling_usd=1,
            operator_approved=False,
            unattended_ack=False,
            spend_consent=False,
        )
