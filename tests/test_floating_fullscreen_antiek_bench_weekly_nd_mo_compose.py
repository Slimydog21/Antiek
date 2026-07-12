"""Pure tests for floating fullscreen + Antiek-bench weekly ND pack."""

from __future__ import annotations

import pytest

from substrate.floating_fullscreen_antiek_bench_weekly_nd_mo_compose import (
    FloatingFullscreenAntiekBenchWeeklyNdMoComposeError,
    compose_floating_fullscreen_antiek_bench_weekly_nd_mo,
    format_floating_fullscreen_antiek_bench_weekly_nd_mo_summary,
)

WEEKLY_ND = {
    "weekly_learn": {
        "week_id": "2026-W28",
        "min_events_per_task": 2,
        "events": [
            {
                "event_id": "e1",
                "task": "deep_research",
                "model_id": "gpt-5",
                "outcome": "failed",
            },
            {
                "event_id": "e2",
                "task": "deep_research",
                "model_id": "gpt-5",
                "outcome": "failed",
            },
            {
                "event_id": "e3",
                "task": "twin_notes",
                "model_id": "claude",
                "outcome": "worked",
            },
            {
                "event_id": "e4",
                "task": "twin_notes",
                "model_id": "claude",
                "outcome": "worked",
            },
        ],
    },
    "nd_research": {
        "nd_shadow": {
            "selected_model_id": "gpt-5.5",
            "nd_recommended_model_id": "claude-opus",
            "kill_switch_on": True,
            "inventory_model_ids": ["gpt-5.5", "claude-opus"],
            "task": "deep_research",
        },
        "research_pack": {
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
                                    {
                                        "goal_id": "g2",
                                        "title": "Draft twin notes",
                                    },
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
                                        "requested_families": [
                                            "arxiv",
                                            "substack",
                                        ],
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
        },
    },
}


def test_fullscreen_weekly_ready():
    c = compose_floating_fullscreen_antiek_bench_weekly_nd_mo(
        fullscreen={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "highlight": "Scaling laws claim from page 12",
            "prompt": "What evidence supports this?",
            "gated": False,
        },
        weekly_nd=WEEKLY_ND,
        operator_ack=True,
    )
    assert c.fullscreen.fullscreen_ready is True
    assert c.weekly_nd.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.pack_dispatched is False
    assert c.backlog_mutated is False
    assert c.store_mutated is False
    assert c.production_router_verdict == "REJECT"
    assert c.live_router_authorized is False
    assert c.live_execution_authorized is False
    assert (
        c.authority
        == "floating_fullscreen_antiek_bench_weekly_nd_mo_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_floating_fullscreen_antiek_bench_weekly_nd_mo_summary(c)
    )


def test_operator_ack_false():
    c = compose_floating_fullscreen_antiek_bench_weekly_nd_mo(
        fullscreen={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "highlight": "Scaling laws claim",
            "gated": False,
        },
        weekly_nd=WEEKLY_ND,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_gated_throws():
    with pytest.raises(
        (FloatingFullscreenAntiekBenchWeeklyNdMoComposeError, Exception)
    ):
        compose_floating_fullscreen_antiek_bench_weekly_nd_mo(
            fullscreen={
                "session_id": "sess-1",
                "parent_asset_id": "book-1",
                "highlight": "secret",
                "gated": True,
            },
            weekly_nd=WEEKLY_ND,
            operator_ack=True,
        )


def test_sparse_weekly_blocks():
    c = compose_floating_fullscreen_antiek_bench_weekly_nd_mo(
        fullscreen={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "highlight": "Scaling laws claim",
            "gated": False,
        },
        weekly_nd={
            **WEEKLY_ND,
            "weekly_learn": {
                "week_id": "2026-W28",
                "min_events_per_task": 5,
                "events": [
                    {
                        "event_id": "e1",
                        "task": "deep_research",
                        "model_id": "gpt-5",
                        "outcome": "failed",
                    }
                ],
            },
        },
        operator_ack=True,
    )
    assert c.weekly_nd.pack_ready is False
    assert c.pack_ready is False
    assert c.backlog_mutated is False
