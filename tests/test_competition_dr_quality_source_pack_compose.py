"""Pure tests for competition DR quality + source pack compose."""

from __future__ import annotations

from substrate.competition_dr_quality_source_pack_compose import (
    compose_competition_dr_quality_source_pack,
    format_competition_dr_quality_source_pack_summary,
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


def test_pack_ready():
    c = compose_competition_dr_quality_source_pack(
        session_id="sess-1",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv", "substack"],
        citations=CITATIONS,
        quality_overall=0.8,
        quality_floor=0.5,
        would_exceed=False,
        operator_ack=True,
    )
    assert c.pack_ready is True
    assert c.citations.pack_ready is True
    assert c.quality_budget.gate_ready is True
    assert c.competition.behind_count == 1
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    s = format_competition_dr_quality_source_pack_summary(c)
    assert "live_dispatch_authorized=false" in s
    assert c.to_dict()["remote_fetched"] is False


def test_require_no_behind_blocks():
    c = compose_competition_dr_quality_source_pack(
        session_id="sess-1",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv", "substack"],
        citations=CITATIONS,
        quality_overall=0.9,
        would_exceed=False,
        operator_ack=True,
        require_no_behind_gaps=True,
    )
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False


def test_quality_blocks():
    c = compose_competition_dr_quality_source_pack(
        session_id="s",
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
    assert c.quality_budget.quality_ready is False
    assert c.pack_ready is False


def test_would_exceed_blocks():
    c = compose_competition_dr_quality_source_pack(
        session_id="s",
        competitor_decisions=[],
        requested_families=["arxiv"],
        citations=[CITATIONS[0]],
        quality_overall=0.9,
        would_exceed=True,
        operator_ack=True,
    )
    assert c.quality_budget.budget_ready is False
    assert c.pack_ready is False


def test_empty_citations():
    c = compose_competition_dr_quality_source_pack(
        session_id="s",
        competitor_decisions=[],
        requested_families=["arxiv"],
        citations=[],
        quality_overall=0.9,
        would_exceed=False,
        operator_ack=True,
    )
    assert c.citations.pack_ready is False
    assert c.pack_ready is False


def test_ack_false():
    c = compose_competition_dr_quality_source_pack(
        session_id="s",
        competitor_decisions=[],
        requested_families=["arxiv"],
        citations=[CITATIONS[0]],
        quality_overall=0.9,
        would_exceed=False,
        operator_ack=False,
    )
    assert c.pack_ready is False
