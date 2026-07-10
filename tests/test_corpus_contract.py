"""Conformance tests for the two-verb corpus contract.

Runs the conformance kit against both reference adapters (twin notes and
hosted documents) plus the broken-adapter red-proof.  Each adapter is
tested with a realistic fixture corpus seeded into an in-memory reader.

SPR-07/08 will import the conformance helpers to validate their own
adapters against the same bar.
"""

from __future__ import annotations

from typing import Any

import pytest

from substrate.corpus_contract.adapters.hosted_docs import HostedDocsCorpusAdapter
from substrate.corpus_contract.adapters.twin_notes import TwinNotesCorpusAdapter
from substrate.corpus_contract.conformance import (
    BrokenProvenanceAdapter,
    FixtureDoc,
    assert_empty_query_returns_no_hits,
    assert_fetch_roundtrip,
    assert_miss_has_id,
    assert_provenance_completeness,
    assert_read_only,
    assert_search_retrieval,
    assert_unknown_id_returns_miss,
)

# ---------------------------------------------------------------------------
# Fixture data — realistic, not synthetic
# ---------------------------------------------------------------------------

TWIN_FIXTURE = FixtureDoc(
    id="twin_abc123",
    query_phrase="recursive note-taker substrate",
    content=(
        "The recursive note-taker substrate captures insights and questions "
        "for every information asset. Each asset has a twin side carrying "
        "LLM- and operator-recorded notes. The twin substrate is the recursive "
        "note-taker for this asset."
    ),
)

HOSTED_FIXTURE = FixtureDoc(
    id="hdoc_def456",
    query_phrase="deep-research doctrine",
    content=(
        "The deep-research doctrine defines exactly two verbs for any private "
        "corpus: search returning ids, fetch returning a document. This two-verb "
        "shape is what makes 'call arxiv, substack, and other knowledge-dense "
        "publications into my deep researches' one uniform mechanism."
    ),
)


# ---------------------------------------------------------------------------
# In-memory readers — minimal implementations of the reader protocols
# ---------------------------------------------------------------------------


class InMemoryTwinNoteReader:
    """In-memory twin-note reader for conformance testing."""

    def __init__(self, notes: list[dict[str, Any]]) -> None:
        self._notes = notes

    def list_twins(self, asset_id: str) -> list[dict[str, Any]]:
        return [n for n in self._notes if n.get("asset_id") == asset_id]


class InMemoryHostedDocReader:
    """In-memory hosted-document reader for conformance testing."""

    def __init__(self, docs: dict[str, dict[str, Any]], memberships: dict[str, list[str]]) -> None:
        self._docs = docs
        self._memberships = memberships

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        return self._docs.get(document_id)

    def list_membership(self, owner_id: str) -> list[str]:
        return list(self._memberships.get(owner_id, []))


# ---------------------------------------------------------------------------
# Adapter factories
# ---------------------------------------------------------------------------


def _make_twin_adapter() -> TwinNotesCorpusAdapter:
    reader = InMemoryTwinNoteReader(
        notes=[
            {
                "note_id": TWIN_FIXTURE.id,
                "asset_id": "asset-1",
                "kind": "insight",
                "text": TWIN_FIXTURE.content,
                "source_spawn_id": None,
                "investigation_id": None,
            },
            {
                "note_id": "twin_other",
                "asset_id": "asset-1",
                "kind": "question",
                "text": "What claims should be wrestled next?",
                "source_spawn_id": None,
                "investigation_id": None,
            },
        ]
    )
    return TwinNotesCorpusAdapter(reader, asset_id="asset-1")


