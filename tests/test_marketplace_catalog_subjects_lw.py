"""Residual (lw): research-domain subjects + STEM PD spine + by_subject honesty."""

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
from substrate.marketplace_host import (  # noqa: E402
    CatalogEntry,
    default_demo_catalog,
    host_book_into_account,
    InMemoryHostStore,
    make_catalog,
)


def test_catalog_entry_subjects_normalized_on_add() -> None:
    cat = make_catalog(
        [
            CatalogEntry(
                book_id="x",
                title="X",
                author="A",
                source="project_gutenberg",
                license_class="public_domain",
                is_free=True,
                body_text="hi",
                subjects=("Science", "  Math ", "", "science"),
            )
        ]
    )
    e = cat.get("x")
    assert e is not None
    # empty stripped; lowercased; order-preserving unique (Science + science → one).
    assert e.subjects == ("science", "math")
    assert "" not in e.subjects


def test_filter_by_subject_exact_token() -> None:
    cat = default_demo_catalog()
    math = cat.filter_by_subject("mathematics")
    assert len(math) >= 2  # elements + principia
    assert all("mathematics" in e.subjects for e in math)
    science = cat.filter_by_subject("science")
    assert len(science) >= 3
    empty = cat.filter_by_subject("")
    assert len(empty) == len(cat.search(""))


def test_search_includes_subjects() -> None:
    cat = default_demo_catalog()
    hits = cat.search("mathematics")
    assert any(e.book_id == "pd-elements" for e in hits)
    assert any(e.book_id == "pd-principia" for e in hits)


def test_stem_pd_spine_in_demo_catalog() -> None:
    cat = default_demo_catalog()
    ids = {e.book_id for e in cat.search("")}
    assert "pd-elements" in ids
    assert "pd-principia" in ids
    assert "pd-novum" in ids
    # Residual (td): Faraday / Maxwell knowledge-dense electricity STEM.
    assert "pd-faraday-electricity" in ids
    assert "pd-maxwell-em" in ids
    # Residual (tx): Boole laws of thought computing/logic PD.
    assert "pd-boole-laws-of-thought" in ids
    # Residual (ub): Heaviside electromagnetic theory electricity STEM.
    assert "pd-heaviside-em" in ids
    assert len(ids) >= 14
    elements = cat.get("pd-elements")
    assert elements is not None
    assert elements.license_class == "public_domain"
    assert elements.is_free is True


def test_stem_electricity_subjects_and_free_pd() -> None:
    """Residual (td): Faraday/Maxwell tagged physics+technology, free PD."""
    cat = default_demo_catalog()
    faraday = cat.get("pd-faraday-electricity")
    maxwell = cat.get("pd-maxwell-em")
    assert faraday is not None and maxwell is not None
    for e in (faraday, maxwell):
        assert e.license_class == "public_domain"
        assert e.is_free is True
        assert e.source == "project_gutenberg"
        assert "physics" in e.subjects
        assert "technology" in e.subjects
        assert "electricity" in e.subjects
    tech = cat.filter_by_subject("electricity")
    assert {e.book_id for e in tech} >= {
        "pd-faraday-electricity",
        "pd-maxwell-em",
        "pd-heaviside-em",
    }
    free_pd = [
        e
        for e in cat.search("")
        if e.license_class == "public_domain" and e.is_free
    ]
    assert len(free_pd) >= 13
    physics = cat.filter_by_subject("physics")
    assert any(e.book_id == "pd-faraday-electricity" for e in physics)
    assert any(e.book_id == "pd-maxwell-em" for e in physics)
    assert faraday.source_format == "html"
    assert maxwell.source_format == "html"


def test_boole_computing_logic_pd_html_first() -> None:
    """Residual (tx): Boole free PD hosts HTML for computing researchers."""
    cat = default_demo_catalog()
    boole = cat.get("pd-boole-laws-of-thought")
    assert boole is not None
    assert boole.license_class == "public_domain"
    assert boole.is_free is True
    assert boole.source_format == "html"
    assert "computing" in boole.subjects
    assert "logic" in boole.subjects
    assert "mathematics" in boole.subjects
    computing = cat.filter_by_subject("computing")
    assert any(e.book_id == "pd-boole-laws-of-thought" for e in computing)
    logic = cat.filter_by_subject("logic")
    assert any(e.book_id == "pd-boole-laws-of-thought" for e in logic)
    store = InMemoryHostStore()
    r = host_book_into_account(
        owner_id="tech-researcher",
        store=store,
        book_id="pd-boole-laws-of-thought",
        catalog=cat,
    )
    assert r.view_format == "html"
    assert r.host.license_class == "public_domain"
    assert not r.html.lstrip().lower().startswith("%pdf")
    assert "application/pdf" not in r.html.lower()
    assert "logic" in r.html.lower() or "calculus" in r.html.lower() or "boole" in r.html.lower()


