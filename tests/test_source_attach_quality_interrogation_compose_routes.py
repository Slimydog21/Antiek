"""Route tests for source attach quality interrogation compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.source_attach_quality_interrogation_compose_routes import (
    register_source_attach_quality_interrogation_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_source_attach_quality_interrogation_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/source-attach-quality-interrogation/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
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
                    "title": "Deep research essay",
                    "html_fragment": "<article>essay…</article>",
                },
            ],
            "quality_overall": 0.88,
            "quality_floor": 0.7,
            "would_exceed": False,
            "operator_ack": True,
            "questions": [
                {
                    "question_id": "q1",
                    "body": "How do these sources ground multi-hop claims?",
                    "priority": 2,
                },
                {
                    "question_id": "q2",
                    "body": "Where do they disagree?",
                    "priority": 1,
                },
            ],
            "chase_mode": "swarm_fanout",
            "user_prompt": "Chase with arxiv/substack attached",
            "selected_model_id": "gpt-5.5",
            "models": [
                {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4},
            ],
            "daily_cap_usd": 30,
            "spent_usd": 4,
            "projected_cost_usd_high": 0.4,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["remote_fetched"] is False
    assert body["pdf_view_authorized"] is False
    assert body["live_dispatched"] is False
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["store_mutated"] is False
    assert body["authority"] == (
        "source_attach_quality_interrogation_compose_advisory"
    )


def test_compose_route_budget_block():
    c = _client()
    r = c.post(
        "/research/source-attach-quality-interrogation/compose",
        json={
            "session_id": "sess-2",
            "parent_asset_id": "a",
            "requested_families": ["arxiv"],
            "sources": [
                {
                    "source_id": "arx-1",
                    "family": "arxiv",
                    "title": "Paper",
                    "html_fragment": "<p>x</p>",
                }
            ],
            "quality_overall": 0.9,
            "would_exceed": True,
            "operator_ack": True,
            "questions": [
                {
                    "question_id": "q1",
                    "body": "Chase?",
                    "priority": 1,
                }
            ],
            "chase_mode": "single_question",
            "user_prompt": "Chase",
            "selected_model_id": "gpt-5.5",
            "models": [{"model_id": "gpt-5.5", "projected_cost_usd_high": 0.5}],
            "daily_cap_usd": 1,
            "spent_usd": 0.9,
            "projected_cost_usd_high": 0.5,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_dispatched"] is False
