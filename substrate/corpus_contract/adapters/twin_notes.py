"""Invariant-safe, read-only twin-note corpus adapter."""

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

_KEYS = frozenset({"note_id", "asset_id", "kind", "text", "source_spawn_id", "investigation_id"})
_SNIPPET_MAX = 200


class TwinNoteReader(Protocol):
    def list_twins(self, asset_id: str) -> list[dict[str, Any]]: ...


class TwinRow(TypedDict):
    note_id: str
    asset_id: str
    kind: str
    text: str
    source_spawn_id: str | None
    investigation_id: str | None


def _reader(reader: object) -> None:
    public = {
        name
        for name in dir(reader)
        if not name.startswith("_")
        and callable(inspect.getattr_static(reader, name))
    }
    if public != {"list_twins"}:
        raise CorpusContractError(
            f"reader callable surface must be exactly list_twins; got {sorted(public)}"
        )


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise CorpusContractError(f"{field} must be a nonempty exact str")
    return value


def _row(value: object, asset_id: str) -> TwinRow:
    if type(value) is not dict or frozenset(value) != _KEYS:
        raise CorpusContractError("twin row must be an exact dict with the frozen fields")
    row = value
    _text(row["note_id"], "note_id")
    _text(row["kind"], "kind")
    _text(row["text"], "text")
    if _text(row["asset_id"], "asset_id") != asset_id:
        raise CorpusContractError("twin row escaped asset scope")
    for key in ("source_spawn_id", "investigation_id"):
        if row[key] is not None and (type(row[key]) is not str or not row[key]):
            raise CorpusContractError(f"{key} must be None or nonempty exact str")
    return cast(TwinRow, row)


def _snippet(text: str, query: str) -> str:
    at = text.casefold().find(query.casefold())
    start = max(0, at - 80)
    end = min(len(text), start + _SNIPPET_MAX)
    start = max(0, end - _SNIPPET_MAX)
    return text[start:end]


class TwinNotesCorpusAdapter:
    def __init__(
        self,
        reader: object,
        asset_id: str,
        *,
        now_fn: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        _reader(reader)
        self._asset_id = _text(asset_id, "asset_id")
        self.__reader = cast(TwinNoteReader, reader)
        self._now_fn = now_fn or (lambda: datetime.datetime.now(datetime.UTC))

    def _rows(self) -> tuple[TwinRow, ...]:
        raw = self.__reader.list_twins(self._asset_id)
        if type(raw) is not list:
            raise CorpusContractError("list_twins must return an exact list")
        rows = tuple(_row(item, self._asset_id) for item in raw)
        ids = [str(row["note_id"]) for row in rows]
        if len(ids) != len(set(ids)):
            raise CorpusContractError("duplicate twin note_id")
        return rows

    def search(self, query: str) -> Sequence[CorpusHit]:
        if type(query) is not str:
            raise CorpusContractError("query must be an exact str")
        q = query.strip()
        if not q:
            return ()
        hits = [
            CorpusHit(
                id=row["note_id"],
                score=float(len(q)) / len(row["text"]),
                snippet=_snippet(row["text"], q),
            )
            for row in self._rows()
            if q.casefold() in row["text"].casefold()
        ]
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.id)))

    def fetch(self, id: str) -> FetchResult:
        wanted = _text(id, "id")
        for row in self._rows():
            if row["note_id"] == wanted:
                return CorpusDocument(
                    content=row["text"],
                    provenance=Provenance(
                        source_kind=f"twin_note:{row['kind']}",
                        origin_ref=self._asset_id,
                        retrieved_at=validate_utc(self._now_fn(), "clock output"),
                    ),
                )
        return CorpusMiss(id=wanted)
