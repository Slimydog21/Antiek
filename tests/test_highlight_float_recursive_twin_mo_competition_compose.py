"""Pure tests for highlight float → recursive twin MO competition."""

from __future__ import annotations

import pytest

from substrate.highlight_float_recursive_twin_mo_competition_compose import (
    HighlightFloatRecursiveTwinMoCompetitionComposeError,
    compose_highlight_float_recursive_twin_mo_competition,
    format_highlight_float_recursive_twin_mo_competition_summary,
)

MO_COMP = {
    "mo": {
        "operator_id": "op-1",
        "work_minutes": 120,
        "goals": [
            {"goal_id": "g1", "title": "Survey arxiv competition gaps"},
            {"goal_id": "g2", "title": "Draft twin notes"},
        ],
        "usd_per_hour": 15,
        "approved_ceiling_usd": 40,
        "unattended_ack": True,
        "spend_consent": True,
    },
    "research": {
        "decision": {
            "selected_model_id": "gpt-5.5",
            "models": [
                {
                    "model_id": "gpt-5.5",
                    "tier": "frontier",
                    "projected_cost_usd_high": 2,
                    "projected_cost_usd_low": 1,
                }
            ],
            "daily_cap_usd": 50,
            "spent_usd": 10,
        },
        "competition_view": {
            "session_id": "sess-1",
            "asset_id": "book-1",
            "html_projection_sha": "sha-html-1",
            "view_requested": True,
            "twin_bound": True,
            "claimed_format": "html",
            "competition": {
                "draft_id": "draft-1",
                "parent_asset_id": "book-1",
                "competitor_decisions": [
                    {
                        "competitor": "Perplexity",
                        "area": "citation_grounding",
                        "decision_summary": "Inline citations",
                        "antiek_status": "parity",
                    },
                    {
                        "competitor": "OpenAI DR",
                        "area": "multi_agent_orchestration",
                        "decision_summary": "Planner + browser agents",
                        "antiek_status": "behind",
                        "residual": "strengthen collective floating cohesive pack",
                    },
                ],
                "requested_families": ["arxiv", "substack"],
                "citations": [
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
                ],
                "quality_overall": 0.8,
                "would_exceed": False,
                "search_query": "scaling orchestration",
            },
        },
    },
}

HIGHLIGHT = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "highlight": "scaling laws under noise",
    "gated": False,
    "would_exceed": False,
    "surface_action": "spawn_only",
    "source_families": ["arxiv"],
    "twin_findings": [
        {"source_id": "extra-1", "body": "claim A supported", "kind": "insight"}
    ],
    "mark_for_prompt_context": True,
}


def test_highlight_mo_ready():
    c = compose_highlight_float_recursive_twin_mo_competition(
        highlight_surface=HIGHLIGHT,
        mo_competition=MO_COMP,
        operator_ack=True,
    )
    assert c.highlight_surface.pack_ready is True
    assert c.mo_competition.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.twin_written is False
    assert c.live_execution_authorized is False
    assert (
        c.authority
        == "highlight_float_recursive_twin_mo_competition_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_highlight_float_recursive_twin_mo_competition_summary(c)
    )


def test_gated_throws():
    with pytest.raises(
        HighlightFloatRecursiveTwinMoCompetitionComposeError, match="gated"
    ):
        compose_highlight_float_recursive_twin_mo_competition(
            highlight_surface={**HIGHLIGHT, "gated": True},
            mo_competition=MO_COMP,
            operator_ack=True,
        )


def test_operator_ack_false():
    c = compose_highlight_float_recursive_twin_mo_competition(
        highlight_surface=HIGHLIGHT,
        mo_competition=MO_COMP,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.twin_written is False


def test_unattended_blocks():
    c = compose_highlight_float_recursive_twin_mo_competition(
        highlight_surface=HIGHLIGHT,
        mo_competition={
            **MO_COMP,
            "mo": {**MO_COMP["mo"], "unattended_ack": False},
        },
        operator_ack=True,
    )
    assert c.mo_competition.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
