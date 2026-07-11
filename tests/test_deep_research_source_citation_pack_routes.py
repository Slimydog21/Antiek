"""Hermetic tests for deep research source citation pack routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.deep_research_source_citation_pack_routes import (
    register_deep_research_source_citation_pack_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_deep_research_source_citation_pack_routes(app)
    return TestClient(app)


def test_build_ok() -> None:
    r = _client().post(
        "/research/source-citation-pack/build",
        json={
            "session_id": "sess-1",
            "requested_families": ["arxiv", "substack"],
            "citations": [
                {
                    "citation_id": "c1",
                    "family": "arxiv",
                    "title": "Attention Is All You Need",
                    "external_id": "arxiv:1706.03762",
                    "url": "https://arxiv.org/abs/1706.03762",
                    "year": 2017,
                }
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["remote_fetched"] is False
    assert body["pack_ready"] is True
    assert body["citation_count"] == 1
    assert body["authority"] == "deep_research_source_citation_pack_advisory"


def test_empty_citations() -> None:
    r = _client().post(
        "/research/source-citation-pack/build",
        json={
            "session_id": "s",
            "requested_families": ["arxiv"],
            "citations": [],
        },
    )
    assert r.status_code == 200
    assert r.json()["pack_ready"] is False
    assert r.json()["remote_fetched"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/source-citation-pack/build",
        json={
            "session_id": "s",
            "requested_families": ["arxiv"],
            "citations": [],
            "remote_fetched": True,
        },
    )
    assert r.status_code == 422
