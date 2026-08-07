"""On-demand arXiv HTML fetch — rate-limited, ban-aware, article-sliced (v1).

arXiv now renders most recent papers as native HTML at ``arxiv.org/html/<id>``
(LaTeXML output). That HTML yields materially more clean body text than the PDF
route — the ``~/.claude/skills/arxiv`` port measured ~2.4x more extracted words on
1706.03762 (6,635 vs 2,802) — because PDF-to-text loses structure, math, and
reflowed columns. The platform's full-text path was PDF-only
(:mod:`acquisition.arxiv.pdf_fetch`); this module adds the HTML-first leg so a
caller can prefer HTML and fall back to PDF.

Reused verbatim from the PDF path (NOT re-implemented):
  * The host-global rate governor — every send goes through
    ``acquisition.arxiv.rate_governor.governed_request`` on the caller's
    ``ArxivThrottle``, so the >=3.5s spacing + 429 ``banned_until`` sentinel hold
    across ALL arXiv egresses (search, OAI harvest, PDF, and this HTML fetch)
    under one ``fcntl.flock``. An active ban raises ``ArxivBanned``, which we DO
    NOT catch — re-hitting a banned endpoint is what extends the ban.
  * The redirect-safe governed client (``arxiv_governed_client`` +
    ``install_arxiv_request_hook``) so each ``arxiv.org/html`` → versioned-html
    redirect hop is governed too.

What is HTML-specific here:
  * Article slicing — arXiv wraps the paper in ``<article class="ltx_document">``;
    everything outside it (nav bar, "Report issue" modal, nonprofit banner) is
    page chrome that must not land in the stored body. Ported from the skill's
    ``_slice_article``.
  * Stub detection — a paper with no HTML rendering returns a short placeholder
    page (or 404). Bodies under ``MIN_HTML_CHARS`` or containing the "no html"
    marker are treated as ABSENT (``None``), so the caller falls back to PDF.
  * HTML-absence is normal, not an error: a 404 (no HTML rendering exists) returns
    ``None`` rather than raising, because PDF is the guaranteed path. Only
    ``ArxivBanned`` (rate discipline) is allowed to propagate.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import httpx

from acquisition.arxiv.client import default_user_agent
from acquisition.arxiv.throttle import (  # noqa: F401  (re-export for callers)
    ArxivBanned,
    ArxivThrottle,
)

logger = logging.getLogger("antiek.acquisition.arxiv.html_fetch")

# A real arXiv HTML rendering is comfortably larger than this; anything smaller is
# the "no HTML version" placeholder. Matches the skill's MIN_HTML_CHARS.
MIN_HTML_CHARS = 4000

# arXiv's placeholder for a paper without an HTML rendering contains this marker.
_NO_HTML_MARKER = "no html"

# A longer read timeout than the search API: LaTeXML pages for large papers are
# heavier than an Atom response, but still bounded.
HTML_TIMEOUT_S = 45.0


class HtmlAbsent(Exception):
    """Internal signal: arXiv has no usable HTML rendering for this id. Never
    escapes the module — :func:`fetch_html` maps it to ``None``."""


@dataclass(frozen=True)
class FetchedHtml:
    """Verified, article-sliced arXiv HTML + provenance for the storage layer.

    ``html`` is the ``<article>``-sliced document (chrome stripped). ``sha256`` is
    over the exact stored bytes so an arXiv-compliance query can answer "where did
    this body come from and are these the bytes we fetched".
    """

    arxiv_id: str
    source_url: str
    html: str
    sha256: str
    byte_size: int
    char_count: int


def _html_url(arxiv_id: str) -> str:
    """The canonical native-HTML URL for an arXiv id."""
    return f"https://arxiv.org/html/{arxiv_id}"


def slice_article(raw: str) -> str:
    """Cut arXiv page chrome, keeping only the ``<article>`` paper body.

    arXiv's LaTeXML output wraps the paper in ``<article class="ltx_document">``.
    Keeping the whole page would drag in the nav bar, the "Report GitHub Issue"
    modal, and the nonprofit banner. Ported from the skill's ``_slice_article``;
    if the marker is absent (unexpected layout) the raw HTML is returned unchanged
    so we degrade to "keep everything" rather than lose the body.
    """
    i = raw.find("<article")
    j = raw.rfind("</article>")
    if i < 0 or j <= i:
        return raw
    return "<html><body>" + raw[i : j + len("</article>")] + "</body></html>"


def _is_stub(raw: str) -> bool:
    """True when the fetched HTML is arXiv's no-rendering placeholder."""
    return len(raw) < MIN_HTML_CHARS or _NO_HTML_MARKER in raw[:MIN_HTML_CHARS].lower()


