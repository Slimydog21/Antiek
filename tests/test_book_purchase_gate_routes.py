"""Hermetic tests for book purchase gate routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.book_purchase_gate_routes import (
    register_book_purchase_gate_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_book_purchase_gate_routes(app)
    return TestClient(app)


def test_evaluate_after_free_miss() -> None:
    r = _client().post(
        "/books/purchase-gate/evaluate",
        json={
            "title": "Unknown Book",
            "free_copy_preflight": {"freely_available": False},
            "skip_free_copy": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["purchase_intent_allowed"] is True
    assert body["purchase_executed"] is False


def test_blocks_when_free_available() -> None:
    r = _client().post(
        "/books/purchase-gate/evaluate",
        json={
            "title": "Walden",
            "free_copy_preflight": {"freely_available": True},
            "skip_free_copy": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["purchase_intent_allowed"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/books/purchase-gate/evaluate",
        json={
            "title": "X",
            "skip_free_copy": True,
            "operator_skip_acknowledged": True,
            "purchase_executed": True,
        },
    )
    assert r.status_code == 422


def test_skip_bool_strict() -> None:
    r = _client().post(
        "/books/purchase-gate/evaluate",
        json={
            "title": "X",
            "skip_free_copy": "false",
        },
    )
    assert r.status_code == 422
