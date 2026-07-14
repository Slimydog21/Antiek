"""Bounded lexical retrieval over signed, advisory twin documents.

Search remains a pure local operation. It indexes only non-withheld
``TwinDocument`` values produced by the signed generation boundary, carries the
advisory authority and receipt identity into every hit, and never promotes model
notes into canonical graph provenance.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, final

from .generate import (
    MAX_IDENTIFIER_CHARS,
    MAX_INSIGHTS,
    MAX_PROPOSAL_ITEM_CHARS,
    MAX_QUESTIONS,
    TWIN_AUTHORITY,
    TwinDocument,
    TwinGenerationError,
    verify_twin_document,
)

SearchKind = Literal["insight", "question"]

MAX_SEARCH_DOCUMENTS = 10_000
MAX_SEARCH_RECORDS = 100_000
MAX_SEARCH_TOTAL_CHARS = 5_000_000
MAX_QUERY_CHARS = 2_000
MAX_QUERY_TERMS = 100
MAX_SEARCH_LIMIT = 100
MAX_TOKEN_CHARS = 256

_VALID_KINDS = frozenset({"insight", "question"})
_TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TwinSearchError(ValueError):
    """A search input violates a bounded advisory-search invariant."""


def _canonical_identifier(name: str, value: object) -> str:
    if type(value) is not str:
        raise TwinSearchError(f"{name} must be an exact string")
    if len(value) > MAX_IDENTIFIER_CHARS or not value or value != value.strip():
        raise TwinSearchError(f"{name} must be canonical and within its ceiling")
    return value


def _sha256(name: str, value: object) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        raise TwinSearchError(f"{name} must be a canonical sha256 digest")
    return value


def _tokenize(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(
        token
        for token in _TOKEN_RE.findall(normalized)
        if len(token) <= MAX_TOKEN_CHARS
    )


@dataclass(frozen=True, init=False)
class TwinSearchRecord:
    """One immutable advisory item derived from a materialized twin.

    Receipt fields are generation evidence carried for audit. They are not graph
    provenance and do not make the proposed text a canonical insight or question.
    """

    asset_id: str
    record_id: str
    kind: SearchKind
    text: str
    authority: str
    model_id: str
    receipt_id: str
    budget_authority_id: str
    source_content_hash: str
    proposal_hash: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TwinSearchError("TwinSearchRecord values are created only by TwinIndex.build")

    @classmethod
    def _from_twin(
        cls,
        document: TwinDocument,
        *,
        kind: SearchKind,
        position: int,
        text: str,
    ) -> TwinSearchRecord:
        identity = f"{document.proposal_hash}\0{kind}\0{position}".encode()
        record = object.__new__(cls)
        values: dict[str, object] = {
            "asset_id": document.asset_id,
            "record_id": f"twin-item-{hashlib.sha256(identity).hexdigest()}",
            "kind": kind,
            "text": text,
            "authority": document.authority,
            "model_id": document.model_id,
            "receipt_id": document.receipt_id,
            "budget_authority_id": document.budget_authority_id,
            "source_content_hash": document.source_content_hash,
            "proposal_hash": document.proposal_hash,
        }
        for name, value in values.items():
            object.__setattr__(record, name, value)
        return record


@dataclass(frozen=True)
class TwinSearchHit:
    """One ranked advisory result with an immutable scoring explanation."""

    record: TwinSearchRecord
    score: float
    matched_terms: tuple[str, ...]
    term_frequency: Mapping[str, int]


@final
@dataclass(frozen=True, init=False)
class TwinIndex:
    """Immutable inverted index built only from validated ``TwinDocument`` values."""

    records: tuple[TwinSearchRecord, ...]
    _by_id: Mapping[str, TwinSearchRecord]
    _term_freq: Mapping[str, Mapping[str, int]]
    _doc_freq: Mapping[str, int]
    _kind_index: Mapping[str, frozenset[str]]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TwinSearchError("construct indexes with TwinIndex.build")

    @classmethod
    def build(
        cls,
        documents: list[TwinDocument] | tuple[TwinDocument, ...],
    ) -> TwinIndex:
        if type(documents) not in (list, tuple):
            raise TwinSearchError("documents must be an exact list or tuple")
        if len(documents) > MAX_SEARCH_DOCUMENTS:
            raise TwinSearchError("document count exceeds the search-index ceiling")
        snapshot = tuple(documents)

        records: list[TwinSearchRecord] = []
        total_chars = 0
        for document in snapshot:
            cls._validate_document(document)
            collections: tuple[tuple[SearchKind, tuple[str, ...]], ...] = (
                ("insight", document.proposed_insights),
                ("question", document.proposed_questions),
            )
            for kind, values in collections:
                for position, text in enumerate(values):
                    total_chars += len(text)
                    if total_chars > MAX_SEARCH_TOTAL_CHARS:
                        raise TwinSearchError("twin text exceeds the aggregate index ceiling")
                    records.append(
                        TwinSearchRecord._from_twin(
                            document,
                            kind=kind,
                            position=position,
                            text=text,
                        )
                    )
                    if len(records) > MAX_SEARCH_RECORDS:
                        raise TwinSearchError("record count exceeds the search-index ceiling")

        by_id: dict[str, TwinSearchRecord] = {}
        term_freq: dict[str, dict[str, int]] = {}
        doc_freq: dict[str, int] = {}
        kind_index: dict[str, set[str]] = {}
        for record in records:
            if record.record_id in by_id:
                raise TwinSearchError("duplicate twin proposal cannot be indexed twice")
            by_id[record.record_id] = record
            kind_index.setdefault(record.kind, set()).add(record.record_id)
            seen: set[str] = set()
            for token in _tokenize(record.text):
                postings = term_freq.setdefault(token, {})
                postings[record.record_id] = postings.get(record.record_id, 0) + 1
                seen.add(token)
            for term in seen:
                doc_freq[term] = doc_freq.get(term, 0) + 1

        index = object.__new__(cls)
        object.__setattr__(index, "records", tuple(records))
        object.__setattr__(index, "_by_id", MappingProxyType(dict(by_id)))
        object.__setattr__(
            index,
            "_term_freq",
            MappingProxyType(
                {term: MappingProxyType(dict(postings)) for term, postings in term_freq.items()}
            ),
        )
        object.__setattr__(index, "_doc_freq", MappingProxyType(dict(doc_freq)))
        object.__setattr__(
            index,
            "_kind_index",
            MappingProxyType({kind: frozenset(ids) for kind, ids in kind_index.items()}),
        )
        return index

    @staticmethod
    def _validate_document(document: TwinDocument) -> None:
        if type(document) is not TwinDocument:
            raise TwinSearchError("documents must be exact TwinDocument values")
        try:
            verify_twin_document(document)
        except TwinGenerationError as exc:
            raise TwinSearchError(str(exc)) from exc
        if type(document.withheld) is not bool or document.withheld:
            raise TwinSearchError("withheld twins cannot enter the search index")
        if document.authority != TWIN_AUTHORITY:
            raise TwinSearchError("twin authority must remain advisory")
        _canonical_identifier("asset_id", document.asset_id)
        _canonical_identifier("model_id", document.model_id)
        _canonical_identifier("receipt_id", document.receipt_id)
        _canonical_identifier("budget_authority_id", document.budget_authority_id)
        _sha256("source_content_hash", document.source_content_hash)
        _sha256("proposal_hash", document.proposal_hash)
        if type(document.proposed_insights) is not tuple:
            raise TwinSearchError("proposed insights must be an exact tuple")
        if type(document.proposed_questions) is not tuple:
            raise TwinSearchError("proposed questions must be an exact tuple")
        if len(document.proposed_insights) > MAX_INSIGHTS:
            raise TwinSearchError("twin exceeds the insight count ceiling")
        if len(document.proposed_questions) > MAX_QUESTIONS:
            raise TwinSearchError("twin exceeds the question count ceiling")
        for text in (*document.proposed_insights, *document.proposed_questions):
            if type(text) is not str:
                raise TwinSearchError("twin items must be exact strings")
            if len(text) > MAX_PROPOSAL_ITEM_CHARS:
                raise TwinSearchError("twin item exceeds the per-item ceiling")
            if not text or text != text.strip():
                raise TwinSearchError("twin items must be non-empty canonical strings")

    @property
    def size(self) -> int:
        return len(self.records)

    def _idf(self, term: str) -> float:
        return math.log(1 + self.size / (1 + self._doc_freq.get(term, 0)))


def search_twins(
    index: TwinIndex,
    query: str,
    *,
    limit: int = 10,
    kind_filter: str | None = None,
) -> tuple[TwinSearchHit, ...]:
    """Return immutable, auditable lexical hits without mutating the index."""
    if type(index) is not TwinIndex:
        raise TwinSearchError("index must be an exact TwinIndex value")
    if type(query) is not str:
        raise TwinSearchError("query must be an exact string")
    if len(query) > MAX_QUERY_CHARS:
        raise TwinSearchError("query exceeds the search ceiling")
    if type(limit) is not int:
        raise TwinSearchError("limit must be an exact integer")
    if limit <= 0:
        return ()
    if limit > MAX_SEARCH_LIMIT:
        raise TwinSearchError("limit exceeds the search ceiling")
    if kind_filter is not None and type(kind_filter) is not str:
        raise TwinSearchError("kind_filter must be a string or None")
    if kind_filter is not None and kind_filter not in _VALID_KINDS:
        return ()

    terms = tuple(dict.fromkeys(_tokenize(query)))
    if not terms:
        return ()
    if len(terms) > MAX_QUERY_TERMS:
        raise TwinSearchError("query contains too many distinct terms")

    candidate_ids: set[str] = set()
    for term in terms:
        candidate_ids.update(index._term_freq.get(term, ()))
    if kind_filter is not None:
        candidate_ids.intersection_update(index._kind_index.get(kind_filter, frozenset()))

    hits: list[TwinSearchHit] = []
    for record_id in candidate_ids:
        record = index._by_id[record_id]
        frequencies: dict[str, int] = {}
        score = 0.0
        for term in terms:
            frequency = index._term_freq.get(term, {}).get(record_id, 0)
            if frequency:
                frequencies[term] = frequency
                score += frequency * index._idf(term)
        if frequencies:
            hits.append(
                TwinSearchHit(
                    record=record,
                    score=score,
                    matched_terms=tuple(sorted(frequencies)),
                    term_frequency=MappingProxyType(dict(frequencies)),
                )
            )

    hits.sort(key=lambda hit: (-hit.score, hit.record.record_id))
    return tuple(hits[:limit])


__all__ = [
    "MAX_QUERY_CHARS",
    "MAX_QUERY_TERMS",
    "MAX_SEARCH_DOCUMENTS",
    "MAX_SEARCH_LIMIT",
    "MAX_SEARCH_RECORDS",
    "MAX_SEARCH_TOTAL_CHARS",
    "SearchKind",
    "TwinIndex",
    "TwinSearchError",
    "TwinSearchHit",
    "TwinSearchRecord",
    "search_twins",
]
