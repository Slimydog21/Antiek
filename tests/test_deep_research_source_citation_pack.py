"""Hermetic tests for deep research source citation pack."""

from __future__ import annotations

import pytest

from substrate.deep_research_source_citation_pack import (
    DeepResearchSourceCitationPackError,
    build_deep_research_source_citation_pack,
)


def test_builds_without_remote_fetch() -> None:
    p = build_deep_research_source_citation_pack(
        session_id="sess-1",
        requested_families=["arxiv", "substack"],
        citations=[
            {
                "citation_id": "c1",
                "family": "arxiv",
                "title": "Attention Is All You Need",
                "external_id": "arxiv:1706.03762",
                "url": "https://arxiv.org/abs/1706.03762",
                "year": 2017,
                "authors": "Vaswani et al.",
            },
            {
                "citation_id": "c2",
                "family": "substack",
                "title": "Scaling notes",
                "url": "https://example.substack.com/p/scaling",
            },
        ],
    )
    assert p.remote_fetched is False
    assert p.to_dict()["remote_fetched"] is False
    assert p.selection.fetched is False
    assert p.pack_ready is True
    assert p.citation_count == 2
    assert "arxiv" in p.families_present
    assert p.authority == "deep_research_source_citation_pack_advisory"


def test_filters_outside_families() -> None:
    p = build_deep_research_source_citation_pack(
        session_id="s",
        requested_families=["arxiv"],
        filter_to_selected_families=True,
        citations=[
            {"citation_id": "c1", "family": "arxiv", "title": "Paper A"},
            {"citation_id": "c2", "family": "web", "title": "Blog B"},
        ],
    )
    assert p.citation_count == 1
    assert p.citations[0].citation_id == "c1"
    assert p.remote_fetched is False


def test_empty_not_ready() -> None:
    p = build_deep_research_source_citation_pack(
        session_id="s",
        requested_families=["arxiv"],
        citations=[],
    )
    assert p.pack_ready is False
    assert p.remote_fetched is False
    assert any("no invent" in n for n in p.notes)


def test_rejects_duplicate_and_bad_url() -> None:
    with pytest.raises(DeepResearchSourceCitationPackError, match="duplicate"):
        build_deep_research_source_citation_pack(
            session_id="s",
            requested_families=["arxiv"],
            citations=[
                {"citation_id": "x", "family": "arxiv", "title": "A"},
                {"citation_id": "x", "family": "arxiv", "title": "B"},
            ],
        )
    with pytest.raises(DeepResearchSourceCitationPackError, match="url"):
        build_deep_research_source_citation_pack(
            session_id="s",
            requested_families=["web"],
            citations=[
                {
                    "citation_id": "c1",
                    "family": "web",
                    "title": "T",
                    "url": "not-a-url",
                }
            ],
        )
