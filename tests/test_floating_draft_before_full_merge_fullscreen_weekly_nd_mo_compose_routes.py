"""Route tests for draft-before-merge + fullscreen weekly ND pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_routes import (
    register_floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True, gated: bool = False) -> dict:
    return {
        "draft_gate": {
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "parent_excerpt": "<p>Parent body on scaling laws</p>",
            "sources": [
                {
                    "instance_id": "float-1",
                    "parent_asset_id": "book-1",
                    "status": "completed",
                    "highlight": "key claim",
                    "findings": ["evidence A"],
                }
            ],
            "stage": "draft_only",
        },
        "fullscreen_pack": {
            "fullscreen": {
                "session_id": "sess-1",
                "parent_asset_id": "book-1",
                "highlight": "Scaling laws claim from page 12",
                "prompt": "What evidence supports this?",
                "gated": gated,
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
                                                            "residual": (
                                                                "strengthen collective floating cohesive pack"
                                                            ),
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
            },
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/floating-draft-before-full-merge-fullscreen-weekly-nd-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["draft_written"] is False
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False
    assert body["pack_dispatched"] is False
    assert body["backlog_mutated"] is False
    assert body["store_mutated"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert body["week_id"] == "2026-W28"
    assert (
        body["authority"]
        == "floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/floating-draft-before-full-merge-fullscreen-weekly-nd-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["merge_executed"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_gated_highlight_400():
    c = _client()
    r = c.post(
        "/research/floating-draft-before-full-merge-fullscreen-weekly-nd-mo/compose",
        json=_payload(operator_ack=True, gated=True),
    )
    assert r.status_code == 400


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/floating-draft-before-full-merge-fullscreen-weekly-nd-mo/compose",
        json=payload,
    )
    assert r.status_code == 422
