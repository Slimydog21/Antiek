"""Hermetic tests for source publication registry routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.source_publication_registry_routes import (
    register_source_publication_registry_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_source_publication_registry_routes(app)
    return TestClient(app)


def test_select_ok() -> None:
    r = _client().post(
        "/research/source-publication-registry/select",
        json={"requested_families": ["arxiv", "substack"], "enabled_only": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fetched"] is False
    assert len(body["sources"]) == 2


def test_empty_families_422() -> None:
    r = _client().post(
        "/research/source-publication-registry/select",
        json={"requested_families": []},
    )
    assert r.status_code == 422


def test_custom_ok() -> None:
    r = _client().post(
        "/research/source-publication-registry/select",
        json={
            "requested_families": ["custom"],
            "custom_sources": [
                {
                    "source_id": "my-blog",
                    "family": "custom",
                    "label": "Blog",
                    "enabled": True,
                }
            ],
            "enabled_only": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["fetched"] is False
    assert r.json()["sources"][0]["source_id"] == "my-blog"


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/source-publication-registry/select",
        json={
            "requested_families": ["arxiv"],
            "fetched": True,
        },
    )
    assert r.status_code == 422


def test_strict_bool() -> None:
    r = _client().post(
        "/research/source-publication-registry/select",
        json={
            "requested_families": ["arxiv"],
            "enabled_only": "true",
        },
    )
    assert r.status_code == 422
