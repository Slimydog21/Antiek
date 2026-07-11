"""Pure tests for chase → twin → analysis loop compose."""

from __future__ import annotations

from substrate.chase_twin_analysis_loop_compose import (
    compose_chase_twin_analysis_loop,
    format_chase_twin_analysis_loop_summary,
)


def test_loop_ready():
    c = compose_chase_twin_analysis_loop(
        session_id="sess-1",
        parent_asset_id="paper-1",
        questions=[
            {"question_id": "q1", "body": "What is the core claim?", "priority": 2},
            {"question_id": "q2", "body": "What evidence is missing?", "priority": 1},
        ],
        chase_mode="swarm_fanout",
        would_exceed=False,
        source_families=["arxiv"],
        operator_ack=True,
        analysis_kind="draft_analysis",
        analysis_excerpt="draft collective scaffold",
        completed_slots=[
            {
                "slot_id": "chase_1_q1",
                "question_id": "q1",
                "parent_asset_id": "paper-1",
                "status": "completed",
                "findings": ["claim A supported"],
                "body": "What is the core claim?",
            },
            {
                "slot_id": "chase_2_q2",
                "question_id": "q2",
                "parent_asset_id": "paper-1",
                "status": "completed",
                "findings": ["gap: missing ablation"],
                "body": "What evidence is missing?",
            },
        ],
        mark_for_prompt_context=True,
    )
    assert c.chase.chase_ready is True
    assert c.twin_feed is not None and c.twin_feed.feed_ready is True
    assert c.analysis is not None and c.analysis.analysis_ready is True
    assert c.loop_ready is True
    assert c.live_dispatched is False
    assert c.twin_written is False
    assert c.analysis_written is False
    assert c.record_persisted is False
    assert c.pack_dispatched is False
    s = format_chase_twin_analysis_loop_summary(c)
    assert "live_dispatched=false" in s
    assert c.to_dict()["analysis_written"] is False


def test_one_slot_not_loop_ready():
    c = compose_chase_twin_analysis_loop(
        session_id="s",
        parent_asset_id="p",
        questions=[{"question_id": "q1", "body": "Only one?"}],
        chase_mode="single_question",
        would_exceed=False,
        operator_ack=True,
        analysis_kind="draft_analysis",
        completed_slots=[
            {
                "slot_id": "only",
                "question_id": "q1",
                "parent_asset_id": "p",
                "status": "completed",
                "findings": ["one finding"],
            }
        ],
    )
    assert c.chase.chase_ready is True
    assert c.analysis is None
    assert c.loop_ready is False


def test_would_exceed_blocks():
    c = compose_chase_twin_analysis_loop(
        session_id="s",
        parent_asset_id="p",
        questions=[
            {"question_id": "q1", "body": "A?"},
            {"question_id": "q2", "body": "B?"},
        ],
        chase_mode="swarm_fanout",
        would_exceed=True,
        operator_ack=True,
        analysis_kind="draft_analysis",
        completed_slots=[
            {
                "slot_id": "a",
                "question_id": "q1",
                "parent_asset_id": "p",
                "status": "completed",
                "findings": ["x"],
            },
            {
                "slot_id": "b",
                "question_id": "q2",
                "parent_asset_id": "p",
                "status": "completed",
                "findings": ["y"],
            },
        ],
    )
    assert c.chase.chase_ready is False
    assert c.loop_ready is False
    assert c.live_dispatched is False


def test_ack_false():
    c = compose_chase_twin_analysis_loop(
        session_id="s",
        parent_asset_id="p",
        questions=[
            {"question_id": "q1", "body": "A?"},
            {"question_id": "q2", "body": "B?"},
        ],
        chase_mode="swarm_fanout",
        would_exceed=False,
        operator_ack=False,
        analysis_kind="draft_analysis",
        completed_slots=[
            {
                "slot_id": "a",
                "question_id": "q1",
                "parent_asset_id": "p",
                "status": "completed",
                "findings": ["x"],
            },
            {
                "slot_id": "b",
                "question_id": "q2",
                "parent_asset_id": "p",
                "status": "completed",
                "findings": ["y"],
            },
        ],
    )
    assert c.loop_ready is False
