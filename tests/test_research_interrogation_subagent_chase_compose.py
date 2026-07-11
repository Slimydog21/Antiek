"""Pure tests for research interrogation subagent chase compose."""

from __future__ import annotations

import pytest

from substrate.research_interrogation_subagent_chase_compose import (
    ResearchInterrogationSubagentChaseComposeError,
    compose_research_interrogation_subagent_chase,
    format_research_interrogation_subagent_chase_summary,
)


def test_single_question_ready():
    c = compose_research_interrogation_subagent_chase(
        session_id="sess-1",
        parent_asset_id="paper-1",
        questions=[{"question_id": "q1", "body": "What is the scaling law?"}],
        chase_mode="single_question",
        would_exceed=False,
        source_families=["arxiv"],
        selected_model_id="gpt-5",
        operator_ack=True,
    )
    assert c.chase_ready is True
    assert c.slot_count == 1
    assert c.planned_slots[0].live_dispatched is False
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.to_dict()["live_dispatched"] is False
    s = format_research_interrogation_subagent_chase_summary(c)
    assert "live_dispatched=false" in s
    assert "pack_dispatched=false" in s
    assert "record_persisted=false" in s
    assert "prompts_injected=false" in s


def test_swarm_fanout_priority_order():
    c = compose_research_interrogation_subagent_chase(
        session_id="sess-2",
        parent_asset_id="paper-1",
        questions=[
            {"question_id": "q-low", "body": "minor", "priority": 1},
            {"question_id": "q-high", "body": "critical gap", "priority": 10},
        ],
        chase_mode="swarm_fanout",
        would_exceed=False,
        operator_ack=True,
    )
    assert c.chase_ready is True
    assert c.slot_count == 2
    assert c.planned_slots[0].question_id == "q-high"


def test_collective_merge_after_intent_only():
    c = compose_research_interrogation_subagent_chase(
        session_id="sess-3",
        parent_asset_id="paper-1",
        questions=[
            {"question_id": "q1", "body": "A?"},
            {"question_id": "q2", "body": "B?"},
        ],
        chase_mode="collective_merge_after",
        would_exceed=False,
        mark_for_twin_record=True,
        operator_ack=True,
    )
    assert c.chase_ready is True
    assert c.pack_dispatched is False
    assert c.mark_for_twin_record is True
    assert c.record_persisted is False


def test_would_exceed_blocks():
    c = compose_research_interrogation_subagent_chase(
        session_id="s",
        parent_asset_id="p",
        questions=[{"question_id": "q1", "body": "x"}],
        chase_mode="single_question",
        would_exceed=True,
        operator_ack=True,
    )
    assert c.budget_ready is False
    assert c.chase_ready is False
    assert c.live_dispatched is False


def test_ack_false():
    c = compose_research_interrogation_subagent_chase(
        session_id="s",
        parent_asset_id="p",
        questions=[{"question_id": "q1", "body": "x"}],
        chase_mode="single_question",
        would_exceed=False,
        operator_ack=False,
    )
    assert c.chase_ready is False


def test_rejects_single_with_many():
    with pytest.raises(
        ResearchInterrogationSubagentChaseComposeError, match="exactly 1"
    ):
        compose_research_interrogation_subagent_chase(
            session_id="s",
            parent_asset_id="p",
            questions=[
                {"question_id": "q1", "body": "a"},
                {"question_id": "q2", "body": "b"},
            ],
            chase_mode="single_question",
            would_exceed=False,
            operator_ack=True,
        )


def test_rejects_secret_model():
    with pytest.raises(
        ResearchInterrogationSubagentChaseComposeError, match="secret"
    ):
        compose_research_interrogation_subagent_chase(
            session_id="s",
            parent_asset_id="p",
            questions=[{"question_id": "q1", "body": "x"}],
            chase_mode="single_question",
            would_exceed=False,
            selected_model_id="sk-secret-key",
            operator_ack=True,
        )


def test_rejects_empty_questions():
    with pytest.raises(
        ResearchInterrogationSubagentChaseComposeError, match="non-empty"
    ):
        compose_research_interrogation_subagent_chase(
            session_id="s",
            parent_asset_id="p",
            questions=[],
            chase_mode="swarm_fanout",
            would_exceed=False,
            operator_ack=True,
        )
