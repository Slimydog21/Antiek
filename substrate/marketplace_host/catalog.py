"""Catalog entries with explicit license class (SPR-01).

``license_class`` is the honest answer to "why may this be hosted?":

* ``public_domain`` — free to host (PD connectors / known PD catalog)
* ``purchased`` — host only after a purchase receipt is recorded
* ``unknown`` — deny-by-default; host refuses without operator override

Fixtures only in tests; no network search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

LicenseClass = Literal["public_domain", "purchased", "unknown"]


@dataclass(frozen=True)
class CatalogEntry:
    """One catalog row: identity + license class + optional body for PD fixtures.

    Residual (lw): ``subjects`` are research-domain tags (science, philosophy, …)
    so the marketplace can filter knowledge-dense PD for workstation use.
    Empty subjects is valid (legacy / uncategorized).
    """

    book_id: str
    title: str
    author: str
    source: str
    license_class: LicenseClass
    is_free: bool
    body_text: str = ""
    source_format: str = "html"  # "html" | "pdf" | "epub" | "text" — ingest source only
    subjects: tuple[str, ...] = ()


@dataclass
class Catalog:
    """In-process catalog. Search is substring over title/author/book_id/source/subjects."""

    entries: dict[str, CatalogEntry] = field(default_factory=dict)

    def add(self, entry: CatalogEntry) -> CatalogEntry:
        if not entry.book_id.strip():
            raise ValueError("book_id is required")
        if entry.license_class not in ("public_domain", "purchased", "unknown"):
            raise ValueError(f"invalid license_class: {entry.license_class!r}")
        # Free only when public_domain; purchasable stubs must not claim free.
        if entry.license_class == "public_domain" and not entry.is_free:
            raise ValueError("public_domain entries must be is_free=True")
        if entry.license_class == "purchased" and entry.is_free:
            raise ValueError("purchased entries must not be is_free")
        # Residual (lw): normalize subjects to lowercase tokens (no empties, order-preserving unique).
        seen: set[str] = set()
        subjects_list: list[str] = []
        for s in entry.subjects or ():
            if not isinstance(s, str):
                continue
            token = s.strip().lower()
            if not token or token in seen:
                continue
            seen.add(token)
            subjects_list.append(token)
        subjects = tuple(subjects_list)
        if subjects != entry.subjects:
            entry = CatalogEntry(
                book_id=entry.book_id,
                title=entry.title,
                author=entry.author,
                source=entry.source,
                license_class=entry.license_class,
                is_free=entry.is_free,
                body_text=entry.body_text,
                source_format=entry.source_format,
                subjects=subjects,
            )
        self.entries[entry.book_id] = entry
        return entry

    def get(self, book_id: str) -> CatalogEntry | None:
        return self.entries.get(book_id)

    def search(self, query: str) -> list[CatalogEntry]:
        q = (query or "").strip().lower()
        if not q:
            return sorted(self.entries.values(), key=lambda e: e.book_id)
        out: list[CatalogEntry] = []
        for e in self.entries.values():
            # Residual (lw): subjects join the haystack for domain search.
            subj = " ".join(e.subjects)
            hay = f"{e.book_id} {e.title} {e.author} {e.source} {subj}".lower()
            if q in hay:
                out.append(e)
        return sorted(out, key=lambda e: e.book_id)

    def filter_by_subject(self, subject: str) -> list[CatalogEntry]:
        """Residual (lw): exact subject token match (normalized lowercase)."""
        token = (subject or "").strip().lower()
        if not token:
            return sorted(self.entries.values(), key=lambda e: e.book_id)
        out = [e for e in self.entries.values() if token in e.subjects]
        return sorted(out, key=lambda e: e.book_id)

    def filter_by_source(self, source: str) -> list[CatalogEntry]:
        """Residual (lx): exact knowledge-source match (case-insensitive).

        Parity with ``filter_by_subject`` so UI source chips and tests share
        one substrate contract. Empty source → all entries.
        """
        token = (source or "").strip().lower()
        if not token:
            return sorted(self.entries.values(), key=lambda e: e.book_id)
        out = [
            e
            for e in self.entries.values()
            if (e.source or "").strip().lower() == token
        ]
        return sorted(out, key=lambda e: e.book_id)


def make_catalog(entries: list[CatalogEntry] | None = None) -> Catalog:
    cat = Catalog()
    for e in entries or []:
        cat.add(e)
    return cat
