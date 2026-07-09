"""Residual (lx): catalog filter_by_source substrate (source-chip contract)."""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.marketplace_host import default_demo_catalog  # noqa: E402


def test_filter_by_source_exact_case_insensitive() -> None:
    cat = default_demo_catalog()
    gutenberg = cat.filter_by_source("project_gutenberg")
    assert len(gutenberg) >= 3
    assert all(e.source == "project_gutenberg" for e in gutenberg)

    # Case-insensitive token.
    upper = cat.filter_by_source("PROJECT_GUTENBERG")
    assert {e.book_id for e in upper} == {e.book_id for e in gutenberg}

    se = cat.filter_by_source("standard_ebooks")
    assert len(se) >= 2
    assert all(e.source == "standard_ebooks" for e in se)

    stub = cat.filter_by_source("marketplace_stub")
    assert len(stub) >= 1
    assert all(e.source == "marketplace_stub" for e in stub)


def test_filter_by_source_empty_returns_all() -> None:
    cat = default_demo_catalog()
    all_entries = cat.filter_by_source("")
    assert len(all_entries) == len(cat.search(""))
    assert len(all_entries) >= 10


def test_filter_by_source_unknown_empty() -> None:
    cat = default_demo_catalog()
    assert cat.filter_by_source("not_a_real_source") == []


def test_source_and_subject_compose_on_demo() -> None:
    """STEM PD lives under project_gutenberg for researcher path."""
    cat = default_demo_catalog()
    stem_sources = cat.filter_by_source("project_gutenberg")
    math = [e for e in stem_sources if "mathematics" in e.subjects]
    assert any(e.book_id == "pd-elements" for e in math)
    assert any(e.book_id == "pd-principia" for e in math)
