"""Pure tests for chase completion collective analysis compose."""

from __future__ import annotations

import pytest

from substrate.chase_completion_collective_analysis_compose import (
    ChaseCompletionCollectiveAnalysisComposeError,
    compose_chase_completion_collective_analysis,
    format_chase_completion_collective_analysis_summary,
)

SLOTS = [
    {
        "slot_id": "chase_1_q1",
        "question_id": "q1",
        "parent_asset_id": "paper-1",
        "status": "completed",
        "findings": ["claim A supported by arxiv:123"],
    },
    {
        "slot_id": "chase_2_q2",
        "question_id": "q2",
        "parent_asset_id": "paper-1",
        "status": "completed",
        "findings": ["gap: missing ablation"],
    },
]


def test_draft_ready():
    c = compose_chase_completion_collective_analysis(
        session_id="sess-1",
        parent_asset_id="paper-1",
        slots=SLOTS,
        kind="draft_analysis",
        operator_ack=False,
    )
    assert c.analysis_ready is True
    assert c.analysis_written is False
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert len(c.analysis.findings) == 2
    s = format_chase_completion_collective_analysis_summary(c)
    assert "analysis_written=false" in s
    assert c.to_dict()["analysis_written"] is False


def test_full_ready():
    c = compose_chase_completion_collective_analysis(
        session_id="sess-1",
        parent_asset_id="paper-1",
        slots=SLOTS,
        kind="full_analysis",
        operator_ack=True,
    )
    assert c.analysis_ready is True
    assert c.completed_slot_count == 2
    assert c.analysis_written is False


def test_full_open_throws():
    with pytest.raises(
        ChaseCompletionCollectiveAnalysisComposeError, match="completed"
    ):
        compose_chase_completion_collective_analysis(
            session_id="sess-1",
            parent_asset_id="paper-1",
            slots=[
                SLOTS[0],
                {
                    "slot_id": "chase_2_q2",
                    "question_id": "q2",
                    "parent_asset_id": "paper-1",
                    "status": "open",
                },
            ],
            kind="full_analysis",
            operator_ack=True,
        )


def test_rejects_one_slot():
    with pytest.raises(
        ChaseCompletionCollectiveAnalysisComposeError, match="at least 2"
    ):
        compose_chase_completion_collective_analysis(
            session_id="s",
            parent_asset_id="p",
            slots=[SLOTS[0]],
            kind="draft_analysis",
            operator_ack=False,
        )


def test_cross_parent():
    with pytest.raises(
        ChaseCompletionCollectiveAnalysisComposeError, match="parent_asset_id"
    ):
        compose_chase_completion_collective_analysis(
            session_id="s",
            parent_asset_id="paper-1",
            slots=[
                SLOTS[0],
                {
                    "slot_id": "x",
                    "question_id": "q2",
                    "parent_asset_id": "other",
                    "status": "completed",
                },
            ],
            kind="draft_analysis",
            operator_ack=False,
        )


def test_skips_closed():
    c = compose_chase_completion_collective_analysis(
        session_id="s",
        parent_asset_id="paper-1",
        slots=[
            SLOTS[0],
            SLOTS[1],
            {
                "slot_id": "closed-1",
                "question_id": "q3",
                "parent_asset_id": "paper-1",
                "status": "closed",
            },
        ],
        kind="draft_analysis",
        operator_ack=False,
    )
    assert "closed-1" not in c.selected_slot_ids
    assert len(c.selected_slot_ids) == 2
