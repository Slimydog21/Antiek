"""Pure tests for marketplace → highlight float recursive twin MO."""

from __future__ import annotations

from substrate.marketplace_highlight_float_recursive_twin_mo_compose import (
    compose_marketplace_highlight_float_recursive_twin_mo,
    format_marketplace_highlight_float_recursive_twin_mo_summary,
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
}

MARKET = {
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
    "twin_findings": [
        {
            "source_id": "q1",
            "body": "What is the core thesis?",
            "kind": "question",
        }
    ],
    "mark_for_prompt_context": True,
}


def test_free_book_research_ready():
    c = compose_marketplace_highlight_float_recursive_twin_mo(
        market=MARKET,
        research={
            "highlight_surface": {
                "highlight": "scaling laws under noise",
                "gated": False,
                "would_exceed": False,
                "surface_action": "spawn_only",
                "source_families": ["arxiv"],
            },
            "mo_competition": MO_COMP,
        },
        operator_ack=True,
    )
    assert c.market.session_ready is True
    assert c.research.pack_ready is True
    assert c.pack_ready is True
    assert c.purchase_executed is False
    assert c.charge_executed is False
    assert c.hosted is False
    assert c.pdf_view_authorized is False
    assert c.live_dispatched is False
    assert c.twin_written is False
    assert c.live_execution_authorized is False
    assert (
        c.authority
        == "marketplace_highlight_float_recursive_twin_mo_compose_advisory"
    )
    assert "purchase_executed=false" in (
        format_marketplace_highlight_float_recursive_twin_mo_summary(c)
    )


def test_seed_highlight_from_title():
    c = compose_marketplace_highlight_float_recursive_twin_mo(
        market=MARKET,
        research={
            "highlight_surface": {
                "gated": False,
                "would_exceed": False,
                "surface_action": "spawn_only",
            },
            "mo_competition": MO_COMP,
        },
        operator_ack=True,
        seed_highlight_from_title=True,
    )
    assert c.pack_ready is True
    assert c.purchase_executed is False


def test_operator_ack_false():
    c = compose_marketplace_highlight_float_recursive_twin_mo(
        market=MARKET,
        research={
            "highlight_surface": {
                "highlight": "scaling laws under noise",
                "gated": False,
                "would_exceed": False,
                "surface_action": "spawn_only",
            },
            "mo_competition": MO_COMP,
        },
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.hosted is False


def test_unattended_blocks():
    c = compose_marketplace_highlight_float_recursive_twin_mo(
        market=MARKET,
        research={
            "highlight_surface": {
                "highlight": "scaling laws under noise",
                "gated": False,
                "would_exceed": False,
                "surface_action": "spawn_only",
            },
            "mo_competition": {
                **MO_COMP,
                "mo": {**MO_COMP["mo"], "unattended_ack": False},
            },
        },
        operator_ack=True,
    )
    assert c.research.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
