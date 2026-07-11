"""Pure tests for highlight source attach quality interrogation compose."""

from __future__ import annotations

import pytest

from substrate.highlight_source_attach_quality_interrogation_compose import (
    HighlightSourceAttachQualityInterrogationComposeError,
    compose_highlight_source_attach_quality_interrogation,
    format_highlight_source_attach_quality_interrogation_summary,
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
        "body": "How does this highlight relate to scaling laws?",
        "priority": 2,
    },
    {
        "question_id": "q2",
        "body": "What counter-evidence exists?",
        "priority": 1,
    },
]


def test_highlight_source_ready():
    c = compose_highlight_source_attach_quality_interrogation(
        parent_asset_id="book-1",
        highlight="power-law scaling of loss with compute",
        gated=False,
        preferred_view_mode="floating",
        would_exceed=False,
        selected_model_id="gpt-5.5",
        operator_ack=True,
        session_id="sess-1",
        requested_families=["arxiv", "substack"],
        sources=SOURCES,
        quality_overall=0.88,
        quality_floor=0.7,
        questions=QUESTIONS,
        chase_mode="swarm_fanout",
        models=MODELS,
        daily_cap_usd=30,
        spent_usd=4,
        projected_cost_usd_high=0.4,
    )
    assert c.highlight_launch.launch_ready is True
    assert c.source_interrogation.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.remote_fetched is False
    assert c.pdf_view_authorized is False
    assert "live_dispatched=false" in format_highlight_source_attach_quality_interrogation_summary(
        c
    )


def test_gated_fails_closed():
    with pytest.raises(
        HighlightSourceAttachQualityInterrogationComposeError, match="gated"
    ):
        compose_highlight_source_attach_quality_interrogation(
            parent_asset_id="book-1",
            highlight="secret gated passage",
            gated=True,
            would_exceed=False,
            operator_ack=True,
            session_id="sess-1",
            requested_families=["arxiv"],
            sources=[SOURCES[0]],
            quality_overall=0.9,
            questions=[QUESTIONS[0]],
            chase_mode="single_question",
            models=MODELS,
            daily_cap_usd=20,
            spent_usd=1,
        )


def test_budget_blocks():
    c = compose_highlight_source_attach_quality_interrogation(
        parent_asset_id="book-1",
        highlight="claim",
        gated=False,
        would_exceed=True,
        operator_ack=True,
        session_id="sess-1",
        requested_families=["arxiv"],
        sources=[SOURCES[0]],
        quality_overall=0.9,
        questions=[QUESTIONS[0]],
        chase_mode="single_question",
        models=MODELS,
        daily_cap_usd=1,
        spent_usd=0.9,
        projected_cost_usd_high=0.5,
    )
    assert c.pack_ready is False
    assert c.merge_executed is False


def test_operator_ack_false():
    c = compose_highlight_source_attach_quality_interrogation(
        parent_asset_id="book-1",
        highlight="claim",
        gated=False,
        would_exceed=False,
        operator_ack=False,
        session_id="sess-1",
        requested_families=["arxiv", "substack"],
        sources=SOURCES,
        quality_overall=0.9,
        questions=QUESTIONS,
        chase_mode="swarm_fanout",
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=1,
    )
    assert c.pack_ready is False
    assert c.prompts_injected is False
