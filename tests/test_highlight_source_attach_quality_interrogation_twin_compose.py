"""Pure tests for highlight source attach quality interrogation twin."""

from __future__ import annotations

from substrate.highlight_source_attach_quality_interrogation_twin_compose import (
    compose_highlight_source_attach_quality_interrogation_twin,
    format_highlight_source_attach_quality_interrogation_twin_summary,
)

MODELS = [{"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4}]
SOURCES = [
    {
        "source_id": "arx-1",
        "family": "arxiv",
        "title": "Scaling Laws for Neural Language Models",
        "html_fragment": "<article>abstract…</article>",
    }
]
QUESTIONS = [
    {"question_id": "q1", "body": "How does this highlight relate?", "priority": 2}
]


def test_highlight_twin_ready():
    c = compose_highlight_source_attach_quality_interrogation_twin(
        parent_asset_id="book-1",
        highlight="power-law scaling",
        gated=False,
        would_exceed=False,
        selected_model_id="gpt-5.5",
        operator_ack=True,
        session_id="sess-1",
        requested_families=["arxiv"],
        sources=SOURCES,
        quality_overall=0.9,
        questions=QUESTIONS,
        chase_mode="single_question",
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=1,
    )
    assert c.highlight_pack.pack_ready is True
    assert c.twin_feed.feed_ready is True
    assert c.pack_ready is True
    assert c.twin_feed.finding_count == 3
    assert c.live_dispatched is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert "twin_written=false" in format_highlight_source_attach_quality_interrogation_twin_summary(
        c
    )


def test_budget_blocks():
    c = compose_highlight_source_attach_quality_interrogation_twin(
        parent_asset_id="book-1",
        highlight="claim",
        gated=False,
        would_exceed=True,
        operator_ack=True,
        session_id="s",
        requested_families=["arxiv"],
        sources=SOURCES,
        quality_overall=0.9,
        questions=QUESTIONS,
        chase_mode="single_question",
        models=MODELS,
        daily_cap_usd=1,
        spent_usd=0.9,
        projected_cost_usd_high=0.5,
    )
    assert c.pack_ready is False
    assert c.twin_written is False


def test_operator_ack_false():
    c = compose_highlight_source_attach_quality_interrogation_twin(
        parent_asset_id="book-1",
        highlight="claim",
        gated=False,
        would_exceed=False,
        operator_ack=False,
        session_id="s",
        requested_families=["arxiv"],
        sources=SOURCES,
        quality_overall=0.9,
        questions=QUESTIONS,
        chase_mode="single_question",
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=1,
    )
    assert c.pack_ready is False
    assert c.prompts_injected is False


def test_caller_twin_findings():
    c = compose_highlight_source_attach_quality_interrogation_twin(
        parent_asset_id="book-1",
        highlight="claim",
        gated=False,
        would_exceed=False,
        selected_model_id="gpt-5.5",
        operator_ack=True,
        session_id="s",
        requested_families=["arxiv"],
        sources=SOURCES,
        quality_overall=0.9,
        questions=QUESTIONS,
        chase_mode="single_question",
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=1,
        twin_findings=[
            {"source_id": "c1", "body": "Caller insight", "kind": "insight"}
        ],
    )
    assert c.twin_feed.finding_count == 1
    assert c.pack_ready is True
