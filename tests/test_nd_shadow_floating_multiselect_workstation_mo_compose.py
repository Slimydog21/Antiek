"""Pure tests for ND shadow + multi-select workstation MO."""

from __future__ import annotations

from substrate.nd_shadow_floating_multiselect_workstation_mo_compose import (
    compose_nd_shadow_floating_multiselect_workstation_mo,
    format_nd_shadow_floating_multiselect_workstation_mo_summary,
)

RESEARCH_PACK = {
    "multiselect": {
        "session_id": "sess-1",
        "parent_asset_id": "book-1",
        "members": [
            {
                "instance_id": "inst-a",
                "parent_asset_id": "book-1",
                "status": "open",
                "highlight": "scaling laws claim",
            },
            {
                "instance_id": "inst-b",
                "parent_asset_id": "book-1",
                "status": "completed",
                "highlight": "counter-evidence",
                "findings": ["finding-b1"],
            },
        ],
        "selected_instance_ids": ["inst-a", "inst-b"],
        "pack_mode": "cohesive_prompt",
        "cohesive_prompt": "Synthesize A and B as one unit",
    },
    "workstation_marketplace": {
        "records": {
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "records": [
                {
                    "record_id": "r1",
                    "kind": "insight",
                    "body": "Power-law scaling holds",
                },
                {
                    "record_id": "r2",
                    "kind": "question",
                    "body": "What residual gaps remain?",
                },
            ],
            "mark_for_prompt_context": True,
        },
        "marketplace_research": {
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
                            {
                                "goal_id": "g1",
                                "title": "Survey arxiv competition gaps",
                            },
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
        },
    },
}


def test_research_ready_nd_reject_kill_switch_on():
    c = compose_nd_shadow_floating_multiselect_workstation_mo(
        nd_shadow={
            "selected_model_id": "gpt-5.5",
            "nd_recommended_model_id": "claude-opus",
            "kill_switch_on": True,
            "inventory_model_ids": ["gpt-5.5", "claude-opus"],
            "task": "deep_research",
        },
        research_pack=RESEARCH_PACK,
        operator_ack=True,
    )
    assert c.research_pack.pack_ready is True
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.nd_shadow.live_router_authorized is False
    assert c.nd_shadow.shadow_visible is False
    assert c.pack_ready is True
    assert c.production_router_verdict == "REJECT"
    assert c.live_router_authorized is False
    assert c.live_dispatched is False
    assert c.purchase_executed is False
    assert c.live_execution_authorized is False
    assert (
        c.authority
        == "nd_shadow_floating_multiselect_workstation_mo_compose_advisory"
    )
    assert "verdict=REJECT" in (
        format_nd_shadow_floating_multiselect_workstation_mo_summary(c)
    )


def test_shadow_visible_kill_switch_off():
    c = compose_nd_shadow_floating_multiselect_workstation_mo(
        nd_shadow={
            "selected_model_id": "gpt-5.5",
            "nd_recommended_model_id": "claude-opus",
            "kill_switch_on": False,
            "inventory_model_ids": ["gpt-5.5", "claude-opus"],
            "confidence": 0.7,
            "task": "deep_research",
        },
        research_pack=RESEARCH_PACK,
        operator_ack=True,
    )
    assert c.nd_shadow.shadow_visible is True
    assert c.nd_shadow.differs_from_selected is True
    assert c.nd_shadow.suggested_model_id == "claude-opus"
    assert c.production_router_verdict == "REJECT"
    assert c.live_router_authorized is False
    assert c.pack_ready is True


def test_operator_ack_false():
    c = compose_nd_shadow_floating_multiselect_workstation_mo(
        nd_shadow={
            "selected_model_id": "gpt-5.5",
            "nd_recommended_model_id": None,
            "kill_switch_on": True,
            "inventory_model_ids": ["gpt-5.5"],
        },
        research_pack=RESEARCH_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False


def test_unattended_blocks():
    pack = {
        **RESEARCH_PACK,
        "workstation_marketplace": {
            **RESEARCH_PACK["workstation_marketplace"],
            "marketplace_research": {
                **RESEARCH_PACK["workstation_marketplace"][
                    "marketplace_research"
                ],
                "research": {
                    **RESEARCH_PACK["workstation_marketplace"][
                        "marketplace_research"
                    ]["research"],
                    "mo_competition": {
                        **RESEARCH_PACK["workstation_marketplace"][
                            "marketplace_research"
                        ]["research"]["mo_competition"],
                        "mo": {
                            **RESEARCH_PACK["workstation_marketplace"][
                                "marketplace_research"
                            ]["research"]["mo_competition"]["mo"],
                            "unattended_ack": False,
                        },
                    },
                },
            },
        },
    }
    c = compose_nd_shadow_floating_multiselect_workstation_mo(
        nd_shadow={
            "selected_model_id": "gpt-5.5",
            "nd_recommended_model_id": None,
            "kill_switch_on": True,
            "inventory_model_ids": ["gpt-5.5"],
        },
        research_pack=pack,
        operator_ack=True,
    )
    assert c.research_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.production_router_verdict == "REJECT"
