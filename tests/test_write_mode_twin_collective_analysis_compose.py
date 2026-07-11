"""Pure tests for write-mode twin collective analysis compose."""

from __future__ import annotations

from substrate.write_mode_twin_collective_analysis_compose import (
    compose_write_mode_twin_collective_analysis,
    format_write_mode_twin_collective_analysis_summary,
)

TWIN_SLICES = [
    {
        "parent_asset_id": "asset-1",
        "insights": ["scaling claim holds in compute-optimal regimes"],
        "questions": ["Where does it break?"],
    },
    {
        "parent_asset_id": "asset-2",
        "insights": ["attention efficiency tradeoffs"],
        "questions": [],
    },
]
CHASE_SLOTS = [
    {
        "slot_id": "s1",
        "question_id": "q1",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "findings": ["finding A from chase"],
        "body": "What evidence supports scaling?",
    },
    {
        "slot_id": "s2",
        "question_id": "q2",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "findings": ["finding B from chase"],
        "body": "Counter-evidence?",
    },
]


def test_draft_analysis_ready():
    c = compose_write_mode_twin_collective_analysis(
        session_id="sess-1",
        draft_id="draft-1",
        parent_asset_id="asset-1",
        twin_slices=TWIN_SLICES,
        base_draft_html="<p>Opening paragraph</p>",
        chase_slots=CHASE_SLOTS,
        analysis_kind="draft_analysis",
        operator_ack=True,
    )
    assert c.twin_draft.draft_ready is True
    assert c.collective_analysis.analysis_ready is True
    assert c.pack_ready is True
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.merge_executed is False
    assert c.store_mutated is False
    assert c.live_dispatched is False
    assert "analysis_written=false" in format_write_mode_twin_collective_analysis_summary(
        c
    )
    assert c.to_dict()["draft_written"] is False


def test_full_analysis():
    c = compose_write_mode_twin_collective_analysis(
        session_id="sess-2",
        draft_id="draft-2",
        parent_asset_id="asset-1",
        twin_slices=TWIN_SLICES,
        chase_slots=CHASE_SLOTS,
        analysis_kind="full_analysis",
        operator_ack=True,
    )
    assert c.collective_analysis.analysis.kind == "full_analysis"
    assert c.pack_ready is True
    assert c.analysis_written is False
    assert c.merge_executed is False


def test_ack_false():
    c = compose_write_mode_twin_collective_analysis(
        session_id="sess-3",
        draft_id="d",
        parent_asset_id="asset-1",
        twin_slices=TWIN_SLICES,
        chase_slots=CHASE_SLOTS,
        analysis_kind="draft_analysis",
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.live_dispatched is False


def test_require_both_false():
    c = compose_write_mode_twin_collective_analysis(
        session_id="sess-4",
        draft_id="d",
        parent_asset_id="asset-1",
        twin_slices=[
            {
                "parent_asset_id": "asset-1",
                "insights": ["only one insight"],
                "questions": [],
            }
        ],
        chase_slots=CHASE_SLOTS,
        analysis_kind="draft_analysis",
        operator_ack=True,
        require_both=False,
    )
    assert c.collective_analysis.analysis_ready is True
    assert c.pack_ready is True
    assert c.merge_executed is False
