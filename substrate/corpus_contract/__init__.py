"""Two-verb corpus contract — search + fetch.

Every Antiek corpus becomes researchable by exposing exactly
``search(query) → hits`` and ``fetch(id) → document``, proven by a reusable
conformance kit.

Doctrine W6: a deep-research loop needs exactly two verbs from any private
corpus.  That two-verb shape is also what makes "call arxiv, substack, and
other knowledge-dense publications into my deep researches" one uniform
mechanism instead of N integrations.

Public API:
    ``CorpusAdapter``  — the typing.Protocol (search + fetch)
    ``CorpusHit``      — one search result (id, score, snippet)
    ``CorpusDocument`` — a fetched document (content + provenance)
    ``CorpusMiss``     — typed miss for unknown ids
    ``Provenance``     — source_kind, origin_ref, retrieved_at
    ``FetchResult``    — ``CorpusDocument | CorpusMiss``
"""

from __future__ import annotations

from .protocol import (
    CorpusAdapter,
    CorpusDocument,
    CorpusHit,
    CorpusMiss,
    FetchResult,
    Provenance,
)

__all__ = [
    "CorpusAdapter",
    "CorpusDocument",
    "CorpusHit",
    "CorpusMiss",
    "FetchResult",
    "Provenance",
]
