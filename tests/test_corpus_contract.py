"""Conformance tests for the two-verb corpus contract.

Runs the conformance kit against both reference adapters (twin notes and
hosted documents) plus the broken-adapter red-proof.  Each adapter is
tested with a realistic fixture corpus seeded into an in-memory reader.

SPR-07/08 will import the conformance helpers to validate their own
adapters against the same bar.
"""

from __future__ import annotations

import datetime
import pathlib
import sys
import tempfile
from typing import Any

import pytest

from substrate.corpus_contract.adapters.hosted_docs import HostedDocsCorpusAdapter
from substrate.corpus_contract.adapters.twin_notes import TwinNotesCorpusAdapter
from substrate.corpus_contract.conformance import (
    BrokenProvenanceAdapter,
    FixtureDoc,
    assert_corpus_conformance,
    assert_empty_query_returns_no_hits,
    assert_fetch_determinism,
    assert_fetch_roundtrip,
    assert_miss_has_id,
    assert_provenance_completeness,
    assert_read_only,
    assert_search_retrieval,
    assert_unknown_id_returns_miss,
)
from substrate.corpus_contract.protocol import (
    CorpusContractError,
    CorpusDocument,
    CorpusHit,
    CorpusMiss,
    Provenance,
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


# Fixed clock for deterministic testing — the kit never relies on wall time.
def _fixed_now() -> datetime.datetime:
    return datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


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
    return TwinNotesCorpusAdapter(reader, asset_id="asset-1", now_fn=_fixed_now)


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
    return HostedDocsCorpusAdapter(reader, owner_id="owner-1", now_fn=_fixed_now)


# ---------------------------------------------------------------------------
# Twin-notes adapter conformance
# ---------------------------------------------------------------------------


class TestTwinNotesConformance:
    def test_search_retrieval(self) -> None:
        adapter = _make_twin_adapter()
        assert_search_retrieval(adapter, TWIN_FIXTURE, decoy_ids=frozenset({"twin_other"}))

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

    def test_fetch_determinism(self) -> None:
        adapter = _make_twin_adapter()
        assert_fetch_determinism(adapter, TWIN_FIXTURE)


class TestHostedDocsConformance:
    def test_search_retrieval(self) -> None:
        adapter = _make_hosted_adapter()
        assert_search_retrieval(adapter, HOSTED_FIXTURE, decoy_ids=frozenset({"hdoc_other"}))

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

    def test_fetch_determinism(self) -> None:
        adapter = _make_hosted_adapter()
        assert_fetch_determinism(adapter, HOSTED_FIXTURE)

    def test_cross_owner_fetch_returns_miss(self) -> None:
        """A document belonging to owner-B must NOT be fetchable by an adapter
        scoped to owner-A.  The document EXISTS in the store (it is not an
        unknown-id miss) — the denial is purely an owner-scope enforcement.

        The adapter checks ``list_membership(owner_id)`` before calling
        ``get_document``; a document outside the declared owner's membership
        list returns ``CorpusMiss`` even though the store has it.
        """
        foreign_doc_id = "hdoc_belongs_to_owner_b"
        docs = {
            foreign_doc_id: {
                "document_id": foreign_doc_id,
                "owner_id": "owner-B",
                "book_id": "book-foreign",
                "content_hash": "foreign123",
                "title": "Foreign Owner Document",
                "license_class": "public_domain",
                "body_text": "This document exists in the store and belongs to owner-B.",
                "source_format": "text",
                "receipt_id": None,
                "view_format": "html",
            },
        }
        # owner-B owns the document; owner-A has an empty library.
        memberships: dict[str, list[str]] = {
            "owner-B": [foreign_doc_id],
            "owner-A": [],
        }
        reader = InMemoryHostedDocReader(docs, memberships)
        # Adapter scoped to owner-A — must NOT see owner-B's document.
        adapter_a = HostedDocsCorpusAdapter(reader, owner_id="owner-A", now_fn=_fixed_now)
        result = adapter_a.fetch(foreign_doc_id)
        assert isinstance(result, CorpusMiss), (
            f"cross-owner fetch of existing doc should return CorpusMiss, "
            f"got {type(result).__name__}"
        )


# ---------------------------------------------------------------------------
# Red-proof: broken adapter MUST fail the kit
# ---------------------------------------------------------------------------


class TestBrokenAdapterRedProof:
    def test_broken_provenance_fails_provenance_check(self) -> None:
        """A BrokenProvenanceAdapter (empty source_kind/origin_ref) MUST fail
        assert_provenance_completeness — proof the kit is not a rubber stamp.
        """
        broken = BrokenProvenanceAdapter(TWIN_FIXTURE, now_fn=_fixed_now)
        with pytest.raises(AssertionError, match="provenance"):
            assert_provenance_completeness(broken, TWIN_FIXTURE)

    def test_broken_adapter_still_passes_search(self) -> None:
        """The broken adapter does pass search (provenance is a fetch-time
        concern).  This is intentional: the red-proof targets provenance,
        not search.
        """
        broken = BrokenProvenanceAdapter(TWIN_FIXTURE, now_fn=_fixed_now)
        assert_search_retrieval(broken, TWIN_FIXTURE)

    def test_broken_adapter_passes_miss(self) -> None:
        broken = BrokenProvenanceAdapter(TWIN_FIXTURE, now_fn=_fixed_now)
        assert_unknown_id_returns_miss(broken)


# ---------------------------------------------------------------------------
# Negative static type proof — mypy MUST reject a wrong-signature adapter
# ---------------------------------------------------------------------------


class TestNegativeTypeProof:
    def test_mypy_rejects_wrong_signature_adapter(self) -> None:
        """Mypy MUST report a type error for a wrong-signature adapter
        assigned to CorpusAdapter.  If this test ever passes (mypy exits
        clean), the Protocol has lost its teeth — the test is designed to
        fail in that case.

        This is the negative static type proof that M1 demands: the
        Protocol rejects adapters whose signatures don't match.
        """
        import os
        import subprocess

        project_root = str(pathlib.Path(__file__).resolve().parent.parent)
        env = {**os.environ, "MYPYPATH": project_root}

        source = """\
from substrate.corpus_contract import CorpusAdapter
class Wrong:
    def search(self, query: int) -> list[str]: return []
    def fetch(self, id: int) -> str: return id
adapter: CorpusAdapter = Wrong()
"""
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "wrong_adapter.py"
            target.write_text(source)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mypy",
                    str(target),
                    "--strict",
                    "--no-error-summary",
                    "--ignore-missing-imports",
                    "--explicit-package-bases",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
        stdout = result.stdout
        stderr = result.stderr

        # mypy MUST find errors — the wrong-signature adapter must be rejected
        assert result.returncode != 0, (
            f"mypy did NOT reject the wrong-signature adapter "
            f"(exit code {result.returncode}).  The Protocol has lost its teeth.\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )
        assert "assignment" in stdout or "arg-type" in stdout or "override" in stdout, (
            f"mypy rejected the adapter but NOT for the expected reason.\n"
            f"Expected 'assignment', 'arg-type', or 'override' in output.\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )


@pytest.mark.parametrize("value", [None, 1, True, [], {}])
def test_hostile_query_and_id_types(value: object) -> None:
    adapter = _make_twin_adapter()
    with pytest.raises(CorpusContractError):
        adapter.search(value)  # type: ignore[arg-type]
    with pytest.raises(CorpusContractError):
        adapter.fetch(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("score", [True, 1, float("nan"), float("inf")])
def test_frozen_value_validation(score: object) -> None:
    with pytest.raises(CorpusContractError):
        CorpusHit(id="id", score=score, snippet="x")  # type: ignore[arg-type]


def test_other_forged_values_rejected() -> None:
    with pytest.raises(CorpusContractError):
        Provenance("kind", "ref", datetime.datetime(2026, 1, 1), "private")
    with pytest.raises(CorpusContractError):
        CorpusDocument("", Provenance("kind", "ref", _fixed_now(), "private"))


class WriteCapableTwinReader(InMemoryTwinNoteReader):
    def mutate(self) -> None:
        pass


def test_write_capable_reader_rejected_before_retention() -> None:
    reader = WriteCapableTwinReader([])
    with pytest.raises(CorpusContractError, match="callable surface"):
        TwinNotesCorpusAdapter(reader, "asset-1")


class WriteCapableHostedReader(InMemoryHostedDocReader):
    def mutate(self) -> None:
        pass


def test_write_capable_hosted_reader_rejected_before_retention() -> None:
    reader = WriteCapableHostedReader({}, {})
    with pytest.raises(CorpusContractError, match="callable surface"):
        HostedDocsCorpusAdapter(reader, "owner-1")


def test_twin_cross_scope_and_malformed_rows_fail_closed() -> None:
    class HostileTwinReader:
        def __init__(self, hostile: dict[str, Any]) -> None:
            self.hostile = hostile

        def list_twins(self, asset_id: str) -> list[dict[str, Any]]:
            return [self.hostile]

    row: dict[str, Any] = {
        "note_id": "n",
        "asset_id": "other",
        "kind": "k",
        "text": "secret",
        "source_spawn_id": None,
        "investigation_id": None,
    }
    adapter = TwinNotesCorpusAdapter(HostileTwinReader(row), "asset-1")
    with pytest.raises(CorpusContractError, match="scope"):
        adapter.search("secret")
    del row["kind"]
    with pytest.raises(CorpusContractError, match="frozen fields"):
        adapter.search("secret")


def test_hosted_hostile_owner_row_fails_closed() -> None:
    reader = InMemoryHostedDocReader(
        {
            HOSTED_FIXTURE.id: {
                "document_id": HOSTED_FIXTURE.id,
                "owner_id": "foreign",
                "book_id": "b",
                "content_hash": "h",
                "title": "deep-research doctrine",
                "license_class": "l",
                "body_text": "foreign secret",
                "source_format": "text",
                "receipt_id": None,
                "view_format": "html",
            }
        },
        {"owner-1": [HOSTED_FIXTURE.id]},
    )
    adapter = HostedDocsCorpusAdapter(reader, "owner-1", now_fn=_fixed_now)
    with pytest.raises(CorpusContractError, match="scope"):
        adapter.search("deep-research doctrine")


def test_duplicate_ids_and_tie_order() -> None:
    base = {
        "asset_id": "asset-1",
        "kind": "k",
        "text": "needle",
        "source_spawn_id": None,
        "investigation_id": None,
    }
    duplicate = TwinNotesCorpusAdapter(
        InMemoryTwinNoteReader([{**base, "note_id": "a"}, {**base, "note_id": "a"}]), "asset-1"
    )
    with pytest.raises(CorpusContractError, match="duplicate"):
        duplicate.search("needle")
    ordered = TwinNotesCorpusAdapter(
        InMemoryTwinNoteReader([{**base, "note_id": "b"}, {**base, "note_id": "a"}]), "asset-1"
    )
    assert [hit.id for hit in ordered.search("needle")] == ["a", "b"]


def test_title_only_match_has_bounded_matching_snippet() -> None:
    adapter = _make_hosted_adapter()
    hits = adapter.search("Deep Research Doctrine")
    assert hits and "deep research doctrine" in hits[0].snippet.casefold()
    assert len(hits[0].snippet) <= 200


def test_provenance_preserves_hosted_rights_and_twin_identity() -> None:
    hosted = _make_hosted_adapter().fetch(HOSTED_FIXTURE.id)
    twin = _make_twin_adapter().fetch(TWIN_FIXTURE.id)
    assert type(hosted) is CorpusDocument
    assert hosted.provenance.license_class == "public_domain"
    assert hosted.provenance.origin_ref == HOSTED_FIXTURE.id
    assert type(twin) is CorpusDocument
    assert twin.provenance.license_class == "operator_private"
    assert twin.provenance.origin_ref == TWIN_FIXTURE.id


@pytest.mark.parametrize(
    "clock",
    [
        lambda: datetime.datetime(2026, 1, 1),
        lambda: "now",
        lambda: datetime.datetime(
            2026, 1, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=1))
        ),
    ],
)
def test_unsafe_clocks_fail(clock: Any) -> None:
    reader = InMemoryTwinNoteReader(
        [
            {
                "note_id": TWIN_FIXTURE.id,
                "asset_id": "asset-1",
                "kind": "insight",
                "text": TWIN_FIXTURE.content,
                "source_spawn_id": None,
                "investigation_id": None,
            }
        ]
    )
    adapter = TwinNotesCorpusAdapter(reader, "asset-1", now_fn=clock)
    with pytest.raises(CorpusContractError, match="clock output"):
        adapter.fetch(TWIN_FIXTURE.id)


def _twin_factory(fixtures: tuple[FixtureDoc, ...]) -> TwinNotesCorpusAdapter:
    reader = InMemoryTwinNoteReader(
        [
            {
                "note_id": fixture.id,
                "asset_id": "factory-asset",
                "kind": "insight",
                "text": fixture.content,
                "source_spawn_id": None,
                "investigation_id": None,
            }
            for fixture in fixtures
        ]
    )
    return TwinNotesCorpusAdapter(reader, "factory-asset", now_fn=_fixed_now)


def _hosted_factory(fixtures: tuple[FixtureDoc, ...]) -> HostedDocsCorpusAdapter:
    rows = {
        fixture.id: {
            "document_id": fixture.id,
            "owner_id": "factory-owner",
            "book_id": f"book-{fixture.id}",
            "content_hash": f"hash-{fixture.id}",
            "title": f"Document {fixture.id}",
            "license_class": "private",
            "body_text": fixture.content,
            "source_format": "text",
            "receipt_id": None,
            "view_format": "html",
        }
        for fixture in fixtures
    }
    reader = InMemoryHostedDocReader(rows, {"factory-owner": [fixture.id for fixture in fixtures]})
    return HostedDocsCorpusAdapter(reader, "factory-owner", now_fn=_fixed_now)


@pytest.mark.parametrize("factory", [_twin_factory, _hosted_factory])
def test_mandatory_factory_level_conformance(factory: Any) -> None:
    assert_corpus_conformance(factory)


def test_factory_conformance_rejects_constant_fabricator() -> None:
    constant = _twin_factory((FixtureDoc("constant-id", "constant-query", "constant-query body"),))

    def ignores_fixture(_fixtures: tuple[FixtureDoc, ...]) -> TwinNotesCorpusAdapter:
        return constant

    with pytest.raises(AssertionError):
        assert_corpus_conformance(ignores_fixture)


class SearchOverride:
    """Exact two-verb adapter used to prove hostile search behavior fails."""

    def __init__(self, delegate: TwinNotesCorpusAdapter, mode: str) -> None:
        self._delegate = delegate
        self._mode = mode
        self._calls = 0

    def search(self, query: str) -> tuple[CorpusHit, ...]:
        hits = self._delegate.search(query)
        if not hits:
            return hits
        if self._mode == "phantom":
            return (*hits, CorpusHit("phantom", 0.1, query))
        if self._mode == "full-snippet":
            first = hits[0]
            return (CorpusHit(first.id, first.score, "x" * 201), *hits[1:])
        if self._mode == "reverse":
            return tuple(reversed(hits))
        if self._mode == "mutating":
            self._calls += 1
            return hits if self._calls == 1 else hits[:-1]
        raise AssertionError(f"unknown hostile mode {self._mode}")

    def fetch(self, id: str) -> CorpusDocument | CorpusMiss:
        return self._delegate.fetch(id)


@pytest.mark.parametrize("mode", ["phantom", "full-snippet", "reverse", "mutating"])
def test_factory_conformance_rejects_hostile_search_adapters(mode: str) -> None:
    def hostile(fixtures: tuple[FixtureDoc, ...]) -> SearchOverride:
        return SearchOverride(_twin_factory(fixtures), mode)

    with pytest.raises(AssertionError):
        assert_corpus_conformance(hostile)


def test_reader_introspection_does_not_execute_descriptors() -> None:
    invoked = False

    class DescriptorReader:
        def list_twins(self, asset_id: str) -> list[dict[str, Any]]:
            return []

        @property
        def detonate(self) -> None:
            nonlocal invoked
            invoked = True
            raise RuntimeError("must not execute")

    TwinNotesCorpusAdapter(DescriptorReader(), "asset")
    assert invoked is False