def fetch_html(
    arxiv_id: str,
    *,
    throttle: ArxivThrottle,
    client: httpx.Client | None = None,
    min_chars: int = MIN_HTML_CHARS,
) -> FetchedHtml | None:
    """Fetch one arXiv paper's native HTML rendering, rate-limited and sliced.

    Returns a :class:`FetchedHtml` when arXiv has a usable HTML rendering, or
    ``None`` when it does not (no rendering / a stub / a 404) — in which case the
    caller falls back to :func:`acquisition.arxiv.pdf_fetch.fetch_pdf`.

    ``throttle`` is REQUIRED (not defaulted) so a caller cannot fetch without the
    cross-process spacing/ban protection — the omission that IP-banned the box
    historically. ``client`` is injectable (tests pass an ``httpx.MockTransport``
    client) so CI never touches the network.

    ``ArxivBanned`` (an active rate-limit ban) PROPAGATES — the caller must pause
    the batch, never retry. Every other failure (404, 5xx, timeout, a stub body)
    resolves to ``None`` so the guaranteed PDF path can take over.
    """
    url = _html_url(arxiv_id)

    from acquisition.arxiv.rate_governor import (
        arxiv_governed_client,
        governed_request,
        install_arxiv_request_hook,
    )

    owns_client = client is None
    if client is None:
        # REDIRECT-SAFE: arxiv.org/html/<id> 302-redirects to the versioned HTML;
        # the hook governs each arXiv redirect hop on the caller's throttle.
        # (Narrow on ``client is None`` — not ``owns_client`` — so mypy proves
        # ``client`` is non-None for the send/close below.)
        client = arxiv_governed_client(throttle=throttle)
    else:
        install_arxiv_request_hook(client, throttle=throttle)
    try:
        def _send() -> httpx.Response:
            return client.get(
                url,
                headers={"User-Agent": default_user_agent()},
                timeout=HTML_TIMEOUT_S,
            )

        # Route through the host-global governor so the wait->send->note critical
        # section is held under the shared flock (same discipline as pdf_fetch).
        # ArxivBanned raised here is deliberately allowed to propagate.
        try:
            resp = governed_request(_send, throttle=throttle)
            resp.raise_for_status()
        except ArxivBanned:
            # An active ban (raised by wait_if_needed BEFORE the send). Propagate:
            # the caller must pause the batch and must NOT fall back to PDF.
            raise
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 429:
                # A FRESH 429 is a ban signal, NOT "HTML absent". The governor has
                # already recorded the ban sentinel via note_response; surface the
                # canonical ArxivBanned so the caller pauses — falling back to PDF
                # here would immediately re-hit arxiv.org and DEEPEN the ban.
                throttle.wait_if_needed()  # sentinel is set → raises ArxivBanned
                raise  # pragma: no cover - wait_if_needed always raises on a live ban
            # 404 = no HTML rendering exists for this id; 5xx = a transient absent
            # HTML leg. HTML is best-effort: fall back to the guaranteed PDF path.
            logger.info(
                "arxiv.org/html/%s returned HTTP %s; no HTML body, will fall back to PDF",
                arxiv_id,
                status if status is not None else "?",
            )
            return None
        except httpx.HTTPError as e:
            # Timeout / connection error on the (best-effort) HTML leg → fall back.
            logger.info(
                "arxiv.org/html/%s HTML fetch failed (%s); will fall back to PDF",
                arxiv_id,
                type(e).__name__,
            )
            return None

        raw = resp.content.decode("utf-8", errors="ignore")
    finally:
        if owns_client:
            client.close()

    if len(raw) < min_chars or _NO_HTML_MARKER in raw[:min_chars].lower():
        logger.info("arxiv.org/html/%s absent/stub (%d chars); PDF fallback", arxiv_id, len(raw))
        return None

    sliced = slice_article(raw)
    body_bytes = sliced.encode("utf-8")
    return FetchedHtml(
        arxiv_id=arxiv_id,
        source_url=url,
        html=sliced,
        sha256=hashlib.sha256(body_bytes).hexdigest(),
        byte_size=len(body_bytes),
        char_count=len(sliced),
    )


__all__ = [
    "FetchedHtml",
    "HtmlAbsent",
    "fetch_html",
    "slice_article",
    "MIN_HTML_CHARS",
    "HTML_TIMEOUT_S",
    "ArxivBanned",
]
