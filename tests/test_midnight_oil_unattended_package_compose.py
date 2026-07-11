"""Pure tests for MO unattended package compose."""

from __future__ import annotations

from substrate.midnight_oil_unattended_package_compose import (
    compose_midnight_oil_unattended_package,
    format_midnight_oil_unattended_package_summary,
)


def test_package_ready():
    c = compose_midnight_oil_unattended_package(
        operator_id="op-1",
        work_minutes=120,
        goals=[
            {"goal_id": "g1", "title": "Survey arxiv"},
            {"goal_id": "g2", "title": "Draft notes"},
        ],
        usd_per_hour=15,
        approved_ceiling_usd=40,
        operator_ack=True,
        unattended_ack=True,
        spend_consent=True,
    )
    assert c.entry_readiness.package_ready is True
    assert c.launch.package_ready is True
    assert c.unattended_package_ready is True
    assert c.live_execution_authorized is False
    assert "live_execution_authorized=false" in format_midnight_oil_unattended_package_summary(
        c
    )
    assert c.to_dict()["live_execution_authorized"] is False


def test_blocks_without_unattended():
    c = compose_midnight_oil_unattended_package(
        operator_id="op-1",
        work_minutes=60,
        goals=[{"goal_id": "g1", "title": "T"}],
        usd_per_hour=10,
        approved_ceiling_usd=20,
        operator_ack=True,
        unattended_ack=False,
        spend_consent=True,
    )
    assert c.unattended_package_ready is False
    assert c.live_execution_authorized is False


def test_blocks_without_ceiling():
    c = compose_midnight_oil_unattended_package(
        operator_id="op-1",
        work_minutes=60,
        goals=[{"goal_id": "g1", "title": "T"}],
        usd_per_hour=10,
        approved_ceiling_usd=None,
        operator_ack=True,
        unattended_ack=True,
        spend_consent=True,
    )
    assert c.entry_readiness.entry.entry_ready is False
    assert c.unattended_package_ready is False


def test_blocks_without_consent():
    c = compose_midnight_oil_unattended_package(
        operator_id="op-1",
        work_minutes=60,
        goals=[{"goal_id": "g1", "title": "T"}],
        usd_per_hour=10,
        approved_ceiling_usd=20,
        operator_ack=True,
        unattended_ack=True,
        spend_consent=False,
    )
    assert c.unattended_package_ready is False
