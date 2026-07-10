"""Conformance kit for the two-verb corpus contract.

Reusable pytest helpers that any adapter must pass.  The kit is the contract —
the adapters are demonstrations.  SPR-07/08 will import these helpers to
validate their own adapters against the same bar.

Each test function accepts an adapter factory and fixture data, so the kit is
parametrizable by corpus.  The test file (``tests/test_corpus_contract.py``)
calls each helper for every reference adapter.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
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


def assert_search_retrieval(
    adapter: CorpusAdapter,
    fixture: FixtureDoc,
    *,
    decoy_ids: frozenset[str] | None = None,
) -> None:
    """A fixture document seeded with ``query_phrase`` must rank first.

    The kit seeds the adapter's reader with a document containing
    ``query_phrase`` verbatim, then asserts that searching for that phrase
    returns at least one hit whose id matches the fixture and whose score > 0.
    The fixture hit must rank first (highest score).

    Additional checks (hardenx round):
    - A non-matching decoy document must NOT rank above the seeded doc.
    - Returned scores must be non-increasing (descending order enforced).
    - A query matching nothing must return zero hits.
    """
    # (a) Decoy exclusion: decoy_ids are ids of documents that do NOT contain
    #     query_phrase.  None of them may rank above the fixture.
    if decoy_ids is None:
        decoy_ids = frozenset()

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
    # (a) No decoy ranks above the fixture
    fixture_idx = next(
        (i for i, h in enumerate(hits) if h.id == fixture.id), None
    )
    assert fixture_idx is not None
    for hit in hits:
        if hit.id in decoy_ids and hit.id != fixture.id:
            hit_idx = hits.index(hit)
            assert hit_idx >= fixture_idx, (
                f"decoy {hit.id!r} (rank {hit_idx}) ranks above "
                f"fixture {fixture.id!r} (rank {fixture_idx})"
            )
    # (b) Scores must be non-increasing
    for i in range(len(hits) - 1):
        assert hits[i].score >= hits[i + 1].score, (
            f"scores not non-increasing: hits[{i}].score={hits[i].score} < "
            f"hits[{i + 1}].score={hits[i + 1].score}"
        )
    # (c) A query matching nothing returns zero hits
    no_hits = adapter.search("__conformance_no_match_xyzzy__")
    assert len(no_hits) == 0, (
        f"query matching nothing returned {len(no_hits)} hits — "
        f"expected zero"
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
    """The adapter's public surface exposes no reader handle and no write methods.

    Structural checks (not name-prefix theatre):

    1. Reader protocols expose only read methods (``list_twins`` for twin
       notes, ``get_document`` + ``list_membership`` for hosted docs).
       Adapters store the reader in a name-mangled private attribute
       (``__reader``) so it is not part of the public API.

    2. No public attribute exposes a reader-protocol instance: if a public
       attribute has ``list_twins`` or ``get_document`` methods, it would
       mean the reader is leaked onto the adapter's public surface.

    3. No public method has a write-sounding name (``put_*``, ``write_*``,
       ``delete_*``, ``update_*``, ``create_*``).

    Residual limits (honesty):
    - Python has no visibility modifiers.  A determined caller can access
      the name-mangled ``_Adapter__reader`` attribute by spelling out the
      class name.  The double-underscore prefix prevents casual access but
      does not enforce encapsulation at the language level.
    - The reader-protocol duck-type check inspects for common read-method
      names.  A reader with an unusual API surface might slip through, but
      such a reader would not satisfy the adapter's type annotation either.
    """
    reader_method_names = frozenset({"list_twins", "get_document", "list_membership"})
    for name in dir(adapter):
        if name.startswith("_"):
            continue
        # Check 3: no write-sounding methods
        for prefix in ("put_", "write_", "delete_", "update_", "create_"):
            assert not name.startswith(prefix), (
                f"adapter exposes write method {name!r} — violates read-only contract"
            )
        # Check 2: no public attribute that is a reader-protocol instance
        attr = getattr(adapter, name, None)
        if attr is not None and not callable(attr):
            exposed = reader_method_names & set(dir(attr))
            assert not exposed, (
                f"adapter.{name} exposes reader-protocol methods {exposed} — "
                f"reader handle must be private"
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

    def __init__(
        self,
        fixture: FixtureDoc,
        *,
        now_fn: Callable[[], Any] | None = None,
    ) -> None:
        self._fixture = fixture
        import datetime as _dt

        self._now_fn = now_fn or (lambda: _dt.datetime.now(_dt.UTC))

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
            return CorpusDocument(
                content=self._fixture.content,
                provenance=Provenance(
                    source_kind="",  # ← broken: empty
                    origin_ref="",   # ← broken: empty
                    retrieved_at=self._now_fn(),
                ),
            )
        return CorpusMiss(id=id)
