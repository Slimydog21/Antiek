"""Conformance kit for the two-verb corpus contract.

Reusable pytest helpers that any adapter must pass.  The kit is the contract —
the adapters are demonstrations.  SPR-07/08 will import these helpers to
validate their own adapters against the same bar.

Each test function accepts an adapter factory and fixture data, so the kit is
parametrizable by corpus.  The test file (``tests/test_corpus_contract.py``)
calls each helper for every reference adapter.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .protocol import CorpusAdapter, CorpusDocument, CorpusMiss, FetchResult

# ---------------------------------------------------------------------------
# Fixture document shape — what the kit seeds into the adapter's reader
# ---------------------------------------------------------------------------


class FixtureDoc:
    """A minimal fixture document for conformance testing.

    ``id`` is the document's opaque identifier.  ``query_phrase`` is a phrase
    that MUST appear verbatim in the document's content — the kit asserts that
    searching for it ranks this document first.  ``content`` is the full text.
    """

    def __init__(self, id: str, query_phrase: str, content: str) -> None:
        self.id = id
        self.query_phrase = query_phrase
        self.content = content


# ---------------------------------------------------------------------------
# Conformance assertions — call each one for every adapter under test
# ---------------------------------------------------------------------------


def assert_search_retrieval(adapter: CorpusAdapter, fixture: FixtureDoc) -> None:
    """A fixture document seeded with ``query_phrase`` must rank first.

    The kit seeds the adapter's reader with a document containing
    ``query_phrase`` verbatim, then asserts that searching for that phrase
    returns at least one hit whose id matches the fixture and whose score > 0.
    The fixture hit must rank first (highest score).
    """
    hits = adapter.search(fixture.query_phrase)
    assert len(hits) > 0, (
        f"search({fixture.query_phrase!r}) returned no hits — "
        f"fixture {fixture.id!r} not found"
    )
    top = hits[0]
    assert top.id == fixture.id, (
        f"expected fixture {fixture.id!r} to rank first, got {top.id!r}"
    )
    assert top.score > 0, f"expected score > 0 for fixture hit, got {top.score}"
    assert fixture.query_phrase.lower() in top.snippet.lower(), (
        f"query_phrase {fixture.query_phrase!r} not in snippet {top.snippet!r}"
    )


def assert_fetch_roundtrip(adapter: CorpusAdapter, fixture: FixtureDoc) -> None:
    """Fetching a known id returns a CorpusDocument with matching content.

    The content need not be byte-identical (adapters may trim), but the
    fixture's query_phrase must appear in the fetched content.
    """
    result = adapter.fetch(fixture.id)
    assert isinstance(result, CorpusDocument), (
        f"expected CorpusDocument for {fixture.id!r}, got {type(result).__name__}"
    )
    assert fixture.query_phrase in result.content, (
        f"query_phrase {fixture.query_phrase!r} not in fetched content"
    )


def assert_unknown_id_returns_miss(adapter: CorpusAdapter) -> None:
    """Fetching an unknown id returns CorpusMiss, not a bare KeyError.

    The id ``__conformance_unknown__`` is guaranteed not to exist.
    """
    result = adapter.fetch("__conformance_unknown__")
    assert isinstance(result, CorpusMiss), (
        f"expected CorpusMiss for unknown id, got {type(result).__name__}"
    )
    assert result.id == "__conformance_unknown__"


def assert_provenance_completeness(adapter: CorpusAdapter, fixture: FixtureDoc) -> None:
    """A fetched document has non-empty provenance fields.

    ``source_kind``, ``origin_ref``, and ``retrieved_at`` must all be set.
    """
    result = adapter.fetch(fixture.id)
    assert isinstance(result, CorpusDocument), (
        f"expected CorpusDocument, got {type(result).__name__}"
    )
    prov = result.provenance
    assert prov.source_kind, "provenance.source_kind is empty"
    assert prov.origin_ref, "provenance.origin_ref is empty"
    assert prov.retrieved_at is not None, "provenance.retrieved_at is None"


def assert_read_only(adapter: CorpusAdapter) -> None:
    """The adapter's public surface has no write methods.

    Checks that the adapter does not expose ``put_*``, ``write_*``,
    ``delete_*``, or ``update_*`` methods.  This is a surface-level check —
    the real read-only guarantee comes from the reader protocol having no
    write method.
    """
    for name in dir(adapter):
        if name.startswith("_"):
            continue
        for prefix in ("put_", "write_", "delete_", "update_", "create_"):
            assert not name.startswith(prefix), (
                f"adapter exposes write method {name!r} — violates read-only contract"
            )


def assert_empty_query_returns_no_hits(adapter: CorpusAdapter) -> None:
    """An empty query returns no hits (edge-case contract)."""
    hits = adapter.search("")
    assert len(hits) == 0, f"empty query returned {len(hits)} hits"


def assert_miss_has_id(adapter: CorpusAdapter) -> None:
    """A CorpusMiss carries the requested id for caller debuggability."""
    result = adapter.fetch("__conformance_miss_id_check__")
    assert isinstance(result, CorpusMiss)
    assert result.id == "__conformance_miss_id_check__"


# ---------------------------------------------------------------------------
# Broken-adapter red-proof — a deliberately non-conforming adapter
# ---------------------------------------------------------------------------


class BrokenProvenanceAdapter:
    """An adapter that returns CorpusDocument with empty provenance.

    This MUST fail ``assert_provenance_completeness`` — that is the
    red-proof that the conformance kit is not a rubber stamp.
    """

    def __init__(self, fixture: FixtureDoc) -> None:
        self._fixture = fixture

    def search(self, query: str) -> Sequence[Any]:
        from .protocol import CorpusHit

        if not query.strip():
            return ()
        if self._fixture.query_phrase.lower() in query.lower():
            return (
                CorpusHit(id=self._fixture.id, score=1.0, snippet=self._fixture.content[:160]),
            )
        return ()

    def fetch(self, id: str) -> FetchResult:
        from .protocol import Provenance

        if id == self._fixture.id:
            import datetime

            return CorpusDocument(
                content=self._fixture.content,
                provenance=Provenance(
                    source_kind="",  # ← broken: empty
                    origin_ref="",   # ← broken: empty
                    retrieved_at=datetime.datetime.now(datetime.UTC),
                ),
            )
        return CorpusMiss(id=id)
