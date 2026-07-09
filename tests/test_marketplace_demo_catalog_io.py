"""Residual (io): knowledge-dense PD demo catalog expansion."""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.marketplace_host import default_demo_catalog, host_book_into_account  # noqa: E402
from substrate.marketplace_host import InMemoryHostStore  # noqa: E402


def test_default_demo_catalog_includes_knowledge_dense_pd() -> None:
    cat = default_demo_catalog()
    ids = {e.book_id for e in cat.search("")}
    # Residual (io): expanded PD spine for research workstation.
    assert "pd-pride" in ids
    assert "pd-origin" in ids
    assert "pd-wealth" in ids
    assert "pd-federalist" in ids
    assert "pd-discourse" in ids
    assert "pd-liberty" in ids
    assert "buy-modern" in ids
    assert len(ids) >= 7

    sources = {e.source for e in cat.search("")}
    assert "project_gutenberg" in sources
    assert "standard_ebooks" in sources
    assert "marketplace_stub" in sources

    origin = cat.get("pd-origin")
    assert origin is not None
    assert origin.license_class == "public_domain"
    assert origin.is_free is True
    assert origin.source_format == "html"
    assert "species" in origin.body_text.lower() or "Beagle" in origin.body_text


def test_host_knowledge_dense_pd_html_first() -> None:
    store = InMemoryHostStore()
    cat = default_demo_catalog()
    r = host_book_into_account(
        owner_id="researcher",
        store=store,
        book_id="pd-origin",
        catalog=cat,
    )
    assert r.view_format == "html"
    assert not r.html.lstrip().lower().startswith("%pdf")
    assert r.html.strip()
    assert r.host.license_class == "public_domain"


def test_catalog_search_by_source() -> None:
    cat = default_demo_catalog()
    gutenberg = cat.search("project_gutenberg")
    assert len(gutenberg) >= 3
    assert all(e.source == "project_gutenberg" for e in gutenberg)
