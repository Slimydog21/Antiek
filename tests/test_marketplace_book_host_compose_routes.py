"""Hermetic tests for marketplace book host compose routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.marketplace_book_host_compose_routes import (
    register_marketplace_book_host_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_marketplace_book_host_compose_routes(app)
    return TestClient(app)


def test_compose_miss() -> None:
    r = _client().post(
        "/books/marketplace-compose/compose",
        json={
            "title": "Unknown Book",
            "free_copy_available": False,
            "host_requested": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "purchase_intent"
    assert body["purchase_executed"] is False
    assert body["hosted"] is False


def test_compose_free_hit() -> None:
    r = _client().post(
        "/books/marketplace-compose/compose",
        json={
            "title": "Walden",
            "free_copy_available": True,
            "html_projection_sha": "sha:ready",
            "host_requested": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["path"] == "html_host"
    assert r.json()["purchase_intent_allowed"] is False
    assert r.json()["hosted"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/books/marketplace-compose/compose",
        json={
            "title": "X",
            "free_copy_available": False,
            "purchase_executed": True,
        },
    )
    assert r.status_code == 422


def test_strict_bool() -> None:
    r = _client().post(
        "/books/marketplace-compose/compose",
        json={
            "title": "X",
            "free_copy_available": False,
            "host_requested": "true",
        },
    )
    assert r.status_code == 422
