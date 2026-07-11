"""Route tests for midnight oil source attach quality compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_source_attach_quality_compose_routes import (
    register_midnight_oil_source_attach_quality_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_midnight_oil_source_attach_quality_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/midnight-oil-source-attach-quality/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 120,
            "goals": [
                {"goal_id": "g1", "title": "Survey arxiv scaling laws"},
                {"goal_id": "g2", "title": "Synthesize substack claims"},
            ],
            "usd_per_hour": 15,
            "approved_ceiling_usd": 40,
            "operator_ack": True,
            "unattended_ack": True,
            "spend_consent": True,
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
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_execution_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["pdf_view_authorized"] is False
    assert body["live_dispatched"] is False
    assert body["store_mutated"] is False
    assert body["authority"] == (
        "midnight_oil_source_attach_quality_compose_advisory"
    )


def test_compose_route_unattended_block():
    c = _client()
    r = c.post(
        "/research/midnight-oil-source-attach-quality/compose",
        json={
            "operator_id": "op-1",
            "work_minutes": 60,
            "goals": [{"goal_id": "g1", "title": "T"}],
            "usd_per_hour": 10,
            "approved_ceiling_usd": 20,
            "operator_ack": True,
            "unattended_ack": False,
            "spend_consent": True,
            "session_id": "s",
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
            "would_exceed": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_execution_authorized"] is False
