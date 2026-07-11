"""Pure tests for MO time goals price entry compose."""

from __future__ import annotations

import pytest

from substrate.midnight_oil_time_goals_price_entry_compose import (
    MidnightOilTimeGoalsPriceEntryComposeError,
    compose_midnight_oil_time_goals_price_entry,
)


def test_entry_ready():
    c = compose_midnight_oil_time_goals_price_entry(
        operator_id="op-1",
        work_minutes=120,
        goals=[
            {"goal_id": "g1", "title": "Survey arxiv"},
            {"goal_id": "g2", "title": "Draft notes"},
        ],
        usd_per_hour=15,
        approved_ceiling_usd=40,
        operator_ack=True,
    )
    assert c.entry_ready is True
    assert c.goal_count == 2
    assert c.recommend.recommended_ceiling_usd is not None
    assert c.live_execution_authorized is False
    assert c.to_dict()["live_execution_authorized"] is False


def test_not_ready_without_approved():
    c = compose_midnight_oil_time_goals_price_entry(
        operator_id="op",
        work_minutes=60,
        goals=[{"goal_id": "g1", "title": "T"}],
        usd_per_hour=10,
        approved_ceiling_usd=None,
        operator_ack=True,
    )
    assert c.entry_ready is False
    assert c.live_execution_authorized is False


def test_rejects_empty_goals():
    with pytest.raises(MidnightOilTimeGoalsPriceEntryComposeError, match="goals"):
        compose_midnight_oil_time_goals_price_entry(
            operator_id="op",
            work_minutes=30,
            goals=[],
            operator_ack=True,
        )
