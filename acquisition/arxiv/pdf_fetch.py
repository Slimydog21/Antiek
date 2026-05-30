"""On-demand arXiv PDF fetch — rate-limited, ban-aware, %PDF-prechecked (SPR-04 M1).

This is the network half of SPR-04: pull ``arxiv.org/pdf/<id>`` on demand (never
prefetch — see below) through the SAME persisted cross-process throttle the
OAI-PMH harvester uses, reject anything that is not actually a PDF, and hand back
verified bytes + a checksum so the storage layer (M2) can record provenance.

Why ON-DEMAND, not prefetch (fairness bar 2 — steelman + refute)
----------------------------------------------------------------
"Prefetch every paper's PDF for serving speed" is the tempting alternative. It is
wrong twice over: (a) a full-corpus prefetch re-trips the exact IP-scoped 429 ban
the throttle exists to avoid (project_researchmaxx_arxiv.md, 2026-05-17 — the box
was banned by re-implemented throttling on a bulk sweep); and (b) most of the
corpus is T3 (arXiv-default license), whose body Antiek may NOT host — prefetching
would pull bytes we are not allowed to store. On-demand fetch of a SINGLE id, only
once its license has been gated to T1 by the storage layer, is the only compliant
shape. This module therefore fetches ONE id per call and assumes the caller has
already decided the paper is worth fetching; the tier gate lives in ``store.py``.

What this module DOES NOT re-implement (diligence bar 4)
-------------------------------------------------------
  * Rate limiting / the ban sentinel — REUSED from ``acquisition.arxiv.throttle``
    (``ArxivThrottle.request`` does the >=3s spacing + 429 ``banned_until``). On a
    ban this raises ``ArxivBanned`` and we DO NOT retry: re-hitting a banned
    endpoint is precisely what extends the ban. The exception propagates so the
    caller PAUSES the batch.
  * The %PDF magic-byte precheck — REUSED from ``acquisition.openaccess.unpaywall``
    (``_looks_like_pdf`` + ``NotAPdf``), the shared helper the connector-resilience
    work (PR #23) added on the open-access path. arXiv serves an HTML interstitial
    (a "withdrawn paper" / terms page) with a 200 when there is no PDF; that body
    must be rejected, never stored as if it were a document. We do not fork a
    second copy of the magic-byte logic.

What this module adds (the genuinely arXiv-PDF-specific part)
------------------------------------------------------------
  * A size guard: a PDF that is absurdly small (a truncated / error body that still
    happens to start ``%PDF-``) or absurdly large (a fetch gone wrong / a
    decompression bomb risk) is refused. The bounds are conservative — a real
    arXiv paper PDF is comfortably inside them.
  * A sha256 checksum of the verified bytes, returned so the storage layer can
    stamp it into provenance (defensibility bar 5: an arXiv compliance query can
    be answered from the stored row — source_url, sha256, byte_size).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

import httpx

from acquisition.arxiv.client import DEFAULT_TIMEOUT_S, DEFAULT_USER_AGENT
from acquisition.arxiv.throttle import ArxivBanned, ArxivThrottle  # noqa: F401  (re-export for callers)
from acquisition.openaccess.unpaywall import NotAPdf, _looks_like_pdf

# Conservative byte bounds for a single arXiv paper PDF. The lower bound rejects a
# truncated / error body that still starts with the magic bytes; the upper bound
# caps a runaway fetch (a real arXiv preprint PDF is well under 50 MB — the
# largest in the corpus are heavy-figure papers in the low tens of MB). These are
# guards against pathological inputs, not a content judgement.
MIN_PDF_BYTES = 1024  # 1 KiB — smaller than this is not a real paper PDF
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MiB


class PdfTooSmall(NotAPdf):
    """The fetched body passed the %PDF magic-byte check but is implausibly
    small for a real paper (a truncated / error body). Subclasses ``NotAPdf``
    so callers that already branch on "not a usable PDF" catch it for free, and
    so it is — like ``NotAPdf`` — a permanent (don't-retry) condition."""


class PdfTooLarge(NotAPdf):
    """The fetched body is larger than ``MAX_PDF_BYTES``. Refused rather than
    stored: an arXiv paper PDF this large is a fetch gone wrong, and storing it
    risks a decompression / memory blowup downstream."""


@dataclass(frozen=True)
class FetchedPdf:
    """Verified PDF bytes + the provenance the storage layer stamps onto the row.

    Every field here is what an arXiv-compliance query needs to answer "where did
    this body come from and is it the bytes we fetched": the canonical source URL,
    the sha256 of the exact bytes stored, and their size.
    """

    arxiv_id: str
    source_url: str
    content: bytes
    sha256: str
    byte_size: int


def _pdf_url(arxiv_id: str) -> str:
    """The canonical PDF URL for an arXiv id. Mirrors the client/adapter
    convention (``ArxivPaper.pdf_url`` and ``adapter._default_fetch_pdf``)."""
    return f"https://arxiv.org/pdf/{arxiv_id}"


def fetch_pdf(
    arxiv_id: str,
    *,
    throttle: ArxivThrottle,
    client: Optional[httpx.Client] = None,
    min_bytes: int = MIN_PDF_BYTES,
    max_bytes: int = MAX_PDF_BYTES,
) -> FetchedPdf:
    """Fetch one arXiv paper's PDF on demand, rate-limited and verified.

    The flow, in order, every gate fail-closed:

      1. ``throttle.request(send)`` — enforces >=3s spacing and raises
         ``ArxivBanned`` (which we DO NOT catch here) if a ban sentinel is
         active. The 429 ban-sentinel is recorded by ``note_response`` inside
         ``request``; we never re-attempt.
      2. ``raise_for_status`` — a non-2xx (404 for a withdrawn id, 5xx) raises
         ``httpx.HTTPStatusError`` so the caller records a per-item failure and
         leaves the row metadata-only (honesty bar 1: never fabricate a body).
      3. ``_looks_like_pdf`` — the shared %PDF magic-byte + content-type check.
         An HTML interstitial (arXiv's no-PDF terms page, served 200) is rejected
         with ``NotAPdf`` — NOT stored.
      4. size guard — reject implausibly small / large bodies.
      5. sha256 — checksum the verified bytes for provenance.

    ``throttle`` is REQUIRED (not defaulted) so a caller cannot accidentally
    fetch without the cross-process spacing/ban protection — the omission that
    IP-banned the box historically. ``client`` is injectable (tests pass an
    ``httpx.MockTransport`` client) so CI never touches the network; in prod a
    short-lived client is created per call with ``follow_redirects`` (arXiv 302s
    /pdf/<id> to the versioned PDF).
    """
    url = _pdf_url(arxiv_id)

    owns_client = client is None
    if owns_client:
        client = httpx.Client(follow_redirects=True)
    try:
        def _send() -> httpx.Response:
            return client.get(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=DEFAULT_TIMEOUT_S,
            )

        # throttle.request pairs wait_if_needed() BEFORE and note_response() AFTER
        # so a 429 records the ban sentinel and an active ban raises ArxivBanned
        # before the send. We deliberately let ArxivBanned propagate.
        resp = throttle.request(_send)
        resp.raise_for_status()
        content = resp.content
        content_type = resp.headers.get("content-type")
    finally:
        if owns_client:
            client.close()

    if not _looks_like_pdf(content, content_type):
        raise NotAPdf(
            f"arxiv.org/pdf/{arxiv_id} did not return a PDF (content-type="
            f"{content_type!r}, leading bytes={content[:8]!r}); likely an HTML "
            "interstitial for a withdrawn/absent paper. Not storing it as a body."
        )

    size = len(content)
    if size < min_bytes:
        raise PdfTooSmall(
            f"arxiv.org/pdf/{arxiv_id} returned {size} bytes (< {min_bytes}); "
            "implausibly small for a real paper PDF — likely a truncated/error "
            "body. Refusing to store."
        )
    if size > max_bytes:
        raise PdfTooLarge(
            f"arxiv.org/pdf/{arxiv_id} returned {size} bytes (> {max_bytes}); "
            "larger than any plausible arXiv paper PDF. Refusing to store."
        )

    digest = hashlib.sha256(content).hexdigest()
    return FetchedPdf(
        arxiv_id=arxiv_id,
        source_url=url,
        content=content,
        sha256=digest,
        byte_size=size,
    )


__all__ = [
    "FetchedPdf",
    "fetch_pdf",
    "NotAPdf",
    "PdfTooSmall",
    "PdfTooLarge",
    "ArxivBanned",
    "MIN_PDF_BYTES",
    "MAX_PDF_BYTES",
]
