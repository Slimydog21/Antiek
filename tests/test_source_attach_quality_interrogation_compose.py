"""Pure tests for source attach quality interrogation compose."""

from __future__ import annotations

from substrate.source_attach_quality_interrogation_compose import (
    compose_source_attach_quality_interrogation,
    format_source_attach_quality_interrogation_summary,
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


def test_source_quality_interrogation_ready():
    c = compose_source_attach_quality_interrogation(
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
    assert c.source_quality.pack_ready is True
    assert c.interrogation.loop_ready is True
    assert c.pack_ready is True
    assert c.remote_fetched is False
    assert c.pdf_view_authorized is False
    assert c.live_dispatch_authorized is False
    assert c.live_dispatched is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.store_mutated is False
    # chase inherits source families
    slots = c.interrogation.chase.planned_slots
    assert slots
    families = getattr(slots[0], "source_families", None) or slots[0].get(
        "source_families"
    ) if isinstance(slots[0], dict) else None
    # planned_slots may be dataclasses
    if families is None and hasattr(slots[0], "source_families"):
        families = slots[0].source_families
    assert families is not None
    assert "arxiv" in list(families)
    assert c.authority == (
        "source_attach_quality_interrogation_compose_advisory"
    )
    assert "remote_fetched=false" in format_source_attach_quality_interrogation_summary(
        c
    )
    assert c.to_dict()["live_dispatched"] is False


def test_budget_would_exceed_blocks_pack_ready():
    c = compose_source_attach_quality_interrogation(
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
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.remote_fetched is False


def test_low_quality_blocks_source_pack():
    c = compose_source_attach_quality_interrogation(
        session_id="sess-3",
        parent_asset_id="a",
        requested_families=["arxiv"],
        sources=[SOURCES[0]],
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
    assert c.source_quality.pack_ready is False
    assert c.pack_ready is False
    assert c.pdf_view_authorized is False


def test_operator_ack_false_blocks():
    c = compose_source_attach_quality_interrogation(
        session_id="sess-4",
        parent_asset_id="a",
        requested_families=["arxiv", "substack"],
        sources=SOURCES,
        quality_overall=0.9,
        would_exceed=False,
        questions=QUESTIONS,
        chase_mode="swarm_fanout",
        user_prompt="Interrogate sources",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=1,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.prompts_injected is False
    assert c.record_persisted is False