def _make_hosted_adapter() -> HostedDocsCorpusAdapter:
    docs = {
        HOSTED_FIXTURE.id: {
            "document_id": HOSTED_FIXTURE.id,
            "owner_id": "owner-1",
            "book_id": "book-1",
            "content_hash": "abc123",
            "title": "Deep Research Doctrine",
            "license_class": "public_domain",
            "body_text": HOSTED_FIXTURE.content,
            "source_format": "text",
            "receipt_id": None,
            "view_format": "html",
        },
        "hdoc_other": {
            "document_id": "hdoc_other",
            "owner_id": "owner-1",
            "book_id": "book-2",
            "content_hash": "def456",
            "title": "Other Document",
            "license_class": "public_domain",
            "body_text": "Some other content about machine learning.",
            "source_format": "text",
            "receipt_id": None,
            "view_format": "html",
        },
    }
    memberships = {"owner-1": [HOSTED_FIXTURE.id, "hdoc_other"]}
    reader = InMemoryHostedDocReader(docs, memberships)
    return HostedDocsCorpusAdapter(reader, owner_id="owner-1")


# ---------------------------------------------------------------------------
# Twin-notes adapter conformance
# ---------------------------------------------------------------------------


class TestTwinNotesConformance:
    def test_search_retrieval(self) -> None:
        adapter = _make_twin_adapter()
        assert_search_retrieval(adapter, TWIN_FIXTURE)

    def test_fetch_roundtrip(self) -> None:
        adapter = _make_twin_adapter()
        assert_fetch_roundtrip(adapter, TWIN_FIXTURE)

    def test_unknown_id_returns_miss(self) -> None:
        adapter = _make_twin_adapter()
        assert_unknown_id_returns_miss(adapter)

    def test_provenance_completeness(self) -> None:
        adapter = _make_twin_adapter()
        assert_provenance_completeness(adapter, TWIN_FIXTURE)

    def test_read_only(self) -> None:
        adapter = _make_twin_adapter()
        assert_read_only(adapter)

    def test_empty_query_returns_no_hits(self) -> None:
        adapter = _make_twin_adapter()
        assert_empty_query_returns_no_hits(adapter)

    def test_miss_has_id(self) -> None:
        adapter = _make_twin_adapter()
        assert_miss_has_id(adapter)


# ---------------------------------------------------------------------------
# Hosted-documents adapter conformance
# ---------------------------------------------------------------------------


class TestHostedDocsConformance:
    def test_search_retrieval(self) -> None:
        adapter = _make_hosted_adapter()
        assert_search_retrieval(adapter, HOSTED_FIXTURE)

    def test_fetch_roundtrip(self) -> None:
        adapter = _make_hosted_adapter()
        assert_fetch_roundtrip(adapter, HOSTED_FIXTURE)

    def test_unknown_id_returns_miss(self) -> None:
        adapter = _make_hosted_adapter()
        assert_unknown_id_returns_miss(adapter)

    def test_provenance_completeness(self) -> None:
        adapter = _make_hosted_adapter()
        assert_provenance_completeness(adapter, HOSTED_FIXTURE)

    def test_read_only(self) -> None:
        adapter = _make_hosted_adapter()
        assert_read_only(adapter)

    def test_empty_query_returns_no_hits(self) -> None:
        adapter = _make_hosted_adapter()
        assert_empty_query_returns_no_hits(adapter)

    def test_miss_has_id(self) -> None:
        adapter = _make_hosted_adapter()
        assert_miss_has_id(adapter)


# ---------------------------------------------------------------------------
# Red-proof: broken adapter MUST fail the kit
# ---------------------------------------------------------------------------


class TestBrokenAdapterRedProof:
    def test_broken_provenance_fails_provenance_check(self) -> None:
        """A BrokenProvenanceAdapter (empty source_kind/origin_ref) MUST fail
        assert_provenance_completeness — proof the kit is not a rubber stamp.
        """
        broken = BrokenProvenanceAdapter(TWIN_FIXTURE)
        with pytest.raises(AssertionError, match="provenance"):
            assert_provenance_completeness(broken, TWIN_FIXTURE)

    def test_broken_adapter_still_passes_search(self) -> None:
        """The broken adapter does pass search (provenance is a fetch-time
        concern).  This is intentional: the red-proof targets provenance,
        not search.
        """
        broken = BrokenProvenanceAdapter(TWIN_FIXTURE)
        assert_search_retrieval(broken, TWIN_FIXTURE)

    def test_broken_adapter_passes_miss(self) -> None:
        broken = BrokenProvenanceAdapter(TWIN_FIXTURE)
        assert_unknown_id_returns_miss(broken)
