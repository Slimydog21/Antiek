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
    # Residual (wd): Shannon mathematical theory of communication.
    assert "pd-shannon-communication" in ids
    # Residual (wl): Turing on computable numbers.
    assert "pd-turing-computable-numbers" in ids
    # Residual (xi): Lovelace Analytical Engine computing history.
    assert "pd-lovelace-analytical-engine" in ids
    # Residual (agh): Gödel incompleteness foundations STEM PD.
    assert "pd-godel-incompleteness" in ids
    assert len(ids) >= 18
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
    # Residual (abh/agh): free PD HTML spine floor after Gödel ≥18.
    assert len(free_pd) >= 18
    physics = cat.filter_by_subject("physics")
    assert any(e.book_id == "pd-faraday-electricity" for e in physics)
    assert any(e.book_id == "pd-maxwell-em" for e in physics)
    assert faraday.source_format == "html"
    assert maxwell.source_format == "html"


def test_shannon_information_theory_subjects_and_free_pd() -> None:
    """Residual (wd): Shannon tagged computing+information_theory, free PD."""
    cat = default_demo_catalog()
    shannon = cat.get("pd-shannon-communication")
    assert shannon is not None
    assert shannon.license_class == "public_domain"
    assert shannon.is_free is True
    assert shannon.source == "project_gutenberg"
    assert shannon.source_format == "html"
    assert "computing" in shannon.subjects
    assert "information_theory" in shannon.subjects
    assert "technology" in shannon.subjects
    info = cat.filter_by_subject("information_theory")
    assert {e.book_id for e in info} >= {"pd-shannon-communication"}
    computing = cat.filter_by_subject("computing")
    assert {e.book_id for e in computing} >= {
        "pd-boole-laws-of-thought",
        "pd-shannon-communication",
        "pd-turing-computable-numbers",
    }


def test_free_computing_stem_quartet() -> None:
    """Residual (xt/agh): free computing includes Boole/Shannon/Turing/Lovelace/Gödel."""
    cat = default_demo_catalog()
    free_comp = [
        e
        for e in cat.filter_by_subject("computing")
        if e.is_free and e.license_class == "public_domain"
    ]
    ids = {e.book_id for e in free_comp}
    assert ids >= {
        "pd-boole-laws-of-thought",
        "pd-shannon-communication",
        "pd-turing-computable-numbers",
        "pd-lovelace-analytical-engine",
        "pd-godel-incompleteness",
    }
    assert all(e.source_format == "html" for e in free_comp if e.book_id in ids)
    # Residual (zy/agh): free computing set size honesty after Gödel.
    assert len(free_comp) >= 5
    assert all(e.is_free for e in free_comp)


def test_godel_foundations_subjects_and_free_pd() -> None:
    """Residual (agh): Gödel incompleteness tagged foundations+logic, free PD HTML."""
    cat = default_demo_catalog()
    godel = cat.get("pd-godel-incompleteness")
    assert godel is not None
    assert godel.license_class == "public_domain"
    assert godel.is_free is True
    assert godel.source == "project_gutenberg"
    assert godel.source_format == "html"
    assert "foundations" in godel.subjects
    assert "logic" in godel.subjects
    assert "computability" in godel.subjects
    assert "computing" in godel.subjects
    foundations = cat.filter_by_subject("foundations")
    assert {e.book_id for e in foundations} >= {"pd-godel-incompleteness"}
    free_pd = [
        e
        for e in cat.search("")
        if e.license_class == "public_domain" and e.is_free
    ]
    assert len(free_pd) >= 18
    assert any(e.book_id == "pd-godel-incompleteness" for e in free_pd)


def test_free_technology_includes_electricity_and_computing() -> None:
    """Residual (yp): free technology subject spans electricity + computing STEM."""
    cat = default_demo_catalog()
    free_tech = [
        e
        for e in cat.filter_by_subject("technology")
        if e.is_free and e.license_class == "public_domain"
    ]
    ids = {e.book_id for e in free_tech}
    # Electricity + computing free STEM both tag technology for tech researchers.
    assert ids >= {
        "pd-faraday-electricity",
        "pd-shannon-communication",
        "pd-turing-computable-numbers",
        "pd-lovelace-analytical-engine",
        # Residual (abj): Hooke Micrographia free technology (instruments · biology).
        "pd-hooke-micrographia",
    }
    assert all(e.source_format == "html" for e in free_tech if e.book_id in ids)
    assert all("technology" in e.subjects for e in free_tech if e.book_id in ids)
    # Residual (zw/abj): free technology set is non-trivial for tech researchers.
    assert len(free_tech) >= 5
    assert all(e.is_free for e in free_tech)


