"""Pure tests for competition quality + interrogation loop compose."""

from __future__ import annotations

from substrate.competition_quality_interrogation_loop_compose import (
    compose_competition_quality_interrogation_loop,
    format_competition_quality_interrogation_loop_summary,
)

MODELS = [
    {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4},
    {"model_id": "grok-4.5", "projected_cost_usd_high": 0.2},
]
QUESTIONS = [
    {
        "question_id": "q1",
        "body": "How do competitors structure multi-hop citations?",
        "priority": 2,
    },
    {
        "question_id": "q2",
        "body": "Where is Antiek ahead on HTML-native research?",
        "priority": 1,
    },
]
DECISIONS = [
    {
        "competitor": "Perplexity",
        "area": "citation_grounding",
        "decision_summary": "Inline citations with source cards",
        "antiek_status": "parity",
    },
    {
        "competitor": "OpenAI DR",
        "area": "multi_agent_orchestration",
        "decision_summary": "Planner + browser agents",
        "antiek_status": "behind",
        "residual": "strengthen collective floating cohesive pack",
    },
]
CITATIONS = [
    {
        "citation_id": "c1",
        "family": "arxiv",
        "title": "Scaling Laws for Neural Language Models",
        "external_id": "arxiv:2001.08361",
    },
    {
        "citation_id": "c2",
        "family": "substack",
        "title": "Deep research essay",
    },
]


def test_session_ready():
    c = compose_competition_quality_interrogation_loop(
        session_id="sess-1",
        parent_asset_id="asset-1",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv", "substack"],
        citations=CITATIONS,
        quality_overall=0.85,
        quality_floor=0.7,
        would_exceed=False,
        questions=QUESTIONS,
        chase_mode="swarm_fanout",
        prior_records=[
            {
                "record_id": "i1",
                "kind": "insight",
                "body": "HTML-native doctrine is a differentiator",
            }
        ],
        user_prompt="Chase competitor gaps with arxiv/substack rigor",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=30,
        spent_usd=4,
        projected_cost_usd_high=0.4,
        source_families=["arxiv", "substack"],
        operator_ack=True,
    )
    assert c.quality_pack.pack_ready is True
    assert c.interrogation.loop_ready is True
    assert c.session_ready is True
    assert c.live_dispatch_authorized is False
    assert c.live_dispatched is False
    assert c.remote_fetched is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert "remote_fetched=false" in format_competition_quality_interrogation_loop_summary(
        c
    )
    assert c.to_dict()["live_dispatch_authorized"] is False


def test_budget_blocks():
    c = compose_competition_quality_interrogation_loop(
        session_id="sess-2",
        parent_asset_id="a",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv"],
        citations=[CITATIONS[0]],
        quality_overall=0.9,
        would_exceed=True,
        questions=[QUESTIONS[0]],
        chase_mode="single_question",
        user_prompt="Chase",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=1,
        spent_usd=0.9,
        projected_cost_usd_high=0.5,
        operator_ack=True,
    )
    assert c.session_ready is False
    assert c.live_dispatch_authorized is False


def test_low_quality():
    c = compose_competition_quality_interrogation_loop(
        session_id="sess-3",
        parent_asset_id="a",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv"],
        citations=[CITATIONS[0]],
        quality_overall=0.2,
        quality_floor=0.7,
        would_exceed=False,
        questions=QUESTIONS,
        chase_mode="swarm_fanout",
        user_prompt="Go",
        selected_model_id="grok-4.5",
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=1,
        operator_ack=True,
    )
    assert c.quality_pack.pack_ready is False
    assert c.session_ready is False
    assert c.remote_fetched is False


def test_ack_false():
    c = compose_competition_quality_interrogation_loop(
        session_id="sess-4",
        parent_asset_id="a",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv", "substack"],
        citations=CITATIONS,
        quality_overall=0.9,
        would_exceed=False,
        questions=QUESTIONS,
        chase_mode="swarm_fanout",
        user_prompt="Interrogate",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=1,
        operator_ack=False,
    )
    assert c.session_ready is False
    assert c.live_dispatched is False
    assert c.prompts_injected is False
