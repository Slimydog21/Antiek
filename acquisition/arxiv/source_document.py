"""arXiv → structured ``Document`` (Reader SPR-02 M3) — prefer source over PDF.

This is the WIRING that connects the existing governed arXiv fetchers to the
deterministic path-selecting mapper in
``processing.extraction.to_document_model.arxiv_to_document``. It owns the
network decision; the mapper owns the parsing.

arXiv fetch discipline (rigor #4 — the prior 429-ban must NOT recur):

* NO second fetcher. The HTTP egress here goes through the SAME host-global rate
  governor (``acquisition.arxiv.rate_governor.governed_request`` +
  ``arxiv_governed_client``) that ``_default_fetch_pdf`` / ``pdf_fetch`` /the OAI
  harvest use — the >= 3s spacing + 429 ``banned_until`` sentinel hold across ALL
  arXiv jobs on the box. An active ban raises ``ArxivBanned`` and PAUSES (never
  retries) — the exact failure mode project_researchmaxx_arxiv.md records.
* ar5iv is on a DIFFERENT host (``ar5iv.org``) than the banned ``export.arxiv.org``
  search API; the PDF host (``arxiv.org``) is a third. We still govern every arXiv-
  family request through the one governor so a future ar5iv rate-limit can't race
  either. ar5iv egress is OPT-IN: the default fetcher only hits ar5iv when the
  caller asks for the structured path, so a metadata-only ingest never touches it.
* The fetchers are INJECTABLE (``fetch_html`` / ``fetch_pdf`` params) so tests run
  with NO network — the default suite validates the mapping against a local
  ar5iv-shaped HTML fixture + a locally-built PDF, never hitting arXiv.
"""

from __future__ import annotations

import logging

from processing.extraction.to_document_model import (
    ArxivExtraction,
    ArxivSourceFetch,
    arxiv_to_document,
)
from substrate.contracts.document_model import DocumentAttribution

logger = logging.getLogger(__name__)

# ar5iv renders the LaTeX source to structured HTML (math as <math alttext=tex>).
# ``ar5iv.org/abs/<id>`` is the stable entry; it 302s to the rendered article.
AR5IV_BASE_URL = "https://ar5iv.org/abs/"


def _default_fetch_ar5iv_html(arxiv_id: str) -> str | None:
    """Fetch ar5iv structured HTML for ``arxiv_id`` through the host-global arXiv
    rate governor. Returns the HTML on success, ``None`` when ar5iv has no
    rendering for the paper (404) so the caller falls back to the PDF path.

    Reuses ``arxiv_governed_client`` + ``governed_request`` — the SAME governed
    seam as the PDF fetch, so this egress is host-globally spaced and an active
    ban PAUSES rather than re-hitting arXiv (rigor #4)."""
    from typing import cast

    import httpx

    from .client import DEFAULT_TIMEOUT_S, DEFAULT_USER_AGENT
    from .rate_governor import (
        arxiv_governed_client,
        canonical_arxiv_throttle,
        governed_request,
    )

    url = f"{AR5IV_BASE_URL}{arxiv_id}"
    throttle = canonical_arxiv_throttle()
    with arxiv_governed_client(throttle=throttle) as c:
        def _send() -> httpx.Response:
            return c.get(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=DEFAULT_TIMEOUT_S,
            )

        r = cast("httpx.Response", governed_request(_send, throttle=throttle))
    if r.status_code == 404:
        return None
    r.raise_for_status()
    # ar5iv returns HTML; a non-HTML body means no rendering — treat as absent.
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype.lower():
        return None
    return r.text


def fetch_arxiv_document(
    arxiv_id: str,
    *,
    document_id: str,
    title: str | None = None,
    attribution: DocumentAttribution | None = None,
    prefer_structured: bool = True,
    fetch_html=None,
    fetch_pdf=None,
) -> ArxivExtraction:
    """Fetch and extract an arXiv paper to a structured ``Document``, preferring
    ar5iv structured source (math as tex) and falling back to the M2 PDF path.

    Returns an ``ArxivExtraction`` whose ``.path`` records which fired
    (``"structured_source"`` / ``"pdf_fallback"`` / ``"empty"``) — the M3
    acceptance criterion (record the chosen path on the document).

    ``fetch_html`` / ``fetch_pdf`` are injectable for tests (default: the
    governed fetchers). ``prefer_structured=False`` skips ar5iv entirely (PDF
    only) — used when an operator knows the paper has no ar5iv rendering and
    wants to avoid the extra governed request.
    """
    html: str | None = None
    if prefer_structured:
        fh = fetch_html or _default_fetch_ar5iv_html
        try:
            html = fh(arxiv_id)
        except Exception as e:  # noqa: BLE001 — ar5iv is best-effort; PDF is the floor
            # An ar5iv failure (including ArxivBanned) must NOT abort ingestion —
            # we degrade to the PDF path. A ban on the arXiv FAMILY would also hit
            # the PDF fetch below and propagate there; here we just log and move
            # on so a 404/network blip doesn't lose the paper.
            logger.info("ar5iv fetch failed for %s (%s); falling back to PDF", arxiv_id, e)
            html = None

    pdf_bytes: bytes | None = None
    if not html:
        fp = fetch_pdf or _default_fetch_pdf_bytes
        pdf_bytes = fp(arxiv_id)

    return arxiv_to_document(
        ArxivSourceFetch(html=html, pdf_bytes=pdf_bytes),
        document_id=document_id,
        title=title,
        attribution=attribution,
    )


def _default_fetch_pdf_bytes(arxiv_id: str) -> bytes:
    """Default PDF fallback — delegates to the adapter's already-governed
    ``_default_fetch_pdf`` so there is exactly ONE governed PDF fetcher (no
    second fetcher; rigor #4)."""
    from .adapter import _default_fetch_pdf

    return _default_fetch_pdf(arxiv_id)


__all__ = [
    "fetch_arxiv_document",
    "AR5IV_BASE_URL",
]
