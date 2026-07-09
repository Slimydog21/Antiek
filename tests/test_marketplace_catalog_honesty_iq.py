"""Residual (iq): marketplace catalog honesty payload (by_source / free counts)."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.marketplace_host_routes import (  # noqa: E402
    catalog_honesty_payload,
    register_marketplace_host_routes,
    reset_marketplace_host_store,
)


def test_catalog_honesty_payload_pure() -> None:
    rows = [
        {
            "book_id": "a",
            "source": "project_gutenberg",
            "license_class": "public_domain",
            "is_free": True,
        },
        {
            "book_id": "b",
            "source": "project_gutenberg",
            "license_class": "public_domain",
            "is_free": True,
        },
        {
            "book_id": "c",
            "source": "marketplace_stub",
            "license_class": "purchased",
            "is_free": False,
        },
    ]
    p = catalog_honesty_payload(rows)
    assert p["view_format"] == "html"
    assert p["payment_rails"] == "manual_receipt_only"
    assert p["by_source"]["project_gutenberg"] == 2
    assert p["by_source"]["marketplace_stub"] == 1
    assert p["public_domain_count"] == 2
    assert p["purchased_count"] == 1
    assert p["free_count"] == 2


@pytest.fixture
def client():
    reset_marketplace_host_store()
    app = FastAPI()
    register_marketplace_host_routes(app)
    return TestClient(app)


def test_catalog_route_includes_honesty_fields(client) -> None:
    r = client.get("/marketplace/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["view_format"] == "html"
    assert body["payment_rails"] == "manual_receipt_only"
    assert body["count"] >= 7  # residual io expansion
    assert body["public_domain_count"] >= 6
    assert body["purchased_count"] >= 1
    assert "project_gutenberg" in body["by_source"]
    assert "standard_ebooks" in body["by_source"]
    assert body["by_source"]["project_gutenberg"] >= 3
