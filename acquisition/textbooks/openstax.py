"""OpenStax open-textbook connector (SPR-05 M2).

OpenStax publishes peer-reviewed college textbooks under open licenses — the
overwhelming majority **CC-BY 4.0**, a handful CC-BY-NC-SA / CC-BY-SA. The
license is per-book authoritative metadata in the OpenStax catalog, so we read
each book's declared license string and route it through ``classify()`` (the
SPR-02 chokepoint) rather than assuming a uniform source license.

Discovery reads the OpenStax catalog record's ``license`` block — ``license.url``
(the canonical ``creativecommons.org/licenses/by/4.0`` URI) is what we hand to
classify(); ``license.name``/``license.version`` are the human label. The book's
full-text PDF (``...resources`` / ``...pdf_url``) is the body we ingest.

Compose, do not reimplement: discovery uses the shared ``ThrottledClient``
(SPR-03 ban-aware), the rights decision is ``classify()`` (SPR-02), the ingest
is ``ingest_textbook`` -> ``ingest_servable_book`` (SPR-01 staging target),
dedup keys on the catalog slug / ISBN (SPR-04, in the orchestrator).
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from ._common import SourceError, TextbookWork, ThrottledClient, ingest_textbook

logger = logging.getLogger("acquisition.textbooks.openstax")

# OpenStax exposes a public catalog JSON (the same data the openstax.org book
# grid renders). The exact host has moved over the catalog's history; this is
# the documented open catalog endpoint. Tests inject a fake client, so no live
# host is contacted in CI.
OPENSTAX_CATALOG_URL = "https://openstax.org/apps/cms/api/v2/pages/?type=books.Book&fields=*"


def _author(book: dict) -> Optional[str]:
    """Best-effort author/editor string from the catalog record."""
    authors = book.get("authors") or book.get("senior_authors") or []
    if isinstance(authors, list):
        names = [
            (a.get("value", {}).get("name") if isinstance(a, dict) else None)
            or (a.get("name") if isinstance(a, dict) else None)
            or (a if isinstance(a, str) else None)
            for a in authors
        ]
        names = [n for n in names if n]
        if names:
            return "; ".join(names)
    return None


def _declared_license(book: dict) -> Optional[str]:
    """Read the book's DECLARED license string from the catalog record.

    Prefers the canonical CC URI (``license.url``); falls back to a license
    name/code. Returns it verbatim — classify() resolves it against the CC
    table. ``None`` when the record carries no license, which classify() gates
    by default (we never round an unknown license up to servable)."""
    lic = book.get("license")
    if isinstance(lic, dict):
        url = lic.get("url") or lic.get("license_url")
        if url:
            return str(url)
        name = lic.get("name") or lic.get("license_name")
        if name:
            return str(name)
    if isinstance(lic, str):
        return lic
    # Some catalog records carry a flat ``license_url`` / ``license_name``.
    url = book.get("license_url")
    if url:
        return str(url)
    name = book.get("license_name")
    return str(name) if name else None


def _pdf_url(book: dict) -> Optional[str]:
    """The book's full-text PDF URL from the catalog record."""
    for key in ("high_resolution_pdf_url", "low_resolution_pdf_url", "pdf_url"):
        url = book.get(key)
        if isinstance(url, str) and url:
            return url
    return None


def _to_work(book: dict) -> Optional[TextbookWork]:
    title = (book.get("title") or book.get("book_title") or "").strip()
    if not title:
        logger.info("openstax book %s skipped: no title", book.get("id"))
        return None
    pdf_url = _pdf_url(book)
    if not pdf_url:
        logger.info("openstax book %r skipped: no PDF url", title)
        return None
    slug = str(book.get("slug") or book.get("id") or title)
    return TextbookWork(
        source="openstax",
        source_id=slug,
        title=title,
        author=_author(book),
        source_uri=(
            book.get("webview_rex_link")
            or f"https://openstax.org/details/books/{slug}"
        ),
        download_url=pdf_url,
        declared_license=_declared_license(book),
        isbn=(book.get("print_isbn_13") or book.get("isbn13") or None),
        subjects=tuple(
            s for s in (book.get("subjects") or ()) if isinstance(s, str)
        ),
        source_declaration={},
    )


def discover(
    client: ThrottledClient, *, limit: int = 25
) -> list[TextbookWork]:
    """Discover OpenStax textbooks from the open catalog.

    Returns up to ``limit`` candidates, each carrying its DECLARED license
    string (read from the catalog ``license`` block) for classify() to resolve.
    A record with no title or no PDF url is logged and skipped — never
    fabricated. Network failures raise ``SourceError`` for the caller to handle
    per-batch (the orchestrator isolates a source's discovery failure)."""
    page = client.get_json(OPENSTAX_CATALOG_URL)
    items = page.get("items") or page.get("results") or page.get("books") or []
    out: list[TextbookWork] = []
    for book in items:
        if len(out) >= limit:
            break
        if not isinstance(book, dict):
            continue
        work = _to_work(book)
        if work is not None:
            out.append(work)
    return out


__all__ = [
    "OPENSTAX_CATALOG_URL",
    "discover",
    "ingest_textbook",
    "SourceError",
    "TextbookWork",
    "ThrottledClient",
]
