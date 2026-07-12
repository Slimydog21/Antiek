"""Pure tests for MO + model decision + HTML competition compose."""

from __future__ import annotations

from substrate.mo_model_decision_html_native_competition_compose import (
    compose_mo_model_decision_html_native_competition,
    format_mo_model_decision_html_native_competition_summary,
)

RESEARCH = {
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
    },
}

MO = {
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
}


def test_mo_research_ready():
    c = compose_mo_model_decision_html_native_competition(
        mo=MO,
        research=RESEARCH,
        operator_ack=True,
    )
    assert c.mo.unattended_package_ready is True
    assert c.research.pack_ready is True
    assert c.pack_ready is True
    assert c.live_execution_authorized is False
    assert c.live_router_authorized is False
    assert c.pdf_view_authorized is False
    assert c.twin_written is False
    assert (
        c.authority
        == "mo_model_decision_html_native_competition_compose_advisory"
    )
    assert "live_execution_authorized=false" in (
        format_mo_model_decision_html_native_competition_summary(c)
    )


def test_unattended_ack_blocks():
    c = compose_mo_model_decision_html_native_competition(
        mo={**MO, "unattended_ack": False},
        research=RESEARCH,
        operator_ack=True,
    )
    assert c.mo.unattended_package_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False


def test_budget_blocks():
    research = {
        **RESEARCH,
        "decision": {
            **RESEARCH["decision"],
            "spent_usd": 49,
            "models": [
                {
                    "model_id": "gpt-5.5",
                    "projected_cost_usd_high": 5,
                    "projected_cost_usd_low": 4,
                }
            ],
        },
    }
    c = compose_mo_model_decision_html_native_competition(
        mo=MO,
        research=research,
        operator_ack=True,
    )
    assert c.research.pack_ready is False
    assert c.pack_ready is False
    assert c.live_router_authorized is False


def test_operator_ack_false():
    c = compose_mo_model_decision_html_native_competition(
        mo=MO,
        research=RESEARCH,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
