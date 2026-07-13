"""Conformance kit for the two-verb corpus contract.

Reusable pytest helpers that any adapter must pass.  The kit is the contract —
the adapters are demonstrations.  SPR-07/08 will import these helpers to
validate their own adapters against the same bar.

Each test function accepts an adapter factory and fixture data, so the kit is
parametrizable by corpus.  The test file (``tests/test_corpus_contract.py``)
calls each helper for every reference adapter.

Clock discipline: adapters accept an injectable ``now_fn`` for
``provenance.retrieved_at``.  The wall-clock default (``datetime.now(UTC)``)
exists for production ergonomics only.  The kit itself never relies on the
wall clock — every test passes a fixed ``now_fn`` so that deterministic
replay is proven, not merely possible.
"""

from __future__ import annotations

import datetime
import math
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from .protocol import CorpusAdapter, CorpusDocument, CorpusHit, CorpusMiss, FetchResult, Provenance

AdapterFactory = Callable[[tuple["FixtureDoc", ...]], CorpusAdapter]

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


def assert_corpus_conformance(factory: AdapterFactory) -> None:
    """Run the mandatory kit against two randomized multi-document corpora."""
    observed: list[CorpusDocument] = []
    for _ in range(2):
        nonce = uuid.uuid4().hex
        phrase = f"evidence-{nonce}"
        primary = FixtureDoc(
            f"primary-{nonce}",
            phrase,
            ((f"Primary {phrase} {phrase} {phrase}. ") + ("long context " * 40)),
        )
        secondary = FixtureDoc(
            f"secondary-{nonce}",
            phrase,
            ((f"Secondary {phrase}. ") + ("different context " * 40)),
        )
        decoy = FixtureDoc(
            f"decoy-{nonce}",
            f"unrelated-{nonce}",
            "unrelated material " * 40,
        )
        fixtures = (primary, secondary, decoy)
        adapter = factory(fixtures)
        by_id = {fixture.id: fixture for fixture in fixtures}
        assert_search_retrieval(
            adapter,
            primary,
            decoy_ids=frozenset({decoy.id}),
            expected_ids=(primary.id, secondary.id),
            expected_documents=by_id,
        )
        for fixture in fixtures:
            assert_fetch_roundtrip(adapter, fixture)
            assert_provenance_completeness(adapter, fixture)
            assert_fetch_determinism(adapter, fixture)
        assert_unknown_id_returns_miss(adapter)
        assert_read_only(adapter)
        assert_empty_query_returns_no_hits(adapter)
        assert_miss_has_id(adapter)
        result = adapter.fetch(primary.id)
        assert type(result) is CorpusDocument
        observed.append(result)
    assert observed[0] != observed[1], "factory ignored incompatible fixture corpora"


# ---------------------------------------------------------------------------
# Conformance assertions — call each one for every adapter under test
# ---------------------------------------------------------------------------


