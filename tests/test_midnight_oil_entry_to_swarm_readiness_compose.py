"""Pure tests for MO entry → swarm readiness compose."""

from __future__ import annotations

from substrate.midnight_oil_entry_to_swarm_readiness_compose import (
    compose_midnight_oil_entry_to_swarm_readiness,
    format_midnight_oil_entry_to_swarm_readiness_summary,
)


def test_package_ready():
    c = compose_midnight_oil_entry_to_swarm_readiness(
        operator_id="op-1",
        work_minutes=120,
        goals=[
            {"goal_id": "g1", "title": "Survey arxiv"},
            {"goal_id": "g2", "title": "Draft notes"},
        ],
        usd_per_hour=15,
        approved_ceiling_usd=40,
        operator_ack=True,
        brief_dispatch_ready=True,
        unattended_ack=True,
        spend_consent=True,
    )
    assert c.entry.entry_ready is True
    assert c.readiness.unattended_ready is True
    assert c.package_ready is True
    assert c.live_execution_authorized is False
    assert c.to_dict()["live_execution_authorized"] is False
    assert "live_execution_authorized=false" in format_midnight_oil_entry_to_swarm_readiness_summary(
        c
    )


def test_not_ready_without_unattended():
    c = compose_midnight_oil_entry_to_swarm_readiness(
        operator_id="op-1",
        work_minutes=60,
        goals=[{"goal_id": "g1", "title": "T"}],
        usd_per_hour=10,
        approved_ceiling_usd=20,
        operator_ack=True,
        brief_dispatch_ready=True,
        unattended_ack=False,
        spend_consent=True,
    )
    assert c.package_ready is False
    assert c.live_execution_authorized is False


def test_not_ready_without_ceiling():
    c = compose_midnight_oil_entry_to_swarm_readiness(
        operator_id="op-1",
        work_minutes=60,
        goals=[{"goal_id": "g1", "title": "T"}],
        usd_per_hour=10,
        approved_ceiling_usd=None,
        operator_ack=True,
        brief_dispatch_ready=True,
        unattended_ack=True,
        spend_consent=True,
    )
    assert c.entry.entry_ready is False
    assert c.package_ready is False
