"""Layered PDF-vs-HTML-landing-page detection for the open-access fetch path.

The 2026-05-29 prod run found 6 of 15 OA "PDF" links were really HTML landing
pages or publisher paywalls served 200-OK — their bytes began ``b'<!DO'``
(``<!DOCTYPE html>``). Handing those to the PDF reader as if they were a
document either crashes the parser or, worse, lands a 0-word husk that looks
like a real rights decision. #23 added a content-type + ``%PDF-`` magic-byte
sniff inline in ``unpaywall.download_pdf`` and ``pmc.download_pdf`` (the
private ``_looks_like_pdf`` helper, duplicated across the two). This module
consolidates that single detection into ONE shared, public, layered check and
adds the third signal #23 lacked: a pdf-parse failure.

The three layers, in order of cost:

  1. ``Content-Type`` — a ``text/html`` or ``text/plain`` body is rejected
     immediately (cheapest, no byte inspection). A missing/ambiguous
     content-type does NOT pass on its own — many landing pages omit it.
  2. Magic bytes — a real PDF begins ``%PDF-`` (leading whitespace tolerated);
     HTML begins ``<!DO`` / ``<htm`` / ``<?xm``. This catches the exact prod
     case and any other non-PDF body regardless of content-type.
  3. pdf-parse — for bytes that pass (1) and (2), confirm ``pypdf`` can open
     them. A truncated or corrupt PDF that begins ``%PDF-`` but cannot be
     parsed is the final reject signal, so a half-downloaded file never enters
     the corpus as a document.

A failed item is a COUNTED per-item rejection (``NotAPdf``), never a crash and
never an ingest. The check runs BEFORE any extraction/chunking so a landing
page never reaches the substrate or the extraction-quality gate as if it were
a document.
"""

from __future__ import annotations


class NotAPdf(ValueError):
    """The fetched bytes are not a usable PDF (HTML landing page, paywall, or
    a corrupt/truncated PDF). A counted, recoverable failure mode: the caller
    records a per-item miss and tries the next candidate URL rather than
    aborting the item or the run.

    Subclasses ``ValueError`` so ``OAThrottle.run_with_retry`` re-raises it
    immediately — a landing page will not become a PDF on retry, so it must
    not burn the retry budget.
    """


# A real PDF file begins with the ``%PDF-`` signature (per the PDF spec; the
# 5-byte ``%PDF-`` header is mandatory). Leading whitespace/BOM is tolerated
# because some servers prepend a stray newline.
_PDF_MAGIC = b"%PDF-"

# Leading bytes that positively identify an HTML/XML body — the landing-page
# signatures the prod run hit. Matched case-insensitively on the lstrip'd head.
_HTML_PREFIXES = (b"<!do", b"<html", b"<htm", b"<?xml", b"<head", b"<body")

# How many leading bytes to inspect for the magic-byte sniff. 1KB is plenty to
# clear leading whitespace and any short prologue without copying a large body.
_SNIFF_BYTES = 1024


def looks_like_pdf_bytes(content: bytes) -> bool:
    """Layer 2 only: do the leading bytes look like a PDF (``%PDF-``) and NOT
    like HTML? Pure, no parsing. Exposed for callers/tests that have only the
    bytes (no response headers)."""
    head = content[:_SNIFF_BYTES].lstrip()
    low = head[:16].lower()
    if any(low.startswith(p) for p in _HTML_PREFIXES):
        return False
    return head.startswith(_PDF_MAGIC)


def _parses_as_pdf(content: bytes) -> bool:
    """Layer 3: can ``pypdf`` open these bytes? A ``%PDF-``-prefixed but
    truncated/corrupt body fails here. ``pypdf`` is the in-tree parser the
    books reader already uses — no new dependency. Any parse exception (the
    library raises a variety) is treated as "not a usable PDF"."""
    import io

    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - pypdf is the [pdf] extra
        # If the parser is unavailable we cannot run layer 3; layers 1+2 stand
        # on their own. Treat as "parseable" so we do not reject a real PDF
        # merely because the optional extra is missing in some environment.
        return True
    try:
        reader = PdfReader(io.BytesIO(content))
        # Touch the page tree: a header-only or structurally-broken PDF that
        # PdfReader accepts lazily still fails when we enumerate pages.
        _ = len(reader.pages)
    except Exception:
        return False
    return True


def assert_pdf(
    content: bytes,
    *,
    content_type: str | None = None,
    url: str | None = None,
    parse_check: bool = True,
) -> None:
    """Run all three layers; raise ``NotAPdf`` (with a specific reason) on the
    first that rejects. Returns ``None`` when the bytes are a usable PDF.

    ``parse_check=False`` skips layer 3 (the pypdf open) for callers that only
    need the cheap header sniff — but the default fetch path runs all three so
    a truncated PDF is caught before ingest.
    """
    where = f" ({url})" if url else ""

    # Layer 1 — content-type.
    if content_type:
        ct = content_type.lower()
        if "application/pdf" not in ct and ("text/html" in ct or "text/plain" in ct):
            raise NotAPdf(
                f"non-PDF Content-Type {content_type!r}{where} — likely an "
                "HTML landing page or paywall, not a PDF"
            )

    # Layer 2 — magic bytes.
    head = content[:_SNIFF_BYTES].lstrip()
    low = head[:16].lower()
    if any(low.startswith(p) for p in _HTML_PREFIXES):
        raise NotAPdf(
            f"HTML/XML leading bytes {content[:8]!r}{where} — a landing page "
            "served where a PDF was expected"
        )
    if not head.startswith(_PDF_MAGIC):
        raise NotAPdf(
            f"missing %PDF- signature (head={content[:8]!r}){where} — not a PDF"
        )

    # Layer 3 — pdf-parse.
    if parse_check and not _parses_as_pdf(content):
        raise NotAPdf(
            f"%PDF- header present but pypdf could not parse the body{where} — "
            "truncated or corrupt PDF"
        )


def is_pdf(
    content: bytes,
    *,
    content_type: str | None = None,
    parse_check: bool = True,
) -> bool:
    """Boolean form of :func:`assert_pdf` for callers that want a predicate
    rather than an exception."""
    try:
        assert_pdf(content, content_type=content_type, parse_check=parse_check)
    except NotAPdf:
        return False
    return True
