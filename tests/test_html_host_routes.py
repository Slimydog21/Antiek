"""Hermetic tests for HTML host routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_host_routes import register_html_host_routes

SHA = "b" * 64


def _client() -> TestClient:
    app = FastAPI()
    register_html_host_routes(app)
    return TestClient(app)


def test_evaluate_ok() -> None:
    r = _client().post(
        "/books/html-host/evaluate",
        json={
            "title": "Walden",
            "free_copy_preflight": {"freely_available": True},
            "html_projection": {
                "ready": True,
                "html_sha256": SHA,
                "html_bytes": 100,
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["host_allowed"] is True
    assert body["hosted"] is False
    assert body["purchase_executed"] is False


def test_blocks_without_html() -> None:
    r = _client().post(
        "/books/html-host/evaluate",
        json={
            "title": "X",
            "purchase_gate": {"purchase_intent_allowed": True},
            "html_projection": {"ready": False},
        },
    )
    assert r.status_code == 200
    assert r.json()["host_allowed"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/books/html-host/evaluate",
        json={"title": "X", "hosted": True},
    )
    assert r.status_code == 422


def test_purchase_executed_rejected() -> None:
    r = _client().post(
        "/books/html-host/evaluate",
        json={
            "title": "X",
            "purchase_gate": {
                "purchase_intent_allowed": True,
                "purchase_executed": True,
            },
            "html_projection": {"ready": True, "html_sha256": SHA},
        },
    )
    assert r.status_code == 400
