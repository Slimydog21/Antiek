"""Pure tests for research wrestle + competition quality compose."""

from __future__ import annotations

from substrate.research_wrestle_competition_quality_compose import (
    compose_research_wrestle_competition_quality,
    format_research_wrestle_competition_quality_summary,
)

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
        "title": "Scaling Laws under Noise",
        "external_id": "arxiv:2301.00001",
    },
    {
        "citation_id": "c2",
        "family": "substack",
        "title": "Research notes on evals",
        "url": "https://example.substack.com/p/evals",
    },
]


def test_session_ready():
    c = compose_research_wrestle_competition_quality(
        session_id="sess-1",
        parent_asset_id="paper-1",
        floating_instance_count=2,
        completed_floating_count=1,
        twin_insight_count=3,
        twin_question_count=2,
        open_question_count=1,
        preferred_view_mode="floating",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv", "substack"],
        citations=CITATIONS,
        quality_overall=0.8,
        quality_floor=0.5,
        would_exceed=False,
        operator_ack=True,
    )
    assert c.wrestle.wrestle_ready is True
    assert c.competition_quality.pack_ready is True
    assert c.session_ready is True
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    s = format_research_wrestle_competition_quality_summary(c)
    assert "live_dispatch_authorized=false" in s
    assert c.to_dict()["remote_fetched"] is False


def test_require_no_behind_blocks():
    c = compose_research_wrestle_competition_quality(
        session_id="sess-1",
        parent_asset_id="paper-1",
        floating_instance_count=2,
        completed_floating_count=1,
        twin_insight_count=2,
        twin_question_count=1,
        open_question_count=1,
        competitor_decisions=DECISIONS,
        requested_families=["arxiv", "substack"],
        citations=CITATIONS,
        quality_overall=0.9,
        would_exceed=False,
        operator_ack=True,
        require_no_behind_gaps=True,
    )
    assert c.competition_quality.pack_ready is False
    assert c.session_ready is False
    assert c.live_dispatch_authorized is False


def test_quality_blocks():
    c = compose_research_wrestle_competition_quality(
        session_id="s",
        parent_asset_id="p",
        floating_instance_count=1,
        completed_floating_count=0,
        twin_insight_count=1,
        twin_question_count=1,
        open_question_count=1,
        competitor_decisions=[
            {
                "competitor": "X",
                "area": "budget_controls",
                "decision_summary": "hard caps",
                "antiek_status": "ahead",
            }
        ],
        requested_families=["arxiv"],
        citations=[CITATIONS[0]],
        quality_overall=0.2,
        quality_floor=0.5,
        would_exceed=False,
        operator_ack=True,
    )
    assert c.competition_quality.pack_ready is False
    assert c.session_ready is False


def test_would_exceed_blocks():
    c = compose_research_wrestle_competition_quality(
        session_id="s",
        parent_asset_id="p",
        floating_instance_count=2,
        completed_floating_count=1,
        twin_insight_count=2,
        twin_question_count=1,
        open_question_count=0,
        competitor_decisions=[],
        requested_families=["arxiv"],
        citations=[CITATIONS[0]],
        quality_overall=0.9,
        would_exceed=True,
        operator_ack=True,
    )
    assert c.session_ready is False
    assert c.live_dispatch_authorized is False


def test_ack_false():
    c = compose_research_wrestle_competition_quality(
        session_id="s",
        parent_asset_id="p",
        floating_instance_count=2,
        completed_floating_count=1,
        twin_insight_count=2,
        twin_question_count=1,
        open_question_count=1,
        competitor_decisions=DECISIONS,
        requested_families=["arxiv", "substack"],
        citations=CITATIONS,
        quality_overall=0.8,
        would_exceed=False,
        operator_ack=False,
    )
    assert c.competition_quality.pack_ready is False
    assert c.session_ready is False
