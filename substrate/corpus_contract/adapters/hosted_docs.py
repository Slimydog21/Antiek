"""Invariant-safe, read-only hosted-document corpus adapter."""

from __future__ import annotations

import datetime
import inspect
from collections.abc import Callable, Sequence
from typing import Any, Protocol, TypedDict, cast

from ..protocol import (
    CorpusContractError,
    CorpusDocument,
    CorpusHit,
    CorpusMiss,
    FetchResult,
    Provenance,
    validate_utc,
)

_KEYS = frozenset(
    {
        "document_id",
        "owner_id",
        "book_id",
        "content_hash",
        "title",
        "license_class",
        "body_text",
        "source_format",
        "receipt_id",
        "view_format",
    }
)
_OPTIONAL = frozenset({"receipt_id"})
_MAX = 200


class HostedDocReader(Protocol):
    def get_document(self, document_id: str) -> dict[str, Any] | None: ...
    def list_membership(self, owner_id: str) -> list[str]: ...


class HostedRow(TypedDict):
    document_id: str
    owner_id: str
    book_id: str
    content_hash: str
    title: str
    license_class: str
    body_text: str
    source_format: str
    receipt_id: str | None
    view_format: str


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise CorpusContractError(f"{field} must be a nonempty exact str")
    return value


def _reader(reader: object) -> None:
    public = {
        name
        for name in dir(reader)
        if not name.startswith("_")
        and callable(inspect.getattr_static(reader, name))
    }
    expected = {"get_document", "list_membership"}
    if public != expected:
        raise CorpusContractError(
            f"reader callable surface must be exactly {sorted(expected)}; got {sorted(public)}"
        )


def _row(value: object, requested: str, owner: str) -> HostedRow:
    if type(value) is not dict or frozenset(value) != _KEYS:
        raise CorpusContractError("hosted row must be an exact dict with frozen fields")
    row = value
    for key in _KEYS - _OPTIONAL:
        _text(row[key], key)
    if row["receipt_id"] is not None and (
        type(row["receipt_id"]) is not str or not row["receipt_id"]
    ):
        raise CorpusContractError("receipt_id must be None or nonempty exact str")
    if row["document_id"] != requested or row["owner_id"] != owner:
        raise CorpusContractError("hosted row id/owner escaped requested scope")
    return cast(HostedRow, row)


def _snippet(title: str, body: str, query: str) -> str:
    source = body if query.casefold() in body.casefold() else title
    at = source.casefold().find(query.casefold())
    start = max(0, at - 80)
    end = min(len(source), start + _MAX)
    start = max(0, end - _MAX)
    return source[start:end]


class HostedDocsCorpusAdapter:
    def __init__(
        self,
        reader: object,
        owner_id: str,
        *,
        now_fn: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        _reader(reader)
        self._owner_id = _text(owner_id, "owner_id")
        self.__reader = cast(HostedDocReader, reader)
        self._now_fn = now_fn or (lambda: datetime.datetime.now(datetime.UTC))

    def _membership(self) -> tuple[str, ...]:
        raw = self.__reader.list_membership(self._owner_id)
        if type(raw) is not list:
            raise CorpusContractError("list_membership must return an exact list")
        ids = tuple(_text(item, "membership document id") for item in raw)
        if len(ids) != len(set(ids)):
            raise CorpusContractError("duplicate membership document id")
        return ids

    def _document(self, id: str) -> HostedRow | None:
        raw = self.__reader.get_document(id)
        return None if raw is None else _row(raw, id, self._owner_id)

    def search(self, query: str) -> Sequence[CorpusHit]:
        if type(query) is not str:
            raise CorpusContractError("query must be an exact str")
        q = query.strip()
        if not q:
            return ()
        hits: list[CorpusHit] = []
        for id in self._membership():
            row = self._document(id)
            if row is None:
                raise CorpusContractError("membership references missing document")
            combined = f"{row['title']}\n{row['body_text']}"
            if q.casefold() in combined.casefold():
                hits.append(
                    CorpusHit(
                        id=id,
                        score=float(len(q)) / len(combined),
                        snippet=_snippet(row["title"], row["body_text"], q),
                    )
                )
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.id)))

    def fetch(self, id: str) -> FetchResult:
        wanted = _text(id, "id")
        if wanted not in self._membership():
            return CorpusMiss(id=wanted)
        row = self._document(wanted)
        if row is None:
            raise CorpusContractError("membership references missing document")
        return CorpusDocument(
            content=row["body_text"],
            provenance=Provenance(
                source_kind="hosted_document",
                origin_ref=wanted,
                retrieved_at=validate_utc(self._now_fn(), "clock output"),
            ),
        )
