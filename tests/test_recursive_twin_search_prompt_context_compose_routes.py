"""Route tests for recursive twin search prompt context."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_search_prompt_context_compose_routes import (
    register_recursive_twin_search_prompt_context_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_search_prompt_context_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/recursive-twin-search-prompt-context/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
            "source_excerpt": "Parent about scaling laws.",
            "twin_records": [
                {
                    "twin_id": "t1",
                    "parent_asset_id": "asset-1",
                    "insights": ["scaling laws hold under compute-optimal regimes"],
                    "questions": ["Where do they break?"],
                }
            ],
            "search_query": "scaling laws",
            "user_prompt": "Next step",
            "selected_model_id": "gpt-5.5",
            "models": [
                {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4},
            ],
            "daily_cap_usd": 20,
            "spent_usd": 2,
            "projected_cost_usd_high": 0.4,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["twin_written"] is False
    assert body["remote_index_queried"] is False
    assert body["prompts_injected"] is False
    assert body["live_router_authorized"] is False
