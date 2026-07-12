"""Pure tests for model decision + HTML-native competition compose."""

from __future__ import annotations

from substrate.model_decision_html_native_competition_compose import (
    compose_model_decision_html_native_competition,
    format_model_decision_html_native_competition_summary,
)

COMPETITION_VIEW = {
    "session_id": "sess-1",
    "asset_id": "asset-1",
    "html_projection_sha": "sha-html-1",
    "view_requested": True,
    "twin_bound": True,
    "twin_substrate_ready": True,
    "claimed_format": "html",
    "competition": {
        "draft_id": "draft-1",
        "parent_asset_id": "asset-1",
        "competitor_decisions": [
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
        "quality_floor": 0.5,
        "would_exceed": False,
        "search_query": "scaling orchestration citations",
    },
}

DECISION = {
    "selected_model_id": "gpt-5.5",
    "models": [
        {
            "model_id": "gpt-5.5",
            "tier": "frontier",
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        {
            "model_id": "grok-4.5",
            "tier": "fast",
            "projected_cost_usd_high": 0.5,
            "projected_cost_usd_low": 0.2,
        },
    ],
    "daily_cap_usd": 50,
    "spent_usd": 10,
}


def test_decision_competition_ready():
    c = compose_model_decision_html_native_competition(
        decision=DECISION,
        competition_view=COMPETITION_VIEW,
        operator_ack=True,
    )
    assert c.decision.decision_ready is True
    assert c.competition_view.pack_ready is True
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.live_meter_read is False
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.live_dispatch_authorized is False
    assert c.remote_index_queried is False
    assert c.twin_written is False
    assert c.draft_written is False
    assert (
        c.authority
        == "model_decision_html_native_competition_compose_advisory"
    )
    assert "live_router_authorized=false" in (
        format_model_decision_html_native_competition_summary(c)
    )


def test_budget_would_exceed_blocks():
    c = compose_model_decision_html_native_competition(
        decision={
            **DECISION,
            "spent_usd": 49,
            "models": [
                {
                    "model_id": "gpt-5.5",
                    "tier": "frontier",
                    "projected_cost_usd_high": 5,
                    "projected_cost_usd_low": 4,
                }
            ],
        },
        competition_view=COMPETITION_VIEW,
        operator_ack=True,
    )
    assert c.decision.would_exceed is True
    assert c.pack_ready is False
    assert c.live_router_authorized is False


def test_operator_ack_false():
    c = compose_model_decision_html_native_competition(
        decision=DECISION,
        competition_view=COMPETITION_VIEW,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.twin_written is False


def test_competition_budget_blocks():
    view = {
        **COMPETITION_VIEW,
        "competition": {
            **COMPETITION_VIEW["competition"],
            "would_exceed": True,
        },
    }
    c = compose_model_decision_html_native_competition(
        decision=DECISION,
        competition_view=view,
        operator_ack=True,
    )
    assert c.competition_view.pack_ready is False
    assert c.pack_ready is False
    assert c.remote_fetched is False
