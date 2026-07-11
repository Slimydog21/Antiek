"""Hermetic tests for reading↔research HTML parity routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.reading_research_html_parity_compose_routes import (
    register_reading_research_html_parity_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_reading_research_html_parity_compose_routes(app)
    return TestClient(app)


def test_compose_ok() -> None:
    r = _client().post(
        "/assets/reading-research-html-parity/compose",
        json={
            "reading": {
                "asset_id": "a1",
                "asset_kind": "book",
                "source_format": "epub",
                "html_projection_sha": "sha-abc",
            },
            "research": {
                "asset_id": "a1",
                "asset_kind": "research",
                "source_format": "markdown",
                "html_projection_sha": "sha-abc",
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pdf_primary"] is False
    assert body["parity_ready"] is True
    assert body["authority"] == "reading_research_html_parity_compose_advisory"


def test_missing_sha_not_ready() -> None:
    r = _client().post(
        "/assets/reading-research-html-parity/compose",
        json={
            "reading": {
                "asset_id": "a1",
                "asset_kind": "book",
                "source_format": "pdf",
                "html_projection_sha": None,
            },
            "research": {
                "asset_id": "a1",
                "asset_kind": "research",
                "source_format": "pdf",
                "html_projection_sha": None,
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["parity_ready"] is False
    assert r.json()["pdf_primary"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/assets/reading-research-html-parity/compose",
        json={
            "reading": {
                "asset_id": "a1",
                "asset_kind": "book",
                "source_format": "html",
                "html_projection_sha": "x",
            },
            "research": {
                "asset_id": "a1",
                "asset_kind": "research",
                "source_format": "html",
                "html_projection_sha": "x",
            },
            "pdf_primary": True,
        },
    )
    assert r.status_code == 422
