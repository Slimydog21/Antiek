"""Hermetic tests for floating research draft combined document."""

from __future__ import annotations

import pytest

from substrate.floating_research_draft_combined_document import (
    FloatingResearchDraftCombinedDocumentError,
    compose_floating_research_draft_combined_document,
)


def test_builds_without_write() -> None:
    d = compose_floating_research_draft_combined_document(
        parent_asset_id="asset-1",
        parent_excerpt="<p>Original parent body</p>",
        operator_ack=False,
        sources=[
            {
                "instance_id": "fdr_1",
                "parent_asset_id": "asset-1",
                "status": "completed",
                "highlight": "scaling laws",
                "findings": ["claim A holds under noise"],
            }
        ],
    )
    assert d.draft_written is False
    assert d.merge_executed is False
    assert d.to_dict()["draft_written"] is False
    assert d.to_dict()["merge_executed"] is False
    assert d.draft_ready is True
    assert d.section_count >= 3
    assert d.authority == "floating_research_draft_combined_document_advisory"


def test_not_ready_without_content() -> None:
    d = compose_floating_research_draft_combined_document(
        parent_asset_id="a",
        parent_excerpt="body",
        operator_ack=True,
        sources=[
            {
                "instance_id": "f1",
                "parent_asset_id": "a",
                "status": "open",
            }
        ],
    )
    assert d.draft_ready is False
    assert d.draft_written is False


def test_rejects_cross_parent_and_closed() -> None:
    with pytest.raises(
        FloatingResearchDraftCombinedDocumentError, match="parent_asset_id"
    ):
        compose_floating_research_draft_combined_document(
            parent_asset_id="a",
            operator_ack=False,
            sources=[
                {
                    "instance_id": "f1",
                    "parent_asset_id": "other",
                    "status": "completed",
                    "findings": ["x"],
                }
            ],
        )
    with pytest.raises(
        FloatingResearchDraftCombinedDocumentError, match="not closed"
    ):
        compose_floating_research_draft_combined_document(
            parent_asset_id="a",
            operator_ack=False,
            sources=[
                {
                    "instance_id": "f1",
                    "parent_asset_id": "a",
                    "status": "closed",
                    "findings": ["x"],
                }
            ],
        )


def test_rejects_empty_sources() -> None:
    with pytest.raises(
        FloatingResearchDraftCombinedDocumentError, match="sources"
    ):
        compose_floating_research_draft_combined_document(
            parent_asset_id="a",
            operator_ack=False,
            sources=[],
        )
