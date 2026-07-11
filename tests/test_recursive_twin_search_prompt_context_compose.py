"""Pure tests for recursive twin search prompt context compose."""

from __future__ import annotations

from substrate.recursive_twin_search_prompt_context_compose import (
    compose_recursive_twin_search_prompt_context,
    format_recursive_twin_search_prompt_context_summary,
)

MODELS = [
    {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4},
    {"model_id": "grok-4.5", "projected_cost_usd_high": 0.2},
]
TWIN = [
    {
        "twin_id": "twin-1",
        "parent_asset_id": "asset-1",
        "insights": ["scaling laws hold under compute-optimal regimes"],
        "questions": ["Does the law break at sparse models?"],
        "source_label": "paper-notes",
    },
    {
        "twin_id": "twin-2",
        "parent_asset_id": "asset-2",
        "insights": ["attention efficiency tradeoffs"],
        "questions": ["What is the scaling frontier?"],
    },
]


def test_ready_pack():
    c = compose_recursive_twin_search_prompt_context(
        session_id="sess-1",
        parent_asset_id="asset-1",
        source_excerpt="Parent document about neural scaling laws.",
        focus_questions=["What is the core claim?"],
        twin_records=TWIN,
        search_query="scaling laws",
        user_prompt="Synthesize twin insights for next research step",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=3,
        projected_cost_usd_high=0.4,
        operator_ack=True,
    )
    assert c.twin_propose.twin_propose_ready is True
    assert len(c.search.hits) > 0
    assert c.prompt_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.twin_written is False
    assert c.remote_index_queried is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.live_router_authorized is False
    assert "prompts_injected=false" in format_recursive_twin_search_prompt_context_summary(
        c
    )
    assert c.to_dict()["live_router_authorized"] is False


def test_no_hits_seed():
    c = compose_recursive_twin_search_prompt_context(
        session_id="sess-2",
        parent_asset_id="asset-x",
        source_excerpt="Unrelated excerpt about gardens and soil.",
        twin_records=TWIN,
        search_query="zzzznonexistenttoken",
        user_prompt="Continue",
        selected_model_id="grok-4.5",
        models=MODELS,
        daily_cap_usd=10,
        spent_usd=1,
        operator_ack=True,
    )
    assert len(c.search.hits) == 0
    assert c.prompt_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.remote_index_queried is False


def test_ack_false():
    c = compose_recursive_twin_search_prompt_context(
        session_id="sess-3",
        parent_asset_id="asset-1",
        source_excerpt="Source text",
        twin_records=TWIN,
        search_query="scaling",
        user_prompt="Go",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=10,
        spent_usd=0,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.prompts_injected is False


def test_budget_would_exceed():
    c = compose_recursive_twin_search_prompt_context(
        session_id="sess-4",
        parent_asset_id="asset-1",
        source_excerpt="Scaling text",
        twin_records=TWIN,
        search_query="scaling",
        user_prompt="Deep research next",
        selected_model_id="gpt-5.5",
        models=MODELS,
        daily_cap_usd=1,
        spent_usd=0.9,
        projected_cost_usd_high=0.5,
        operator_ack=True,
    )
    assert c.prompt_pack.would_exceed is True
    assert c.live_router_authorized is False
