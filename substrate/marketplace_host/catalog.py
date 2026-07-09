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
    """One catalog row: identity + license class + optional body for PD fixtures."""

    book_id: str
    title: str
    author: str
    source: str
    license_class: LicenseClass
    is_free: bool
    body_text: str = ""
    source_format: str = "html"  # "html" | "pdf" | "epub" | "text" — ingest source only


@dataclass
class Catalog:
    """In-process catalog. Search is substring over title/author/book_id."""

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
            hay = f"{e.book_id} {e.title} {e.author} {e.source}".lower()
            if q in hay:
                out.append(e)
        return sorted(out, key=lambda e: e.book_id)


def make_catalog(entries: list[CatalogEntry] | None = None) -> Catalog:
    cat = Catalog()
    for e in entries or []:
        cat.add(e)
    return cat
