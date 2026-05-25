"""Read workflow — book assets + servable-corpus legal gate (SPR-01).

Antiek's Read workflow is "Spotify for books, not Internet Archive": the
reading experience and the ad-economics engine ship now, but the *served
corpus* stays inside the legal gate. This package models a book as a
first-class readable asset over the existing ``documents`` table and
enforces — at the data layer — that only legally servable content is
served full text.

The load-bearing design decision (master-spec §9.0 / §9.10): servability
is a DERIVED PROJECTION over ``documents.content_class`` (the column the
chunk-search G1 gate already keys off in ``substrate/graph/search.py``)
plus a book-level takedown override. There is no second authoritative
servability column, because a parallel gate would drift from G1 and a
gate that drifts fails open.

Modules:

- ``servability`` — the (content_class, taken_down) → ServabilityStatus
  projection and the ``is_servable_full_text`` predicate. M2.
- ``model`` — the ``book_assets`` row (TOC, pagination, cover, takedown
  state) and its single-writer CRUD. M1 + M7.
- ``serve`` — the full-text serve path; deny-by-default allowlist gate
  reusing the content_class idiom. M3.
- ``takedown`` — flips a book to taken-down, purges cached full text,
  restricts retrieval, emits an audit event. M4.
- ``ingest`` — wraps ``acquisition/books`` to land a book with provenance,
  an ip_holder, and a deny-by-default content_class. M5.
"""

from __future__ import annotations

from .servability import (
    ServabilityStatus,
    is_servable_full_text,
    servability_of,
)

__all__ = [
    "ServabilityStatus",
    "servability_of",
    "is_servable_full_text",
]
