"""Pure tests for multi-select + workstation record write twin pack."""

from __future__ import annotations

import pytest

from substrate.multi_select_workstation_record_write_twin_compose import (
    MultiSelectWorkstationRecordWriteTwinComposeError,
    compose_multi_select_workstation_record_write_twin,
    format_multi_select_workstation_record_write_twin_summary,
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
                                                "residual": (
                                                    "strengthen collective floating cohesive pack"
                                                ),
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
        },
    },
}

FULLSCREEN_PACK = {
    "fullscreen": {
        "session_id": "sess-1",
        "parent_asset_id": "book-1",
        "highlight": "Scaling laws claim from page 12",
        "prompt": "What evidence supports this?",
        "gated": False,
    },
    "weekly_nd": WEEKLY_ND,
}

DRAFT_GATE = {
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
}


RESEARCH_PACK = {
    "draft_gate": DRAFT_GATE,
    "fullscreen_pack": FULLSCREEN_PACK,
}

SETTINGS = {
    "models": [
        {"model_id": "gpt-5.5", "provider": "openai"},
        {"model_id": "grok-4.5", "provider": "xai"},
    ],
    "pending_add_model_ids": ["mimo-v2"],
    "action": "preview",
    "daily_cap_usd": 25,
    "spent_usd": 4,
    "selected_model_id": "gpt-5.5",
    "projected_cost_usd_high": 2,
    "projected_cost_usd_low": 1,
}


SETTINGS_RESEARCH = {
    "settings": SETTINGS,
    "research_pack": RESEARCH_PACK,
}

WRITE = {
    "session_id": "sess-1",
    "draft_id": "draft-1",
    "parent_asset_id": "book-1",
    "twin_slices": [
        {
            "parent_asset_id": "asset-1",
            "insights": ["scaling claim holds in compute-optimal regimes"],
            "questions": ["Where does it break?"],
        },
        {
            "parent_asset_id": "asset-2",
            "insights": ["attention efficiency tradeoffs"],
            "questions": [],
        },
    ],
    "base_draft_html": "<p>Opening paragraph</p>",
    "chase_slots": [
        {
            "slot_id": "s1",
            "question_id": "q1",
            "parent_asset_id": "book-1",
            "status": "completed",
            "findings": ["finding A from chase"],
            "body": "What evidence supports scaling?",
        },
        {
            "slot_id": "s2",
            "question_id": "q2",
            "parent_asset_id": "book-1",
            "status": "completed",
            "findings": ["finding B from chase"],
            "body": "Counter-evidence?",
        },
    ],
    "analysis_kind": "draft_analysis",
}


RESEARCH_WRITE = {
    "write": WRITE,
    "settings_research": SETTINGS_RESEARCH,
}

MO = {
    "operator_id": "op-1",
    "work_minutes": 120,
    "goals": [
        {"goal_id": "g1", "title": "Map scaling literature"},
        {"goal_id": "g2", "title": "Synthesize open problems"},
    ],
    "usd_per_hour": 30,
    "price_ceiling_ack": True,
    "stage": "recommend_only",
}


MO_WRITE = {
    "mo": MO,
    "research_write": RESEARCH_WRITE,
}

TWIN = {
    "parent_asset_id": "book-1",
    "source_excerpt": (
        "<p>Scaling laws hold under noise in compute-optimal regimes.</p>"
    ),
    "focus_questions": ["Where does it break?", "What residual gaps?"],
}


HTML_VIEW = {
    "session_id": "sess-1",
    "asset_id": "book-1",
    "html_projection_sha": "sha-html-ready",
    "view_requested": True,
    "twin_bound": True,
    "twin_substrate_ready": True,
    "claimed_format": "html",
}

TWIN_MO = {
    "twin": TWIN,
    "mo_write": MO_WRITE,
}


HTML_PACK = {
    "html_view": HTML_VIEW,
    "twin_mo": TWIN_MO,
}

RECORD_PROMPT = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "records": [
        {
            "record_id": "r1",
            "kind": "insight",
            "body": "scaling holds under noise",
            "source_ref": "book-1",
        },
        {
            "record_id": "r2",
            "kind": "question",
            "body": "What is the failure mode?",
        },
    ],
    "user_prompt": "Summarize open questions from the pack",
    "selected_model_id": "gpt-5",
    "models": [
        {
            "model_id": "gpt-5",
            "tier": "frontier",
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        {
            "model_id": "composer-2.5",
            "tier": "workhorse",
            "projected_cost_usd_high": 0.5,
        },
    ],
    "daily_cap_usd": 100,
    "spent_usd": 40,
    "projected_cost_usd_high": 2,
    "projected_cost_usd_low": 1,
}


RECORD_HTML = {
    "record_prompt": RECORD_PROMPT,
    "html_pack": HTML_PACK,
}

SOURCES = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "requested_families": ["arxiv", "substack"],
    "sources": [
        {
            "source_id": "arx-1",
            "family": "arxiv",
            "title": "Scaling Laws for Neural Language Models",
            "external_id": "arxiv:2001.08361",
            "html_fragment": "<article>abstract…</article>",
        },
        {
            "source_id": "sub-1",
            "family": "substack",
            "title": "The Batch essay",
            "external_id": "substack:thebatch",
            "url": "https://example.substack.com/p/x",
            "html_fragment": "<article>essay…</article>",
        },
    ],
    "quality_overall": 0.85,
    "quality_floor": 0.7,
    "would_exceed": False,
}