def test_heaviside_electricity_pd_html_first() -> None:
    """Residual (ub): Heaviside free PD hosts HTML for electricity STEM."""
    cat = default_demo_catalog()
    heav = cat.get("pd-heaviside-em")
    assert heav is not None
    assert heav.license_class == "public_domain"
    assert heav.is_free is True
    assert heav.source_format == "html"
    assert "electricity" in heav.subjects
    assert "engineering" in heav.subjects
    assert "physics" in heav.subjects
    store = InMemoryHostStore()
    r = host_book_into_account(
        owner_id="tech-researcher",
        store=store,
        book_id="pd-heaviside-em",
        catalog=cat,
    )
    assert r.view_format == "html"
    assert r.host.license_class == "public_domain"
    assert not r.html.lstrip().lower().startswith("%pdf")
    assert "application/pdf" not in r.html.lower()
    assert (
        "heaviside" in r.html.lower()
        or "maxwell" in r.html.lower()
        or "electromagnetic" in r.html.lower()
    )


def test_host_stem_pd_html_first() -> None:
    store = InMemoryHostStore()
    cat = default_demo_catalog()
    r = host_book_into_account(
        owner_id="researcher",
        store=store,
        book_id="pd-principia",
        catalog=cat,
    )
    assert r.view_format == "html"
    assert not r.html.lstrip().lower().startswith("%pdf")
    assert "Newton" in r.html or "motion" in r.html.lower() or "body" in r.html.lower()


def test_host_faraday_maxwell_html_first_electricity() -> None:
    """Residual (te): Faraday/Maxwell host as HTML free PD (not PDF)."""
    store = InMemoryHostStore()
    cat = default_demo_catalog()
    for book_id, needle in (
        ("pd-faraday-electricity", "Induction"),
        ("pd-maxwell-em", "electromagnetic"),
    ):
        r = host_book_into_account(
            owner_id="tech-researcher",
            store=store,
            book_id=book_id,
            catalog=cat,
        )
        assert r.view_format == "html"
        assert r.host.license_class == "public_domain"
        assert not r.html.lstrip().lower().startswith("%pdf")
        assert needle.lower() in r.html.lower()
        assert "application/pdf" not in r.html.lower()


def test_catalog_honesty_by_subject() -> None:
    rows = [
        {
            "book_id": "a",
            "source": "project_gutenberg",
            "license_class": "public_domain",
            "is_free": True,
            "subjects": ["science", "biology"],
        },
        {
            "book_id": "b",
            "source": "standard_ebooks",
            "license_class": "public_domain",
            "is_free": True,
            "subjects": ["science", "philosophy"],
        },
        {
            "book_id": "c",
            "source": "marketplace_stub",
            "license_class": "purchased",
            "is_free": False,
            "subjects": ["technology"],
        },
    ]
    p = catalog_honesty_payload(rows)
    assert p["by_subject"]["science"] == 2
    assert p["by_subject"]["biology"] == 1
    assert p["by_subject"]["philosophy"] == 1
    assert p["by_subject"]["technology"] == 1
    assert p["view_format"] == "html"


@pytest.fixture
def client():
    reset_marketplace_host_store()
    app = FastAPI()
    register_marketplace_host_routes(app)
    return TestClient(app)


def test_catalog_route_subjects_and_by_subject(client) -> None:
    r = client.get("/marketplace/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["view_format"] == "html"
    assert body["count"] >= 10
    assert "by_subject" in body
    assert body["by_subject"].get("science", 0) >= 1
    assert body["by_subject"].get("mathematics", 0) >= 1
    # STEM spine entries present with subjects.
    by_id = {e["book_id"]: e for e in body["entries"]}
    assert "pd-elements" in by_id
    assert "mathematics" in by_id["pd-elements"]["subjects"]
    assert "pd-principia" in by_id
    assert "physics" in by_id["pd-principia"]["subjects"]
    assert "pd-novum" in by_id
    assert "method" in by_id["pd-novum"]["subjects"]


def test_electricity_chip_filter_includes_faraday_maxwell() -> None:
    """Residual (tj): electricity domain chip surfaces Faraday/Maxwell free PD."""
    cat = default_demo_catalog()
    elec = cat.filter_by_subject("electricity")
    ids = {e.book_id for e in elec}
    assert "pd-faraday-electricity" in ids
    assert "pd-maxwell-em" in ids
    assert all(e.is_free and e.license_class == "public_domain" for e in elec)
    # technology chip also reaches them (tech researcher path).
    tech = cat.filter_by_subject("technology")
    tech_ids = {e.book_id for e in tech}
    assert "pd-faraday-electricity" in tech_ids
    assert "pd-maxwell-em" in tech_ids
