"""Route tests for fullscreen + weekly ND multi-select pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_fullscreen_antiek_bench_weekly_nd_mo_compose_routes import (
    register_floating_fullscreen_antiek_bench_weekly_nd_mo_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_fullscreen_antiek_bench_weekly_nd_mo_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/floating-fullscreen-antiek-bench-weekly-nd-mo/compose",
        json={
            "fullscreen": {
                "session_id": "sess-1",
                "parent_asset_id": "book-1",
                "highlight": "Scaling laws claim from page 12",
                "prompt": "What evidence supports this?",
                "gated": False,
            },
            "weekly_nd": {
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
                                                    "title": "Survey arxiv",
                                                },
                                                {
                                                    "goal_id": "g2",
                                                    "title": "Draft notes",
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
                                                            "decision_summary": "Inline",
                                                            "antiek_status": "parity",
                                                        }
                                                    ],
                                                    "requested_families": [
                                                        "arxiv"
                                                    ],
                                                    "citations": [
                                                        {
                                                            "citation_id": "c1",
                                                            "family": "arxiv",
                                                            "title": "Scaling Laws under Noise",
                                                            "external_id": "arxiv:2301.00001",
                                                        }
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
            },
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["backlog_mutated"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert (
        body["authority"]
        == "floating_fullscreen_antiek_bench_weekly_nd_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/floating-fullscreen-antiek-bench-weekly-nd-mo/compose",
        json={
            "fullscreen": {
                "session_id": "sess-2",
                "parent_asset_id": "book-2",
                "highlight": "claim text here",
                "gated": False,
            },
            "weekly_nd": {
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
                    ],
                },
                "nd_research": {
                    "nd_shadow": {
                        "selected_model_id": "gpt-5.5",
                        "nd_recommended_model_id": None,
                        "kill_switch_on": True,
                        "inventory_model_ids": ["gpt-5.5"],
                    },
                    "research_pack": {
                        "multiselect": {
                            "session_id": "sess-2",
                            "parent_asset_id": "book-2",
                            "members": [
                                {
                                    "instance_id": "inst-a",
                                    "parent_asset_id": "book-2",
                                    "status": "open",
                                    "highlight": "claim one",
                                },
                                {
                                    "instance_id": "inst-b",
                                    "parent_asset_id": "book-2",
                                    "status": "completed",
                                    "highlight": "claim two",
                                },
                            ],
                            "selected_instance_ids": ["inst-a", "inst-b"],
                            "pack_mode": "cohesive_prompt",
                            "cohesive_prompt": "Synthesize",
                        },
                        "workstation_marketplace": {
                            "records": {
                                "session_id": "sess-2",
                                "parent_asset_id": "book-2",
                                "records": [
                                    {
                                        "record_id": "r1",
                                        "kind": "insight",
                                        "body": "A",
                                    }
                                ],
                            },
                            "marketplace_research": {
                                "market": {
                                    "session_id": "sess-2",
                                    "asset_id": "book-2",
                                    "title": "Book",
                                    "account_id": "acct-1",
                                    "free_copy_available": True,
                                    "free_html_projection_sha": "sha",
                                    "port_requested": True,
                                    "purchase_ack": False,
                                    "list_price_usd": 10,
                                    "approved_spend_usd": 20,
                                    "remaining_budget_usd": 50,
                                    "view_requested": True,
                                },
                                "research": {
                                    "highlight_surface": {
                                        "highlight": "passage text here",
                                        "gated": False,
                                        "would_exceed": False,
                                        "surface_action": "spawn_only",
                                    },
                                    "mo_competition": {
                                        "mo": {
                                            "operator_id": "op-1",
                                            "work_minutes": 60,
                                            "goals": [
                                                {"goal_id": "g1", "title": "T"},
                                                {"goal_id": "g2", "title": "U"},
                                            ],
                                            "usd_per_hour": 10,
                                            "approved_ceiling_usd": 20,
                                            "unattended_ack": True,
                                            "spend_consent": True,
                                        },
                                        "research": {
                                            "decision": {
                                                "selected_model_id": "gpt-5.5",
                                                "models": [
                                                    {"model_id": "gpt-5.5"}
                                                ],
                                                "daily_cap_usd": 50,
                                                "spent_usd": 10,
                                            },
                                            "competition_view": {
                                                "session_id": "sess-2",
                                                "asset_id": "book-2",
                                                "html_projection_sha": "sha",
                                                "view_requested": True,
                                                "twin_bound": True,
                                                "claimed_format": "html",
                                                "competition": {
                                                    "draft_id": "d",
                                                    "parent_asset_id": "book-2",
                                                    "competitor_decisions": [
                                                        {
                                                            "competitor": "Perplexity",
                                                            "area": "citation_grounding",
                                                            "decision_summary": "Inline",
                                                            "antiek_status": "parity",
                                                        }
                                                    ],
                                                    "requested_families": [
                                                        "arxiv"
                                                    ],
                                                    "citations": [
                                                        {
                                                            "citation_id": "c1",
                                                            "family": "arxiv",
                                                            "title": "Paper title here",
                                                            "external_id": "arxiv:1",
                                                        }
                                                    ],
                                                    "quality_overall": 0.9,
                                                    "would_exceed": False,
                                                    "search_query": "paper scaling",
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "operator_ack": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_dispatched"] is False
    assert body["production_router_verdict"] == "REJECT"
