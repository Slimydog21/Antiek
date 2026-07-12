"""Pure tests for workstation insight → marketplace highlight MO."""

from __future__ import annotations

import pytest

from substrate.workstation_insight_marketplace_highlight_mo_compose import (
    WorkstationInsightMarketplaceHighlightMoComposeError,
    compose_workstation_insight_marketplace_highlight_mo,
    format_workstation_insight_marketplace_highlight_mo_summary,
)

MARKET_RESEARCH = {
    "market": {
        "session_id": "sess-1",
        "asset_id": "book-1",
        "title": "Scaling Laws",
        "account_id": "acct-1",
        "free_copy_available": True,
        "free_html_projection_sha": "sha-free",
        "port_requested": True,
        "purchase_ack": False,
        "list_price_usd": 10,
        "approved_spend_usd": 20,
        "remaining_budget_usd": 50,
        "view_requested": True,
    },
    "research": {
        "highlight_surface": {
            "highlight": "scaling laws under noise",
            "gated": False,
            "would_exceed": False,
            "surface_action": "spawn_only",
            "source_families": ["arxiv"],
        },
        "mo_competition": {
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
                    "html_projection_sha": "sha-free",
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
        },
    },
}


def test_records_market_ready():
    c = compose_workstation_insight_marketplace_highlight_mo(
        records={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "records": [
                {
                    "record_id": "r1",
                    "kind": "insight",
                    "body": "Power-law scaling holds in compute-optimal regimes",
                },
                {
                    "record_id": "r2",
                    "kind": "question",
                    "body": "What residual gaps remain vs OpenAI DR?",
                },
            ],
            "mark_for_prompt_context": True,
        },
        marketplace_research=MARKET_RESEARCH,
        operator_ack=True,
    )
    assert c.records.record_ready is True
    assert c.marketplace_research.pack_ready is True
    assert c.pack_ready is True
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.purchase_executed is False
    assert c.live_execution_authorized is False
    assert (
        c.authority
        == "workstation_insight_marketplace_highlight_mo_compose_advisory"
    )
    assert "record_persisted=false" in (
        format_workstation_insight_marketplace_highlight_mo_summary(c)
    )


def test_empty_records_fail_closed():
    with pytest.raises(
        WorkstationInsightMarketplaceHighlightMoComposeError,
        match="records must be a non-empty array",
    ):
        compose_workstation_insight_marketplace_highlight_mo(
            records={
                "session_id": "sess-1",
                "parent_asset_id": "book-1",
                "records": [],
            },
            marketplace_research=MARKET_RESEARCH,
            operator_ack=True,
        )


def test_operator_ack_false():
    c = compose_workstation_insight_marketplace_highlight_mo(
        records={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "records": [{"record_id": "r1", "kind": "insight", "body": "A"}],
        },
        marketplace_research=MARKET_RESEARCH,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.prompts_injected is False


def test_unattended_blocks():
    mr = {
        **MARKET_RESEARCH,
        "research": {
            **MARKET_RESEARCH["research"],
            "mo_competition": {
                **MARKET_RESEARCH["research"]["mo_competition"],
                "mo": {
                    **MARKET_RESEARCH["research"]["mo_competition"]["mo"],
                    "unattended_ack": False,
                },
            },
        },
    }
    c = compose_workstation_insight_marketplace_highlight_mo(
        records={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "records": [{"record_id": "r1", "kind": "insight", "body": "A"}],
        },
        marketplace_research=mr,
        operator_ack=True,
    )
    assert c.marketplace_research.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
