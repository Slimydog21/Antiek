"""Hermetic tests for pure Midnight Oil swarm readiness."""

from __future__ import annotations

import pytest

from substrate.midnight_oil_swarm_readiness import (
    MidnightOilSwarmReadinessError,
    evaluate_midnight_oil_swarm_readiness,
)


def test_unattended_ready_never_live() -> None:
    d = evaluate_midnight_oil_swarm_readiness(
        operator_id="op-1",
        work_minutes=120,
        goal_count=2,
        price_ceiling_usd=5,
        recommended_ceiling_usd=4,
        brief_dispatch_ready=True,
        unattended_ack=True,
        spend_consent=True,
    )
    assert d.unattended_ready is True
    assert d.live_execution_authorized is False
    assert d.to_dict()["live_execution_authorized"] is False


def test_null_ceiling() -> None:
    d = evaluate_midnight_oil_swarm_readiness(
        operator_id="op-1",
        work_minutes=60,
        goal_count=1,
        price_ceiling_usd=None,
        brief_dispatch_ready=True,
        unattended_ack=True,
        spend_consent=True,
    )
    assert d.ceiling_ready is False
    assert d.unattended_ready is False


def test_zero_ceiling_dry() -> None:
    d = evaluate_midnight_oil_swarm_readiness(
        operator_id="op-1",
        work_minutes=30,
        goal_count=1,
        price_ceiling_usd=0,
        brief_dispatch_ready=True,
        unattended_ack=True,
        spend_consent=False,
    )
    assert d.consent_ready is True
    assert d.unattended_ready is True
    assert d.live_execution_authorized is False


def test_positive_needs_consent() -> None:
    d = evaluate_midnight_oil_swarm_readiness(
        operator_id="op-1",
        work_minutes=60,
        goal_count=1,
        price_ceiling_usd=10,
        brief_dispatch_ready=True,
        unattended_ack=True,
        spend_consent=False,
    )
    assert d.consent_ready is False
    assert d.unattended_ready is False


def test_requires_ack() -> None:
    d = evaluate_midnight_oil_swarm_readiness(
        operator_id="op-1",
        work_minutes=60,
        goal_count=1,
        price_ceiling_usd=5,
        brief_dispatch_ready=True,
        unattended_ack=False,
        spend_consent=True,
    )
    assert d.unattended_ready is False


def test_rejects_empty_operator() -> None:
    with pytest.raises(MidnightOilSwarmReadinessError, match="operator_id"):
        evaluate_midnight_oil_swarm_readiness(
            operator_id="  ",
            work_minutes=10,
            goal_count=1,
            price_ceiling_usd=1,
            brief_dispatch_ready=True,
            unattended_ack=True,
            spend_consent=True,
        )
