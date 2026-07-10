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
    # Residual (mf): honesty lines for source/subject in HTML projection.
    assert "By source:" in html or "by source" in html.lower()
    assert "By subject:" in html or "by subject" in html.lower()
    assert "project_gutenberg" in html
    assert "mathematics" in html or "science" in html
    # Residual (abi): free_count / public_domain_count on HTML projection (parity API).
    assert "free_count=" in html
    assert "public_domain_count=" in html
    free_only = project_catalog_html(default_demo_catalog(), free_only=True)
    assert "free_count=" in free_only
    # free_only projection: free_count equals filtered entries (all free).
    import re

    m = re.search(r"free_count=(\d+)", free_only)
    assert m is not None
    assert int(m.group(1)) >= 17
    # Residual (abj): under free_only, free_count == Entries=N of total (identity).
    entries_m = re.search(r"Entries=(\d+) of (\d+)", free_only)
    assert entries_m is not None
    assert int(entries_m.group(1)) == int(m.group(1))


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


def test_project_catalog_html_free_only_biology_free_count() -> None:
    """Residual (abj): free_only + biology free_count matches Origin+Hooke pair."""
    import re

    cat = default_demo_catalog()
    html = project_catalog_html(cat, free_only=True, subject="biology")
    assert "pd-origin" in html or "Origin" in html
    assert (
        "pd-hooke-micrographia" in html
        or "Micrographia" in html
        or "Hooke" in html
    )
    m = re.search(r"free_count=(\d+)", html)
    assert m is not None
    assert int(m.group(1)) == 2
    entries_m = re.search(r"Entries=(\d+) of", html)
    assert entries_m is not None
    assert int(entries_m.group(1)) == 2
    assert "subject=biology" in html
    assert "free_only=True" in html


def test_project_catalog_html_free_only_technology_includes_hooke() -> None:
    """Residual (abk): free_only + technology free STEM includes Hooke instruments."""
    import re

    cat = default_demo_catalog()
    html = project_catalog_html(cat, free_only=True, subject="technology")
    assert "pd-hooke-micrographia" in html or "Micrographia" in html or "Hooke" in html
    assert "pd-shannon" in html or "Shannon" in html or "pd-faraday" in html
    m = re.search(r"free_count=(\d+)", html)
    assert m is not None
    assert int(m.group(1)) >= 5
    entries_m = re.search(r"Entries=(\d+) of", html)
    assert entries_m is not None
    assert int(entries_m.group(1)) == int(m.group(1))
    assert "subject=technology" in html
    assert "free_only=True" in html
    assert "buy-modern" not in html


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
