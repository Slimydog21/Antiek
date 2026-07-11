"""Hermetic tests for reading↔research HTML parity compose."""

from __future__ import annotations

import pytest

from substrate.reading_research_html_parity_compose import (
    ReadingResearchHtmlParityComposeError,
    compose_reading_research_html_parity,
)


def test_parity_ready_matching_sha() -> None:
    c = compose_reading_research_html_parity(
        reading={
            "asset_id": "a1",
            "asset_kind": "book",
            "source_format": "epub",
            "html_projection_sha": "sha-abc",
        },
        research={
            "asset_id": "a1",
            "asset_kind": "research",
            "source_format": "markdown",
            "html_projection_sha": "sha-abc",
        },
    )
    assert c.pdf_primary is False
    assert c.to_dict()["pdf_primary"] is False
    assert c.both_html_ready is True
    assert c.parity_ready is True
    assert c.authority == "reading_research_html_parity_compose_advisory"


def test_sha_differs() -> None:
    c = compose_reading_research_html_parity(
        reading={
            "asset_id": "a1",
            "asset_kind": "book",
            "source_format": "html",
            "html_projection_sha": "sha-1",
        },
        research={
            "asset_id": "a1",
            "asset_kind": "research",
            "source_format": "html",
            "html_projection_sha": "sha-2",
        },
    )
    assert c.both_html_ready is True
    assert c.parity_ready is False
    assert c.pdf_primary is False


def test_never_invents_sha() -> None:
    c = compose_reading_research_html_parity(
        reading={
            "asset_id": "a1",
            "asset_kind": "paper",
            "source_format": "pdf",
            "html_projection_sha": None,
        },
        research={
            "asset_id": "a1",
            "asset_kind": "research",
            "source_format": "pdf",
            "html_projection_sha": None,
        },
    )
    assert c.both_html_ready is False
    assert c.parity_ready is False
    assert c.pdf_primary is False
    assert any("no invent" in n for n in c.notes)


def test_rejects_non_object_mode() -> None:
    with pytest.raises(ReadingResearchHtmlParityComposeError, match="reading"):
        compose_reading_research_html_parity(
            reading=None,  # type: ignore[arg-type]
            research={
                "asset_id": "a",
                "asset_kind": "research",
                "source_format": "html",
                "html_projection_sha": "x",
            },
        )
