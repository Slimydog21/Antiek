"""Two-verb corpus contract — search + fetch.

Doctrine I-2: search returns ids + snippets (context economy); full documents
enter only via fetch, and only spans enter synthesis.  This keeps the
research-loop context window proportional to the hit set rather than the full
corpus.

Doctrine I-8: read-only by construction — the protocol exposes no write
surface; adapters accept injectable *readers*, not store handles with write
capability.

The protocol fits both the twin-note store (``note_id``, ``asset_id``,
``kind``, ``text``, ``source_spawn_id``, ``investigation_id``) and the
hosted-document store (``document_id``, ``owner_id``, ``book_id``,
``content_hash``, ``title``, ``license_class``, ``body_text``,
``source_format``, ``receipt_id``, ``view_format``).  Both stores forced
the same decision: ids are opaque strings (twin notes use ``twin_``-prefixed
hex digests; hosted docs use ``hdoc_``-prefixed hex digests), so the protocol
does not assume a numeric or UUID id shape.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CorpusHit:
    """One search result — id, relevance score, and a text snippet.

    Snippets are context-economy spans, not full documents.  The research loop
    uses them to decide which ids to ``fetch``.
    """

    id: str
    score: float
    snippet: str


@dataclass(frozen=True)
class Provenance:
    """Where a document came from — injected by the adapter at fetch time.

    ``source_kind`` identifies the corpus type (e.g. ``"twin_note"``,
    ``"hosted_document"``).  ``origin_ref`` is a corpus-specific locator
    (e.g. the asset_id for twin notes, the document_id for hosted docs).
    ``retrieved_at`` is UTC, injected at fetch via the adapter's
    ``now_fn`` clock — never stored, never read from the wall clock
    directly.
    """

    source_kind: str
    origin_ref: str
    retrieved_at: _dt.datetime


@dataclass(frozen=True)
class CorpusDocument:
    """A fetched document with content and provenance.

    ``content`` is the full text.  ``provenance`` carries source metadata
    injected by the adapter.
    """

    content: str
    provenance: Provenance


@dataclass(frozen=True)
class CorpusMiss:
    """Typed miss for ``fetch`` of an unknown id.

    Replaces a bare ``KeyError`` so callers handle misses explicitly.
    """

    id: str
    reason: str = "not found"


FetchResult = CorpusDocument | CorpusMiss


@runtime_checkable
class CorpusAdapter(Protocol):
    """The two-verb corpus contract.

    Any adapter conforming to this protocol is researchable by the deep-
    research loop.  ``search`` returns ranked hits with snippets; ``fetch``
    returns a full document with provenance, or a typed miss.

    Implementations MUST be read-only — no write method, no store handle with
    write capability exposed through the interface.
    """

    def search(self, query: str) -> Sequence[CorpusHit]:
        """Return ranked hits for *query*, each with a relevance score and snippet.

        An empty query returns no hits.  Results are ordered by descending
        ``score``.
        """
        ...

    def fetch(self, id: str) -> FetchResult:
        """Fetch a full document by id, or return a typed ``CorpusMiss``.

        ``id`` is an opaque string — the protocol assumes nothing about its
        shape.
        """
        ...
