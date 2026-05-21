"""Content-type detection for the ingestion pipeline (M2).

Given a URL, decide whether to route through the PDF extractor, the
HTML article extractor, the EPUB extractor, or the arXiv extractor.

Detection runs in two passes:

1. **URL pattern (fast, offline).** Cheap regex checks for arXiv
   abs/pdf URLs and obvious file extensions (.pdf, .epub). When the
   URL pattern is unambiguous we return immediately — no HTTP needed.

2. **HEAD request (authoritative).** For anything ambiguous, fire a
   HEAD and read ``Content-Type``. ``application/pdf`` → PDF;
   ``application/epub+zip`` → EPUB; anything else → HTML article.
   When HEAD fails or is rejected (some servers 405 HEAD), we fall
   back to URL extension and finally to HTML article.

Why default to HTML article on ambiguity: the universal library is
mostly web pages; the extractor handles them gracefully even when
content looks unstructured. The PDF/EPUB extractors are stricter and
would fail loudly on the wrong input, while HTML extraction
gracefully degrades to "low word count" and the pipeline's word-count
gate kicks the document out cleanly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

# Routing labels — the pipeline switches on these strings.
ContentType = str
PDF: ContentType = "pdf"
HTML_ARTICLE: ContentType = "html_article"
EPUB: ContentType = "epub"
ARXIV: ContentType = "arxiv"
UNKNOWN: ContentType = "unknown"


# arXiv URL shapes:
#   https://arxiv.org/abs/2402.03300
#   https://arxiv.org/abs/2402.03300v2
#   http://arxiv.org/pdf/2402.03300
#   https://arxiv.org/pdf/2402.03300.pdf
#   https://export.arxiv.org/abs/2402.03300
# We match both abs and pdf paths; the extractor picks the PDF endpoint
# regardless of which one was pasted (the PDF carries the full text).
_ARXIV_HOST_RE = re.compile(r"^(www\.|export\.)?arxiv\.org$", re.IGNORECASE)
_ARXIV_PATH_RE = re.compile(r"^/(abs|pdf)/[a-zA-Z0-9./\-]+$")

# Extensions that uniquely identify content. ``.html`` is intentionally
# absent — most articles don't have an extension at all, so the
# absence of one of these doesn't tell us anything useful.
_PDF_EXT_RE = re.compile(r"\.pdf($|\?|#)", re.IGNORECASE)
_EPUB_EXT_RE = re.compile(r"\.epub($|\?|#)", re.IGNORECASE)

# Content-Type → content kind, with ``;`` and ``charset=`` parameters
# stripped (lowercased). Anything not in this map falls through to
# HTML article (the spec's documented default for ambiguous types).
_MIME_TO_KIND: dict[str, ContentType] = {
    "application/pdf": PDF,
    "application/x-pdf": PDF,
    "application/epub+zip": EPUB,
    "application/epub": EPUB,
    "text/html": HTML_ARTICLE,
    "application/xhtml+xml": HTML_ARTICLE,
}


@dataclass(frozen=True)
class DetectionResult:
    """What ``detect`` returns. ``via`` records which pass produced
    the answer — useful in jobs.metadata for debugging which URLs
    needed the HEAD round-trip vs which were obvious from the URL."""

    content_type: ContentType
    via: str  # "url_pattern" | "head_request" | "extension_fallback" | "default"
    head_status: Optional[int] = None
    head_content_type: Optional[str] = None


def _strip_mime(raw: str) -> str:
    """``"text/html; charset=utf-8"`` → ``"text/html"``."""
    return raw.split(";", 1)[0].strip().lower()


def detect_from_url(url: str) -> Optional[ContentType]:
    """First pass: URL pattern only. Returns None when the URL is
    ambiguous and a HEAD is needed."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    if _ARXIV_HOST_RE.match(host) and _ARXIV_PATH_RE.match(path):
        return ARXIV
    # File-extension hints (don't fight a server's Content-Type — but
    # if the URL ends in .pdf we don't need a HEAD to know).
    if _PDF_EXT_RE.search(path):
        return PDF
    if _EPUB_EXT_RE.search(path):
        return EPUB
    return None


def detect_from_head(
    url: str,
    *,
    client: Optional[httpx.Client] = None,
    timeout_s: float = 10.0,
) -> tuple[Optional[ContentType], Optional[int], Optional[str]]:
    """Second pass: HEAD the URL and look at Content-Type. Returns
    ``(kind, status, raw_content_type)``. ``kind`` is None when HEAD
    failed (caller falls back to extension or default)."""
    headers = {
        "User-Agent": "Antiek/0.1 (services.ingestion.content_type)",
        "Accept": "*/*",
    }
    try:
        if client is not None:
            r = client.head(
                url, headers=headers, timeout=timeout_s,
                follow_redirects=True,
            )
        else:
            with httpx.Client(follow_redirects=True) as c:
                r = c.head(url, headers=headers, timeout=timeout_s)
    except (httpx.HTTPError, OSError):
        return (None, None, None)
    # Some servers respond to HEAD with 405; treat that as
    # "indeterminate" and fall through.
    if r.status_code >= 400:
        return (None, r.status_code, r.headers.get("content-type"))
    raw = r.headers.get("content-type") or ""
    mime = _strip_mime(raw)
    return (_MIME_TO_KIND.get(mime, HTML_ARTICLE), r.status_code, raw)


def detect(
    url: str,
    *,
    client: Optional[httpx.Client] = None,
    do_head: bool = True,
) -> DetectionResult:
    """Full detection pipeline. URL pattern first; HEAD if needed;
    extension fallback if HEAD fails; HTML article as the final
    default per the spec.

    ``do_head=False`` skips the network call — used by tests and by
    operator-batch flows that know the type a priori (e.g. a batch
    of arXiv ids)."""
    url_kind = detect_from_url(url)
    if url_kind is not None:
        return DetectionResult(content_type=url_kind, via="url_pattern")

    if not do_head:
        return DetectionResult(content_type=HTML_ARTICLE, via="default")

    head_kind, head_status, head_raw = detect_from_head(url, client=client)
    if head_kind is not None:
        return DetectionResult(
            content_type=head_kind, via="head_request",
            head_status=head_status, head_content_type=head_raw,
        )

    # HEAD failed. Try extension once more (some servers don't return
    # Content-Type for HEAD; URL is the last signal we have).
    if _PDF_EXT_RE.search(url):
        return DetectionResult(
            content_type=PDF, via="extension_fallback",
            head_status=head_status, head_content_type=head_raw,
        )
    if _EPUB_EXT_RE.search(url):
        return DetectionResult(
            content_type=EPUB, via="extension_fallback",
            head_status=head_status, head_content_type=head_raw,
        )

    # Spec says: ambiguous → HTML article.
    return DetectionResult(
        content_type=HTML_ARTICLE, via="default",
        head_status=head_status, head_content_type=head_raw,
    )
