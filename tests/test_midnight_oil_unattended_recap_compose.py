"""Pure tests for Midnight Oil unattended recap compose."""

from __future__ import annotations

import pytest

from substrate.midnight_oil_unattended_recap_compose import (
    MidnightOilUnattendedRecapComposeError,
    compose_midnight_oil_unattended_recap,
)


def test_recap_ready_no_relaunch():
    c = compose_midnight_oil_unattended_recap(
        run_id="mo-1",
        operator_id="op-1",
        work_minutes_planned=120,
        work_minutes_actual=110,
        price_ceiling_usd=25,
        spend_usd=18.5,
        operator_ack=True,
        artifact_ids=["art-1"],
        goals=[
            {"goal_id": "g1", "title": "Survey arxiv", "status": "done"},
            {"goal_id": "g2", "title": "Draft notes", "status": "blocked"},
            {"goal_id": "g3", "title": "Follow-ups", "status": "pending"},
        ],
    )
    assert c.recap_ready is True
    assert c.goals_done == 1
    assert c.within_ceiling is True
    assert c.live_execution_authorized is False
    assert c.store_mutated is False
    assert c.to_dict()["live_execution_authorized"] is False


def test_unknown_spend_null_ceiling_flag():
    c = compose_midnight_oil_unattended_recap(
        run_id="mo-1",
        operator_id="op",
        work_minutes_planned=60,
        work_minutes_actual=None,
        price_ceiling_usd=10,
        spend_usd=None,
        operator_ack=True,
        goals=[{"goal_id": "g1", "title": "T", "status": "done"}],
    )
    assert c.within_ceiling is None
    assert c.recap_ready is True


def test_not_ready_paths():
    no_ack = compose_midnight_oil_unattended_recap(
        run_id="mo",
        operator_id="op",
        work_minutes_planned=30,
        work_minutes_actual=10,
        price_ceiling_usd=None,
        spend_usd=None,
        operator_ack=False,
        goals=[{"goal_id": "g1", "title": "T", "status": "done"}],
    )
    assert no_ack.recap_ready is False
    no_progress = compose_midnight_oil_unattended_recap(
        run_id="mo",
        operator_id="op",
        work_minutes_planned=30,
        work_minutes_actual=10,
        price_ceiling_usd=None,
        spend_usd=None,
        operator_ack=True,
        goals=[{"goal_id": "g1", "title": "T", "status": "pending"}],
    )
    assert no_progress.recap_ready is False


def test_rejects_empty_goals():
    with pytest.raises(MidnightOilUnattendedRecapComposeError, match="goals"):
        compose_midnight_oil_unattended_recap(
            run_id="mo",
            operator_id="op",
            work_minutes_planned=10,
            work_minutes_actual=None,
            price_ceiling_usd=None,
            spend_usd=None,
            operator_ack=True,
            goals=[],
        )
