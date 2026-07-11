"""Pure tests for research workstation interrogation loop compose."""

from __future__ import annotations

from substrate.research_workstation_interrogation_loop_compose import (
    compose_research_workstation_interrogation_loop,
    format_research_workstation_interrogation_loop_summary,
)

MODELS = [
    {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4},
    {"model_id": "grok-4.5", "projected_cost_usd_high": 0.2},
]
QUESTIONS = [
    {
        "question_id": "q1",
        "body": "What evidence supports the scaling claim?",
        "priority": 2,
    },
    {
        "question_id": "q2",
        "body": "Where do scaling laws break?",
        "priority": 1,
    },
]


def test_loop_ready():
    c = compose_research_workstation_interrogation_loop(
        session_id="sess-1",
        parent_asset_id="asset-1",
        questions=QUESTIONS,
        chase_mode="swarm_fanout",
        prior_records=[
            {
                "record_id": "i1",
                "kind": "insight",
                "body": "Prior note: compute-optimal regimes matter",
            }
        ],
        user_prompt="Interrogate the paper and chase open questions",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=25,
        spent_usd=3,
        projected_cost_usd_high=0.4,
        would_exceed=False,
        source_families=["arxiv", "substack"],
        operator_ack=True,
    )
    assert c.chase.chase_ready is True
    assert c.chase.slot_count == 2
    assert c.prompt_pack.pack_ready is True
    assert c.loop_ready is True
    assert c.live_dispatched is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.live_router_authorized is False
    assert "live_dispatched=false" in format_research_workstation_interrogation_loop_summary(
        c
    )
    assert c.to_dict()["live_dispatched"] is False


def test_budget_blocks():
    c = compose_research_workstation_interrogation_loop(
        session_id="sess-2",
        parent_asset_id="a",
        questions=[QUESTIONS[0]],
        chase_mode="single_question",
        user_prompt="Chase",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=1,
        spent_usd=0.9,
        projected_cost_usd_high=0.5,
        would_exceed=True,
        operator_ack=True,
    )
    assert c.chase.budget_ready is False
    assert c.chase.chase_ready is False
    assert c.loop_ready is False
    assert c.live_dispatched is False


def test_ack_false():
    c = compose_research_workstation_interrogation_loop(
        session_id="sess-3",
        parent_asset_id="a",
        questions=QUESTIONS,
        chase_mode="swarm_fanout",
        user_prompt="Go",
        selected_model_id="grok-4.5",
        models=MODELS,
        daily_cap_usd=10,
        spent_usd=1,
        would_exceed=False,
        operator_ack=False,
    )
    assert c.loop_ready is False
    assert c.prompts_injected is False
    assert c.record_persisted is False


def test_collective_mode():
    c = compose_research_workstation_interrogation_loop(
        session_id="sess-4",
        parent_asset_id="a",
        questions=QUESTIONS,
        chase_mode="collective_merge_after",
        user_prompt="Merge chases after completion",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=2,
        would_exceed=False,
        operator_ack=True,
    )
    assert c.chase.chase_mode == "collective_merge_after"
    assert c.pack_dispatched is False
    assert c.live_dispatched is False