def test_free_electricity_stem_trio() -> None:
    """Residual (xv): free electricity subject includes Faraday/Maxwell/Heaviside."""
    cat = default_demo_catalog()
    free_elec = [
        e
        for e in cat.filter_by_subject("electricity")
        if e.is_free and e.license_class == "public_domain"
    ]
    ids = {e.book_id for e in free_elec}
    assert ids >= {
        "pd-faraday-electricity",
        "pd-maxwell-em",
        "pd-heaviside-em",
    }
    assert all(e.source_format == "html" for e in free_elec if e.book_id in ids)
    # Residual (aaa): free electricity set size honesty (parity computing/technology).
    assert len(free_elec) >= 3
    assert all(e.is_free for e in free_elec)


def test_free_physics_stem_set_size() -> None:
    """Residual (aav): free physics subject is non-trivial for tech researchers.

    Principia + electricity EM trio (Faraday/Maxwell/Heaviside) all free PD HTML.
    Parity electricity/computing/technology domain size honesty.
    """
    cat = default_demo_catalog()
    free_phys = [
        e
        for e in cat.filter_by_subject("physics")
        if e.is_free and e.license_class == "public_domain"
    ]
    ids = {e.book_id for e in free_phys}
    assert ids >= {
        "pd-principia",
        "pd-faraday-electricity",
        "pd-maxwell-em",
        "pd-heaviside-em",
        # Residual (abk): Hooke Micrographia free physics (instrumented observation).
        "pd-hooke-micrographia",
    }
    assert all(e.source_format == "html" for e in free_phys if e.book_id in ids)
    assert len(free_phys) >= 5
    assert all(e.is_free for e in free_phys)


def test_free_mathematics_stem_set_size() -> None:
    """Residual (aaw): free mathematics subject is non-trivial for tech researchers.

    Elements + Principia + Boole + Lovelace (+ EM math) free PD HTML.
    Parity physics/computing domain size honesty.
    """
    cat = default_demo_catalog()
    free_math = [
        e
        for e in cat.filter_by_subject("mathematics")
        if e.is_free and e.license_class == "public_domain"
    ]
    ids = {e.book_id for e in free_math}
    assert ids >= {
        "pd-elements",
        "pd-principia",
        "pd-boole-laws-of-thought",
        "pd-lovelace-analytical-engine",
    }
    assert all(e.source_format == "html" for e in free_math if e.book_id in ids)
    assert len(free_math) >= 4
    assert all(e.is_free for e in free_math)


def test_free_science_stem_set_size() -> None:
    """Residual (aay): free science subject is non-trivial for tech researchers.

    Cross-domain free PD HTML spine (biology + physics + method + STEM).
    Parity physics/mathematics domain size honesty.
    """
    cat = default_demo_catalog()
    free_sci = [
        e
        for e in cat.filter_by_subject("science")
        if e.is_free and e.license_class == "public_domain"
    ]
    ids = {e.book_id for e in free_sci}
    assert ids >= {
        "pd-origin",
        "pd-principia",
        "pd-elements",
        "pd-novum",
        "pd-faraday-electricity",
        "pd-shannon-communication",
        # Residual (abl): Hooke Micrographia free science (instruments · method).
        "pd-hooke-micrographia",
    }
    assert all(e.source_format == "html" for e in free_sci if e.book_id in ids)
    assert len(free_sci) >= 7
    assert all(e.is_free for e in free_sci)


def test_free_philosophy_set_size() -> None:
    """Residual (aba): free philosophy subject is non-trivial for researchers.

    Method + liberty + discourse + political economy free PD HTML.
    Supports tech-researcher critical-reasoning substrate (parity science aay).
    """
    cat = default_demo_catalog()
    free_phil = [
        e
        for e in cat.filter_by_subject("philosophy")
        if e.is_free and e.license_class == "public_domain"
    ]
    ids = {e.book_id for e in free_phil}
    assert ids >= {
        "pd-novum",
        "pd-liberty",
        "pd-discourse",
        "pd-wealth",
    }
    assert all(e.source_format == "html" for e in free_phil if e.book_id in ids)
    assert len(free_phil) >= 4
    assert all(e.is_free for e in free_phil)


