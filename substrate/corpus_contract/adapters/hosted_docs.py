"""Reference adapter: hosted documents corpus.

Read-only adapter over the hosted-document store shape (the HTML-first
document model from ``substrate.marketplace_host``).  The injectable reader
mirrors the real store's fields (``document_id``, ``owner_id``, ``book_id``,
``content_hash``, ``title``, ``license_class``, ``body_text``,
``source_format``, ``receipt_id``, ``view_format``) — grep
``substrate.marketplace_host.host`` for the source of truth.

Search is honest substring matching over document body text; no embedding
dependency.  The adapter accepts a ``HostedDocReader`` (a read-only
protocol), never a ``HostStore`` with write capability.  Zero writes are
interface-proven.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from ..protocol import CorpusAdapter, CorpusDocument, CorpusHit, CorpusMiss, FetchResult, Provenance


@runtime_checkable
class HostedDocReader(Protocol):
    """Read-only view of the hosted-document store.

    Mirrors the read surface of ``HostStore`` + ``AccountLibrary`` but
    exposes NO write surface.  The adapter accepts this, not ``HostStore``,
    so zero writes are structural — not conventional.
    """

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Return a hosted-document dict, or None if not found."""
        ...

    def list_membership(self, owner_id: str) -> list[str]:
        """Return document_ids hosted under *owner_id*."""
        ...


def _snippet(text: str, query: str, *, radius: int = 80) -> str:
    """Extract a snippet around the first occurrence of *query* in *text*."""
    idx = text.lower().find(query.lower())
    if idx < 0:
        trimmed = text[: radius * 2]
        return trimmed + ("…" if len(text) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(text), idx + len(query) + radius)
    snippet = text[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + snippet + suffix


def _score(text: str, query: str) -> float:
    """Score relevance of *text* to *query* via substring matching."""
    q = query.lower()
    t = text.lower()
    if q not in t:
        return 0.0
    return round(len(q) / max(len(t), 1), 6)


class HostedDocsCorpusAdapter:
    """CorpusAdapter over hosted documents for a single owner.

    ``reader`` is injectable and read-only (``HostedDocReader`` protocol).
    ``owner_id`` scopes the corpus to one account's library.
    """

    def __init__(self, reader: HostedDocReader, owner_id: str) -> None:
        self._reader = reader
        self._owner_id = owner_id.strip()
        if not self._owner_id:
            raise ValueError("owner_id is required")

    def search(self, query: str) -> Sequence[CorpusHit]:
        """Lexical substring search over hosted-document body text.

        Returns hits ordered by descending score.  Empty query → no hits.
        Searches across all documents in the owner's library.
        """
        q = (query or "").strip()
        if not q:
            return ()
        doc_ids = self._reader.list_membership(self._owner_id)
        hits: list[CorpusHit] = []
        for doc_id in doc_ids:
            doc = self._reader.get_document(doc_id)
            if doc is None:
                continue
            body = str(doc.get("body_text") or "")
            title = str(doc.get("title") or doc_id)
            # Search body and title
            combined = f"{title}\n{body}"
            s = _score(combined, q)
            if s > 0:
                hits.append(
                    CorpusHit(
                        id=doc_id,
                        score=s,
                        snippet=_snippet(body, q),
                    )
                )
        hits.sort(key=lambda h: h.score, reverse=True)
        return tuple(hits)

    def fetch(self, id: str) -> FetchResult:
        """Fetch a hosted document by id, or return a typed miss."""
        doc = self._reader.get_document(id)
        if doc is None:
            return CorpusMiss(id=id)
        body = str(doc.get("body_text") or "")
        title = str(doc.get("title") or id)
        return CorpusDocument(
            content=body,
            provenance=Provenance(
                source_kind="hosted_document",
                origin_ref=f"{id} (title={title})",
                retrieved_at=datetime.datetime.now(datetime.timezone.utc),
            ),
        )
