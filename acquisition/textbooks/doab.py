"""DOAB / OAPEN open-access-books connector (SPR-05 M4).

The Directory of Open Access Books (DOAB) and OAPEN expose per-book metadata
with a PER-BOOK license (CC variants differ book to book). This connector reads
each book's declared license from its metadata and routes it through
``classify()`` (the SPR-02 chokepoint): CC-BY books -> ``source_declared_open``
(servable); NC/ND/unresolved -> the class SPR-02 dictates (gated), never
``public_domain``.

The 6/15-OA-landing-pages lesson is load-bearing here: a DOAB record advertises
a structured OA full-text URL, but some of those "PDF" links resolve to an HTML
landing page served 200-OK. ``ingest_textbook`` runs the SPR-03
extraction-quality gate (``acquisition.openaccess.pdf_detect.assert_pdf``) over
the fetched bytes BEFORE the reader sees them: bytes starting ``b'<!DO'``
(``<!DOCTYPE html>``) are rejected as a counted per-item miss, never ingested as
a book body.

Compose, do not reimplement: shared ``ThrottledClient`` (SPR-03 ban-aware),
``classify()`` (SPR-02), ``ingest_textbook`` -> ``ingest_servable_book``
(SPR-01 staging), dedup on DOI/ISBN/content-hash (SPR-04, orchestrator).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ._common import SourceError, TextbookWork, ThrottledClient, ingest_textbook

logger = logging.getLogger("acquisition.textbooks.doab")

# DOAB's public metadata API (the documented search/listing endpoint). Tests
# inject a fake client, so no live host is contacted in CI.
DOAB_SEARCH_URL = "https://directory.doabooks.org/rest/search"


def _field(meta: list[dict] | dict | None, key: str) -> Optional[str]:
    """Pull a Dublin-Core-style field value. DOAB records carry metadata either
    as a list of ``{'key': 'dc.title', 'value': ...}`` dicts (the REST shape) or
    as a flat mapping; handle both."""
    if isinstance(meta, dict):
        val = meta.get(key)
        if isinstance(val, list):
            for v in val:
                if v:
                    return str(v)
            return None
        return str(val) if val else None
    if isinstance(meta, list):
        for entry in meta:
            if isinstance(entry, dict) and entry.get("key") == key:
                val = entry.get("value")
                if val:
                    return str(val)
    return None


def _declared_license(record: dict, meta: Any) -> Optional[str]:
    """Read the per-book DECLARED license from the DOAB record.

    DOAB carries the license in ``dc.rights.uri`` / ``dc.rights`` (a
    ``creativecommons.org/licenses/...`` URI). Returns it verbatim for
    classify() to resolve; ``None`` when no license is declared (gated by
    default — we never round an unknown rights field up to servable)."""
    for key in ("dc.rights.uri", "oapen.relation.isLicensedBy", "dc.rights"):
        val = _field(meta, key)
        if val and "creativecommons.org" in val.lower():
            return val
    # Top-level flat fields some exports use.
    for key in ("license", "license_url", "rights"):
        val = record.get(key)
        if isinstance(val, str) and "creativecommons.org" in val.lower():
            return val
    # A bare license string (code) if present.
    for key in ("dc.rights", "rights"):
        val = _field(meta, key) if key == "dc.rights" else record.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _pdf_url(record: dict, meta: Any) -> Optional[str]:
    """The structured OA full-text URL the DOAB record advertises. Prefer an
    explicit bitstream/handle PDF; the extraction gate in ``ingest_textbook``
    catches a link that turns out to be an HTML landing page."""
    # REST records expose a bitstreams list.
    for bs in record.get("bitstreams") or ():
        if isinstance(bs, dict):
            name = (bs.get("name") or "").lower()
            url = bs.get("retrieveLink") or bs.get("url")
            if url and (name.endswith(".pdf") or bs.get("format") == "application/pdf"):
                return str(url)
    for key in ("pdf_url", "download_url", "fulltext_url"):
        url = record.get(key)
        if isinstance(url, str) and url:
            return url
    val = _field(meta, "oapen.identifier.ocn") or _field(meta, "dc.identifier.uri")
    return val


def _to_work(record: dict) -> Optional[TextbookWork]:
    meta = record.get("metadata", record)
    title = (_field(meta, "dc.title") or record.get("name") or record.get("title") or "").strip()
    if not title:
        logger.info("doab record %s skipped: no title", record.get("id"))
        return None
    pdf_url = _pdf_url(record, meta)
    if not pdf_url:
        logger.info("doab record %r skipped: no full-text URL", title)
        return None
    handle = str(record.get("handle") or record.get("id") or title)
    doi = _field(meta, "dc.identifier.doi") or record.get("doi")
    isbn = _field(meta, "dc.identifier.isbn") or record.get("isbn")
    publisher = _field(meta, "publisher.name") or _field(meta, "dc.publisher")
    return TextbookWork(
        source="doab",
        source_id=handle,
        title=title,
        author=_field(meta, "dc.contributor.author") or record.get("author"),
        source_uri=(
            _field(meta, "dc.identifier.uri")
            or f"https://directory.doabooks.org/handle/{handle}"
        ),
        download_url=pdf_url,
        declared_license=_declared_license(record, meta),
        isbn=isbn,
        subjects=tuple(),
        # A gated NC/ND book names its publisher so escrow can accrue to a
        # pre-onboarded holder (the existing ip_holders seam; accrual is not
        # disbursement, no money gate is touched).
        source_declaration=(
            {"rights_holder": publisher} if publisher else {}
        ),
    )


def discover(
    client: ThrottledClient, *, query: Optional[str] = None, limit: int = 25
) -> list[TextbookWork]:
    """Discover DOAB/OAPEN open-access books, each with its per-book declared
    license. Returns up to ``limit`` candidates; a record with no title or no
    full-text URL is logged and skipped. Network failures raise ``SourceError``
    for the caller."""
    params: dict = {"expand": "metadata,bitstreams"}
    if query:
        params["query"] = query
    page = client.get_json(DOAB_SEARCH_URL, params=params)
    records = page if isinstance(page, list) else (
        page.get("items") or page.get("results") or page.get("books") or []
    )
    out: list[TextbookWork] = []
    for record in records:
        if len(out) >= limit:
            break
        if not isinstance(record, dict):
            continue
        work = _to_work(record)
        if work is not None:
            out.append(work)
    return out


__all__ = [
    "DOAB_SEARCH_URL",
    "discover",
    "ingest_textbook",
    "SourceError",
    "TextbookWork",
    "ThrottledClient",
]