def assert_search_retrieval(
    adapter: CorpusAdapter,
    fixture: FixtureDoc,
    *,
    decoy_ids: frozenset[str] | None = None,
    expected_ids: tuple[str, ...] | None = None,
    expected_documents: Mapping[str, FixtureDoc] | None = None,
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
    assert type(hits) is tuple, "search result must be an exact tuple"
    assert len(hits) > 0, (
        f"search({fixture.query_phrase!r}) returned no hits — fixture {fixture.id!r} not found"
    )
    top = hits[0]
    ids: list[str] = []
    for hit in hits:
        assert type(hit) is CorpusHit
        assert type(hit.id) is str and hit.id.strip()
        assert type(hit.score) is float and math.isfinite(hit.score)
        assert type(hit.snippet) is str and hit.snippet.strip()
        assert len(hit.snippet) <= 200
        ids.append(hit.id)
    assert len(ids) == len(set(ids)), "search ids must be unique"
    assert list(hits) == sorted(hits, key=lambda hit: (-hit.score, hit.id)), (
        "search results must sort by descending score then ascending id"
    )
    assert hits == adapter.search(fixture.query_phrase), (
        "identical search must replay deterministically"
    )
    if expected_ids is not None:
        assert tuple(hit.id for hit in hits) == expected_ids, (
            "search did not return the exact seeded matching corpus in rank order"
        )
    if expected_documents is not None:
        for hit in hits:
            expected = expected_documents.get(hit.id)
            assert expected is not None, f"search returned phantom id {hit.id!r}"
            fetched = adapter.fetch(hit.id)
            assert type(fetched) is CorpusDocument, (
                f"search hit {hit.id!r} did not fetch coherently"
            )
            assert fetched.content == expected.content
    assert top.id == fixture.id, f"expected fixture {fixture.id!r} to rank first, got {top.id!r}"
    assert top.score > 0, f"expected score > 0 for fixture hit, got {top.score}"
    assert fixture.query_phrase.lower() in top.snippet.lower(), (
        f"query_phrase {fixture.query_phrase!r} not in snippet {top.snippet!r}"
    )
    # (a) No decoy ranks above the fixture
    fixture_idx = next((i for i, h in enumerate(hits) if h.id == fixture.id), None)
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
    assert len(no_hits) == 0, f"query matching nothing returned {len(no_hits)} hits — expected zero"


def assert_fetch_roundtrip(adapter: CorpusAdapter, fixture: FixtureDoc) -> None:
    """Fetching a known id returns a CorpusDocument with matching content.

    Content is exact: fetch is the full-document verb and may not trim/coerce.
    """
    result = adapter.fetch(fixture.id)
    assert isinstance(result, CorpusDocument), (
        f"expected CorpusDocument for {fixture.id!r}, got {type(result).__name__}"
    )
    assert type(result) is CorpusDocument
    assert type(result.content) is str
    assert result.content == fixture.content


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

    ``source_kind``, ``origin_ref``, ``retrieved_at``, and ``license_class``
    must all be set. Origin identity is the fetched unit id.
    """
    result = adapter.fetch(fixture.id)
    assert isinstance(result, CorpusDocument), (
        f"expected CorpusDocument, got {type(result).__name__}"
    )
    prov = result.provenance
    assert type(prov) is Provenance, "provenance must be exact Provenance"
    assert type(prov.source_kind) is str and prov.source_kind.strip(), (
        "provenance.source_kind is invalid"
    )
    assert type(prov.origin_ref) is str and prov.origin_ref.strip(), (
        "provenance.origin_ref is invalid"
    )
    assert prov.origin_ref == fixture.id
    assert type(prov.license_class) is str and prov.license_class.strip()
    assert type(prov.retrieved_at) is datetime.datetime
    assert prov.retrieved_at.tzinfo is not None
    assert prov.retrieved_at.utcoffset() == datetime.timedelta(0)


def assert_read_only(adapter: CorpusAdapter) -> None:
    """The adapter exposes exactly the two read verbs and no public store handle.

    These are structural/public-surface checks. Behavioral read-only evidence is
    supplied by deterministic repeated search/fetch in the mandatory kit; Python
    cannot prove that an opaque private dependency performed no hidden write.

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
    public_callables = {
        name
        for name in dir(adapter)
        if not name.startswith("_") and callable(getattr(adapter, name))
    }
    assert public_callables == {"search", "fetch"}, (
        f"adapter public callable surface is {sorted(public_callables)!r}"
    )
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


def assert_fetch_determinism(adapter: CorpusAdapter, fixture: FixtureDoc) -> None:
    """Two fetches of the same id with the same clock produce equal results.

    This proves that the adapter's clock is injectable and deterministic —
    when a fixed ``now_fn`` is used, ``provenance.retrieved_at`` is identical
    across calls.  The wall-clock default exists for production ergonomics
    only; the kit never relies on it.
    """
    first = adapter.fetch(fixture.id)
    second = adapter.fetch(fixture.id)
    assert isinstance(first, CorpusDocument), (
        f"expected CorpusDocument for {fixture.id!r}, got {type(first).__name__}"
    )
    assert isinstance(second, CorpusDocument), (
        f"expected CorpusDocument for {fixture.id!r}, got {type(second).__name__}"
    )
    assert first == second, (
        f"two fetches of {fixture.id!r} with the same clock produced "
        f"different results:\n  first:  {first}\n  second: {second}"
    )


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

    def search(self, query: str) -> tuple[CorpusHit, ...]:
        from .protocol import CorpusHit

        if not query.strip():
            return ()
        if self._fixture.query_phrase.lower() in query.lower():
            return (CorpusHit(id=self._fixture.id, score=1.0, snippet=self._fixture.content[:160]),)
        return ()

    def fetch(self, id: str) -> FetchResult:
        from .protocol import Provenance

        if id == self._fixture.id:
            # Deliberately forge a value around constructor validation so the
            # reusable kit proves it independently detects hostile adapters.
            provenance = object.__new__(Provenance)
            object.__setattr__(provenance, "source_kind", "")
            object.__setattr__(provenance, "origin_ref", "")
            object.__setattr__(provenance, "retrieved_at", self._now_fn())
            object.__setattr__(provenance, "license_class", "")
            document = object.__new__(CorpusDocument)
            object.__setattr__(document, "content", self._fixture.content)
            object.__setattr__(document, "provenance", provenance)
            return document
        return CorpusMiss(id=id)