def test_free_biology_includes_origin_and_hooke() -> None:
    """Residual (abc): free biology STEM pair for tech researchers.

    Origin of Species + Hooke Micrographia — free PD HTML (biology + instruments).
    """
    cat = default_demo_catalog()
    free_bio = [
        e
        for e in cat.filter_by_subject("biology")
        if e.is_free and e.license_class == "public_domain"
    ]
    ids = {e.book_id for e in free_bio}
    assert ids >= {"pd-origin", "pd-hooke-micrographia"}
    hooke = cat.get("pd-hooke-micrographia")
    assert hooke is not None
    assert hooke.is_free is True
    assert hooke.source_format == "html"
    assert "technology" in hooke.subjects
    assert "biology" in hooke.subjects
    assert all(e.source_format == "html" for e in free_bio)
    assert len(free_bio) >= 2
    assert all(e.is_free for e in free_bio)


def test_free_method_includes_novum_and_hooke() -> None:
    """Residual (abd): free method subject for research methodology spine.

    Novum Organum + Hooke Micrographia — free PD HTML (Baconian method + instruments).
    """
    cat = default_demo_catalog()
    free_method = [
        e
        for e in cat.filter_by_subject("method")
        if e.is_free and e.license_class == "public_domain"
    ]
    ids = {e.book_id for e in free_method}
    assert ids >= {"pd-novum", "pd-hooke-micrographia"}
    assert all(e.source_format == "html" for e in free_method)
    assert len(free_method) >= 2
    assert all(e.is_free for e in free_method)


def test_free_engineering_stem_trio() -> None:
    """Residual (abf): free engineering subject for tech-researcher systems spine.

    Heaviside + Shannon + Lovelace free PD HTML (len ≥3).
    """
    cat = default_demo_catalog()
    free_eng = [
        e
        for e in cat.filter_by_subject("engineering")
        if e.is_free and e.license_class == "public_domain"
    ]
    ids = {e.book_id for e in free_eng}
    assert ids >= {
        "pd-heaviside-em",
        "pd-shannon-communication",
        "pd-lovelace-analytical-engine",
    }
    assert all(e.source_format == "html" for e in free_eng if e.book_id in ids)
    assert len(free_eng) >= 3
    assert all(e.is_free for e in free_eng)


def test_turing_computability_subjects_and_free_pd() -> None:
    """Residual (wl): Turing tagged computing+computability, free PD."""
    cat = default_demo_catalog()
    turing = cat.get("pd-turing-computable-numbers")
    assert turing is not None
    assert turing.license_class == "public_domain"
    assert turing.is_free is True
    assert turing.source == "project_gutenberg"
    assert turing.source_format == "html"
    assert "computing" in turing.subjects
    assert "computability" in turing.subjects
    assert "logic" in turing.subjects
    comp = cat.filter_by_subject("computability")
    assert {e.book_id for e in comp} >= {"pd-turing-computable-numbers"}


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
    # Residual (ws/xo): Shannon + Turing + Lovelace domain honesty on catalog route.
    assert body["by_subject"].get("information_theory", 0) >= 1
    assert body["by_subject"].get("computability", 0) >= 1
    assert body["by_subject"].get("history", 0) >= 1
    assert body["by_subject"].get("computing", 0) >= 3  # Boole + Shannon + Turing + Lovelace
    assert "pd-shannon-communication" in by_id
    assert "information_theory" in by_id["pd-shannon-communication"]["subjects"]
    assert "pd-turing-computable-numbers" in by_id
    assert "computability" in by_id["pd-turing-computable-numbers"]["subjects"]
    assert "pd-lovelace-analytical-engine" in by_id
    assert "history" in by_id["pd-lovelace-analytical-engine"]["subjects"]
    assert "computing" in by_id["pd-lovelace-analytical-engine"]["subjects"]
    # Residual (yr/abk): technology domain honesty includes Hooke + free STEM.
    assert body["by_subject"].get("technology", 0) >= 5
    # Residual (zb): free_count honesty includes full free PD catalog (STEM expanded).
    # Residual (abg): free_count floor after Hooke Micrographia (abc) ≥17 free PD.
    assert body.get("free_count", 0) >= 18
    assert body.get("public_domain_count", 0) >= 18
    # Residual (aab): free_count matches entry-level free flags (no silent drift).
    free_from_entries = sum(1 for e in body["entries"] if e.get("is_free"))
    assert body["free_count"] == free_from_entries
    # Residual (aad): public_domain_count matches entry license_class (no silent drift).
    pd_from_entries = sum(
        1 for e in body["entries"] if e.get("license_class") == "public_domain"
    )
    assert body["public_domain_count"] == pd_from_entries
    # Residual (aaf): count matches entries length (no silent truncation).
    assert body["count"] == len(body["entries"])


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
