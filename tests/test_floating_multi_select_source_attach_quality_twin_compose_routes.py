"""Route tests for multi-select source attach quality twin compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_multi_select_source_attach_quality_twin_compose_routes import (
    register_floating_multi_select_source_attach_quality_twin_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_multi_select_source_attach_quality_twin_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/floating-multi-select-source-attach-quality-twin/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
            "members": [
                {
                    "instance_id": "inst-a",
                    "parent_asset_id": "asset-1",
                    "status": "open",
                    "highlight": "scaling laws claim",
                },
                {
                    "instance_id": "inst-b",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "findings": ["finding-b1"],
                },
            ],
            "selected_instance_ids": ["inst-a", "inst-b"],
            "pack_mode": "cohesive_prompt",
            "cohesive_prompt": "Synthesize with sources",
            "operator_ack": True,
            "requested_families": ["arxiv"],
            "sources": [
                {
                    "source_id": "arx-1",
                    "family": "arxiv",
                    "title": "Scaling Laws for Neural Language Models",
                    "html_fragment": "<article>abstract…</article>",
                }
            ],
            "quality_overall": 0.9,
            "would_exceed": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["twin_written"] is False
    assert body["twin_feed"]["finding_count"] == 4
    assert body["authority"] == (
        "floating_multi_select_source_attach_quality_twin_compose_advisory"
    )


def test_compose_route_budget_block():
    c = _client()
    r = c.post(
        "/research/floating-multi-select-source-attach-quality-twin/compose",
        json={
            "session_id": "sess-2",
            "parent_asset_id": "asset-1",
            "members": [
                {
                    "instance_id": "inst-a",
                    "parent_asset_id": "asset-1",
                    "status": "open",
                },
                {
                    "instance_id": "inst-b",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                },
            ],
            "selected_instance_ids": ["inst-a", "inst-b"],
            "pack_mode": "cohesive_prompt",
            "cohesive_prompt": "Go",
            "operator_ack": True,
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
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is False
    assert body["twin_written"] is False
