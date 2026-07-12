"""Pure tests for competition DR quality write compose."""

from __future__ import annotations

from substrate.competition_dr_quality_write_compose import (
    compose_competition_dr_quality_write,
    format_competition_dr_quality_write_summary,
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


def test_quality_write_ready():
    c = compose_competition_dr_quality_write(
        session_id="sess-1",
        draft_id="draft-1",
        parent_asset_id="asset-1",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv", "substack"],
        citations=CITATIONS,
        quality_overall=0.8,
        quality_floor=0.5,
        would_exceed=False,
        operator_ack=True,
    )
    assert c.quality_source.pack_ready is True
    assert c.write_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.merge_executed is False
    assert c.authority == "competition_dr_quality_write_compose_advisory"
    assert "live_dispatch_authorized=false" in format_competition_dr_quality_write_summary(
        c
    )


def test_budget_blocks():
    c = compose_competition_dr_quality_write(
        session_id="sess-2",
        draft_id="draft-2",
        parent_asset_id="asset-1",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv"],
        citations=[CITATIONS[0]],
        quality_overall=0.9,
        would_exceed=True,
        operator_ack=True,
    )
    assert c.quality_source.pack_ready is False
    assert c.pack_ready is False
    assert c.remote_fetched is False


def test_operator_ack_false():
    c = compose_competition_dr_quality_write(
        session_id="sess-3",
        draft_id="draft-3",
        parent_asset_id="asset-1",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv", "substack"],
        citations=CITATIONS,
        quality_overall=0.8,
        would_exceed=False,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.draft_written is False


def test_caller_slices():
    c = compose_competition_dr_quality_write(
        session_id="sess-4",
        draft_id="draft-4",
        parent_asset_id="asset-1",
        competitor_decisions=DECISIONS,
        requested_families=["arxiv", "substack"],
        citations=CITATIONS,
        quality_overall=0.8,
        would_exceed=False,
        operator_ack=True,
        twin_slices=[
            {
                "parent_asset_id": "asset-1",
                "insights": ["A", "B"],
                "questions": ["Q?"],
            }
        ],
        chase_slots=[
            {
                "slot_id": "s1",
                "question_id": "q1",
                "parent_asset_id": "asset-1",
                "status": "completed",
                "findings": ["f1"],
            },
            {
                "slot_id": "s2",
                "question_id": "q2",
                "parent_asset_id": "asset-1",
                "status": "completed",
                "findings": ["f2"],
            },
        ],
        analysis_kind="full_analysis",
    )
    assert c.write_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.merge_executed is False
