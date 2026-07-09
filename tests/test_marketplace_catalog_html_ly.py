"""Residual (ly): HTML-first catalog projection + route include_html."""

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
    register_marketplace_host_routes,
    reset_marketplace_host_store,
)
from substrate.marketplace_host import (  # noqa: E402
    default_demo_catalog,
    project_catalog_html,
)


def test_project_catalog_html_never_pdf() -> None:
    cat = default_demo_catalog()
    html = project_catalog_html(cat)
    assert html.strip()
    assert not html.lstrip().lower().startswith("%pdf")
    assert "marketplace catalog" in html.lower() or "catalog" in html.lower()
    assert "pd-elements" in html or "Euclid" in html
    assert "manual_receipt_only" in html or "payment" in html.lower()


def test_project_catalog_html_filters_compose() -> None:
    cat = default_demo_catalog()
    math = project_catalog_html(cat, subject="mathematics")
    assert "pd-elements" in math or "Euclid" in math
    assert "Pride" not in math  # literature novel filtered out

    free = project_catalog_html(cat, free_only=True)
    assert "buy-modern" not in free or "Modern Systems" not in free

    gutenberg = project_catalog_html(cat, source="project_gutenberg")
    assert "project_gutenberg" in gutenberg
    # standard_ebooks titles should be absent when source-filtered
    assert "pd-pride" not in gutenberg


@pytest.fixture
def client():
    reset_marketplace_host_store()
    app = FastAPI()
    register_marketplace_host_routes(app)
    return TestClient(app)


def test_catalog_route_includes_html_by_default(client) -> None:
    r = client.get("/marketplace/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["view_format"] == "html"
    assert body.get("html")
    assert not body["html"].lstrip().lower().startswith("%pdf")
    assert body["count"] >= 10


def test_catalog_route_include_html_false(client) -> None:
    r = client.get("/marketplace/catalog", params={"include_html": "false"})
    assert r.status_code == 200
    body = r.json()
    assert "html" not in body or body.get("html") is None


def test_catalog_route_html_respects_filters(client) -> None:
    r = client.get(
        "/marketplace/catalog",
        params={"subject": "mathematics", "free_only": "true"},
    )
    assert r.status_code == 200
    body = r.json()
    html = body["html"]
    assert "mathematics" in html or "Euclid" in html or "pd-elements" in html