RESEARCH = {
    "sources": SOURCES,
    "record_html": RECORD_HTML,
}

MARKET = {
    "title": "Scaling Laws Book",
    "account_id": "acct-1",
    "free_copy_available": True,
    "free_html_projection_sha": "sha-free-1",
    "purchase_ack": False,
    "port_requested": True,
}


MARKET_RESEARCH = {
    "market": MARKET,
    "research": RESEARCH,
}

WEEKLY_LEARN = {
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
}


WEEKLY_MARKET = {
    "weekly_learn": WEEKLY_LEARN,
    "market_research": MARKET_RESEARCH,
}

ND_SHADOW = {
    "selected_model_id": "gpt-5",
    "nd_recommended_model_id": "claude-opus",
    "kill_switch_on": True,
    "confidence": 0.72,
    "task": "deep_research",
    "inventory_model_ids": ["gpt-5", "claude-opus", "mimo"],
}


ND_WEEKLY = {
    "nd_shadow": ND_SHADOW,
    "weekly_market": WEEKLY_MARKET,
}

COMPETITION = {
    "session_id": "sess-1",
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
}



COMPETITION_PACK = {
    "competition": COMPETITION,
    "nd_weekly": ND_WEEKLY,
}






WRITE = {
    "session_id": "sess-1",
    "draft_id": "draft-1",
    "parent_asset_id": "book-1",
    "twin_slices": [
        {
            "parent_asset_id": "asset-1",
            "insights": ["scaling claim holds in compute-optimal regimes"],
            "questions": ["Where does it break?"],
        },
        {
            "parent_asset_id": "asset-2",
            "insights": ["attention efficiency tradeoffs"],
            "questions": [],
        },
    ],
    "base_draft_html": "<p>Opening paragraph</p>",
    "chase_slots": [
        {
            "slot_id": "s1",
            "question_id": "q1",
            "parent_asset_id": "book-1",
            "status": "completed",
            "findings": ["finding A from chase"],
            "body": "What evidence supports scaling?",
        },
        {
            "slot_id": "s2",
            "question_id": "q2",
            "parent_asset_id": "book-1",
            "status": "completed",
            "findings": ["finding B from chase"],
            "body": "Counter-evidence?",
        },
    ],
    "analysis_kind": "draft_analysis",
}

HIGHLIGHT_PACK = {
    "highlight": {
        "parent_asset_id": "book-1",
        "highlight": "scaling orchestration residual under noise",
        "gated": False,
        "would_exceed": False,
        "preferred_view_mode": "floating",
        "source_families": ["arxiv", "substack"],
    },
    "twin_search_pack": {"competition_pack": COMPETITION_PACK},
}




RECORD_PROMPT = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "records": [
        {
            "record_id": "r1",
            "kind": "insight",
            "body": "scaling holds under noise",
            "source_ref": "book-1",
        },
        {
            "record_id": "r2",
            "kind": "question",
            "body": "What is the failure mode?",
        },
    ],
    "user_prompt": "Summarize open questions from the pack",
    "selected_model_id": "gpt-5",
    "models": [
        {
            "model_id": "gpt-5",
            "tier": "frontier",
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        {
            "model_id": "composer-2.5",
            "tier": "workhorse",
            "projected_cost_usd_high": 0.5,
        },
    ],
    "daily_cap_usd": 100,
    "spent_usd": 40,
    "projected_cost_usd_high": 2,
    "projected_cost_usd_low": 1,
}

WRITE_PACK = {
    "write": WRITE,
    "highlight_pack": HIGHLIGHT_PACK,
}




MULTISELECT = {
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
}

RECORD_WRITE = {
    "record_prompt": RECORD_PROMPT,
    "write_pack": WRITE_PACK,
}


def test_multiselect_record_write_ready():
    c = compose_multi_select_workstation_record_write_twin(
        multiselect=MULTISELECT,
        record_write=RECORD_WRITE,
        operator_ack=True,
    )
    assert c.multiselect.pack_ready is True
    assert c.record_write.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.prompts_injected is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "multi_select_workstation_record_write_twin_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_multi_select_workstation_record_write_twin_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_multi_select_workstation_record_write_twin(
        multiselect=MULTISELECT,
        record_write=RECORD_WRITE,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_multi_select_workstation_record_write_twin(
        multiselect={**MULTISELECT, "session_id": "sess-other"},
        record_write=RECORD_WRITE,
        operator_ack=True,
    )
    assert c.pack_ready is False
    assert c.pack_dispatched is False


def test_parent_mismatch_blocks():
    ms = {
        **MULTISELECT,
        "parent_asset_id": "book-other",
        "members": [
            {**m, "parent_asset_id": "book-other"} for m in MULTISELECT["members"]
        ],
    }
    c = compose_multi_select_workstation_record_write_twin(
        multiselect=ms,
        record_write=RECORD_WRITE,
        operator_ack=True,
    )
    assert c.pack_ready is False
    assert c.prompts_injected is False


def test_require_operator_ack_type():
    with pytest.raises(MultiSelectWorkstationRecordWriteTwinComposeError):
        compose_multi_select_workstation_record_write_twin(
            multiselect=MULTISELECT,
            record_write=RECORD_WRITE,
            operator_ack="yes",  # type: ignore[arg-type]
        )
