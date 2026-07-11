"""Pure tests for source attach quality interrogation twin compose."""

from __future__ import annotations

from substrate.source_attach_quality_interrogation_twin_compose import (
    compose_source_attach_quality_interrogation_twin,
    format_source_attach_quality_interrogation_twin_summary,
)

MODELS = [
    {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4},
    {"model_id": "grok-4.5", "projected_cost_usd_high": 0.2},
]
SOURCES = [
    {
        "source_id": "arx-1",
        "family": "arxiv",
        "title": "Scaling Laws for Neural Language Models",
        "external_id": "arxiv:2001.08361",
        "html_fragment": "<article>abstract…</article>",
    },
    {
        "source_id": "sub-1",
        "family": "substack",
        "title": "Deep research essay",
        "html_fragment": "<article>essay…</article>",
    },
]
QUESTIONS = [
    {
        "question_id": "q1",
        "body": "How do these sources ground multi-hop claims?",
        "priority": 2,
    },
    {
        "question_id": "q2",
        "body": "Where do they disagree with Antiek doctrine?",
        "priority": 1,
    },
]


def test_source_twin_feed_ready():
    c = compose_source_attach_quality_interrogation_twin(
        session_id="sess-1",
        parent_asset_id="asset-1",
        requested_families=["arxiv", "substack"],
        sources=SOURCES,
        quality_overall=0.88,
        quality_floor=0.7,
        would_exceed=False,
        questions=QUESTIONS,
        chase_mode="swarm_fanout",
        user_prompt="Chase with arxiv/substack attached",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=30,
        spent_usd=4,
        projected_cost_usd_high=0.4,
        operator_ack=True,
    )
    assert c.source_interrogation.pack_ready is True
    assert c.twin_feed.feed_ready is True
    assert c.pack_ready is True
    assert c.twin_feed.finding_count == 4
    assert c.remote_fetched is False
    assert c.twin_written is False
    assert c.live_dispatched is False
    assert c.pdf_view_authorized is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.store_mutated is False
    assert (
        c.authority
        == "source_attach_quality_interrogation_twin_compose_advisory"
    )
    assert "twin_written=false" in format_source_attach_quality_interrogation_twin_summary(
        c
    )
    assert c.to_dict()["twin_written"] is False


def test_budget_blocks_pack_ready():
    c = compose_source_attach_quality_interrogation_twin(
        session_id="sess-2",
        parent_asset_id="a",
        requested_families=["arxiv"],
        sources=[SOURCES[0]],
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
    assert c.source_interrogation.pack_ready is False
    assert c.pack_ready is False
    assert c.twin_written is False


def test_operator_ack_false_blocks():
    c = compose_source_attach_quality_interrogation_twin(
        session_id="sess-3",
        parent_asset_id="a",
        requested_families=["arxiv", "substack"],
        sources=SOURCES,
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
    assert c.pack_ready is False
    assert c.prompts_injected is False
    assert c.twin_written is False


def test_caller_twin_findings_override():
    c = compose_source_attach_quality_interrogation_twin(
        session_id="sess-4",
        parent_asset_id="asset-1",
        requested_families=["arxiv"],
        sources=[SOURCES[0]],
        quality_overall=0.9,
        would_exceed=False,
        questions=[QUESTIONS[0]],
        chase_mode="single_question",
        user_prompt="Chase",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=1,
        operator_ack=True,
        twin_findings=[
            {
                "source_id": "custom-1",
                "body": "Caller insight from completed chase",
                "kind": "insight",
            }
        ],
        analysis_excerpt="Provisional analysis",
    )
    assert c.twin_feed.finding_count == 1
    assert c.twin_feed.insight_count == 1
    assert c.pack_ready is True
    assert c.remote_fetched is False
