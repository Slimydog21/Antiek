"""Pure tests for floating multi-select → workstation marketplace MO."""

from __future__ import annotations

from substrate.floating_multiselect_workstation_marketplace_mo_compose import (
    compose_floating_multiselect_workstation_marketplace_mo,
    format_floating_multiselect_workstation_marketplace_mo_summary,
)

MEMBERS = [
    {
        "instance_id": "inst-a",
        "parent_asset_id": "book-1",
        "status": "open",
        "highlight": "scaling laws claim",
        "prior_prompt": "What evidence supports the claim?",
        "context": ["card-a"],
    },
    {
        "instance_id": "inst-b",
        "parent_asset_id": "book-1",
        "status": "completed",
        "highlight": "counter-evidence",
        "findings": ["finding-b1"],
    },
    {
        "instance_id": "inst-c",
        "parent_asset_id": "book-1",
        "status": "proposed",
        "highlight": "third angle",
    },
]

WORKSTATION_MARKETPLACE = {
    "records": {
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
    },
}


def test_multiselect_workstation_ready():
    c = compose_floating_multiselect_workstation_marketplace_mo(
        multiselect={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "members": MEMBERS,
            "selected_instance_ids": ["inst-a", "inst-b"],
            "pack_mode": "cohesive_prompt",
            "cohesive_prompt": "Synthesize A and B as one unit",
            "extra_context": ["operator note"],
        },
        workstation_marketplace=WORKSTATION_MARKETPLACE,
        operator_ack=True,
    )
    assert c.multiselect.pack_ready is True
    assert c.workstation_marketplace.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.merge_executed is False
    assert c.analysis_written is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.live_execution_authorized is False
    assert (
        c.authority
        == "floating_multiselect_workstation_marketplace_mo_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_floating_multiselect_workstation_marketplace_mo_summary(c)
    )


def test_operator_ack_false():
    c = compose_floating_multiselect_workstation_marketplace_mo(
        multiselect={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "members": MEMBERS,
            "selected_instance_ids": ["inst-a", "inst-b"],
            "pack_mode": "cohesive_prompt",
            "cohesive_prompt": "Synthesize",
        },
        workstation_marketplace=WORKSTATION_MARKETPLACE,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False


def test_unattended_blocks():
    wm = {
        **WORKSTATION_MARKETPLACE,
        "marketplace_research": {
            **WORKSTATION_MARKETPLACE["marketplace_research"],
            "research": {
                **WORKSTATION_MARKETPLACE["marketplace_research"]["research"],
                "mo_competition": {
                    **WORKSTATION_MARKETPLACE["marketplace_research"][
                        "research"
                    ]["mo_competition"],
                    "mo": {
                        **WORKSTATION_MARKETPLACE["marketplace_research"][
                            "research"
                        ]["mo_competition"]["mo"],
                        "unattended_ack": False,
                    },
                },
            },
        },
    }
    c = compose_floating_multiselect_workstation_marketplace_mo(
        multiselect={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "members": MEMBERS,
            "selected_instance_ids": ["inst-a", "inst-b"],
            "pack_mode": "cohesive_prompt",
            "cohesive_prompt": "Synthesize",
        },
        workstation_marketplace=wm,
        operator_ack=True,
    )
    assert c.workstation_marketplace.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False


def test_collective_pack_mode():
    c = compose_floating_multiselect_workstation_marketplace_mo(
        multiselect={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "members": MEMBERS,
            "selected_instance_ids": ["inst-a", "inst-b", "inst-c"],
            "pack_mode": "collective_pack",
            "cohesive_prompt": "Run as pack",
        },
        workstation_marketplace=WORKSTATION_MARKETPLACE,
        operator_ack=True,
    )
    assert c.multiselect.pack_ready is True
    assert c.pack_ready is True
    assert c.pack_dispatched is False
    assert c.purchase_executed is False
