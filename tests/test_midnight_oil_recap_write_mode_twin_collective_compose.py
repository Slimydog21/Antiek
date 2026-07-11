"""Pure tests for midnight oil recap → write twin collective compose."""

from __future__ import annotations

from substrate.midnight_oil_recap_write_mode_twin_collective_compose import (
    compose_midnight_oil_recap_write_mode_twin_collective,
    format_midnight_oil_recap_write_mode_twin_collective_summary,
)

GOALS = [
    {
        "goal_id": "g1",
        "title": "Survey arxiv scaling laws",
        "status": "done",
        "notes": "Found key papers",
    },
    {
        "goal_id": "g2",
        "title": "Synthesize substack claims",
        "status": "done",
        "notes": "Draft synthesis",
    },
    {
        "goal_id": "g3",
        "title": "Open counter-claims",
        "status": "pending",
    },
]


def test_recap_write_pack_ready():
    c = compose_midnight_oil_recap_write_mode_twin_collective(
        run_id="run-1",
        operator_id="op-1",
        work_minutes_planned=120,
        work_minutes_actual=115,
        goals=GOALS,
        price_ceiling_usd=40,
        spend_usd=28,
        artifact_ids=["art-1"],
        operator_ack=True,
        session_id="sess-1",
        draft_id="draft-1",
        parent_asset_id="asset-1",
    )
    assert c.recap.recap_ready is True
    assert c.write_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_execution_authorized is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.merge_executed is False
    assert c.store_mutated is False
    assert (
        c.authority
        == "midnight_oil_recap_write_mode_twin_collective_compose_advisory"
    )
    assert "live_execution_authorized=false" in format_midnight_oil_recap_write_mode_twin_collective_summary(
        c
    )
    assert c.to_dict()["draft_written"] is False


def test_blocks_without_operator_ack():
    c = compose_midnight_oil_recap_write_mode_twin_collective(
        run_id="run-2",
        operator_id="op-1",
        work_minutes_planned=60,
        work_minutes_actual=50,
        goals=GOALS,
        price_ceiling_usd=20,
        spend_usd=10,
        operator_ack=False,
        session_id="s",
        draft_id="d",
        parent_asset_id="a",
    )
    assert c.pack_ready is False
    assert c.live_execution_authorized is False


def test_blocks_when_no_progress_on_recap():
    c = compose_midnight_oil_recap_write_mode_twin_collective(
        run_id="run-3",
        operator_id="op-1",
        work_minutes_planned=60,
        work_minutes_actual=0,
        goals=[{"goal_id": "g1", "title": "T", "status": "pending"}],
        price_ceiling_usd=20,
        spend_usd=0,
        operator_ack=True,
        session_id="s",
        draft_id="d",
        parent_asset_id="a",
    )
    assert c.recap.recap_ready is False
    assert c.pack_ready is False


def test_caller_twin_slices_override():
    c = compose_midnight_oil_recap_write_mode_twin_collective(
        run_id="run-4",
        operator_id="op-1",
        work_minutes_planned=90,
        work_minutes_actual=80,
        goals=GOALS,
        price_ceiling_usd=30,
        spend_usd=20,
        operator_ack=True,
        session_id="s",
        draft_id="d",
        parent_asset_id="a",
        twin_slices=[
            {
                "parent_asset_id": "a",
                "insights": ["Caller insight A", "Caller insight B"],
                "questions": ["Q1?"],
            }
        ],
        chase_slots=[
            {
                "slot_id": "s1",
                "question_id": "q1",
                "parent_asset_id": "a",
                "status": "completed",
                "findings": ["f1"],
            },
            {
                "slot_id": "s2",
                "question_id": "q2",
                "parent_asset_id": "a",
                "status": "completed",
                "findings": ["f2"],
            },
        ],
        analysis_kind="full_analysis",
    )
    assert c.write_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.analysis_written is False
