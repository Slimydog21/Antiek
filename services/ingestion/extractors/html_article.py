"""HTML article extractor (M4) — reader-mode style.

Wraps the existing ``acquisition/urls/extract.py`` extractor (which is
a lightweight Mozilla Readability-equivalent built on BeautifulSoup +
html2text). Adds:

- Best-effort published-at resolution (og:article:published_time,
  schema.org datePublished, <time datetime=...>).
- Best-effort paywall detection per INGESTION_NOTES.md (word count
  threshold + marker-phrase scan).
- A uniform ``ExtractedDocument`` envelope the pipeline consumes.

Why we don't switch to ``readability-lxml``: the existing extractor
has worked-out edge cases (NYT byl meta, schema.org/Person, og:title
fallback) that we'd lose. The diligence rationale (rigor #4) — inherit
working behavior, fix what's broken, don't rewrite for the sake of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# Paywall markers per INGESTION_NOTES.md. Best-effort; over-flag is
# better than under-flag (a wrong paywall=True is harmless, a missed
# paywall=False lies about completeness).
_PAYWALL_MARKERS = (
    "subscribe to continue",
    "subscribe to read",
    "sign in to read",
    "sign in to continue",
    "continue reading",
    "paywall",
    "subscribers only",
    "to read this article",
    "log in to read",
)
_PAYWALL_WORD_COUNT_THRESHOLD = 200


@dataclass(frozen=True)
class HtmlExtraction:
    """Output of ``extract_html``. The pipeline maps this into the
    common ExtractedDocument envelope."""

    title: Optional[str]
    byline: Optional[str]
    content_html: str  # the isolated main-content HTML fragment
    content_text: str  # markdown rendering (rich text the chunker eats)
    published_at: Optional[datetime]
    word_count: int
    paywalled: bool
    final_url: Optional[str] = None
    extra: dict = field(default_factory=dict)


def _detect_paywall(raw_html: str, word_count: int) -> bool:
    """Best-effort. Per INGESTION_NOTES.md: low word count AND at
    least one marker phrase. We don't paywall-flag long articles even
    if a marker phrase appears (e.g. a long article *about* paywalls)."""
    if word_count >= _PAYWALL_WORD_COUNT_THRESHOLD:
        return False
    lowered = raw_html.lower()
    return any(m in lowered for m in _PAYWALL_MARKERS)


_ISO_TIME_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)


def _parse_iso(ts: str) -> Optional[datetime]:
    """RFC3339/ISO 8601 → tz-aware UTC datetime. Returns None on
    anything unparseable."""
    if not ts:
        return None
    m = _ISO_TIME_RE.search(ts)
    candidate = m.group(1) if m else ts.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _resolve_published_at(html_str: str) -> Optional[datetime]:
    """Light-touch parse for published-at. We do this with regex over
    raw HTML rather than re-parsing with BeautifulSoup because the
    underlying ``acquisition.urls.extract`` already paid that cost;
    we just want the timestamp fields it doesn't currently expose."""
    patterns = (
        r'<meta\s+[^>]*property="article:published_time"\s+content="([^"]+)"',
        r'<meta\s+[^>]*name="article:published_time"\s+content="([^"]+)"',
        r'<meta\s+[^>]*itemprop="datePublished"\s+content="([^"]+)"',
        r'<time\s+[^>]*datetime="([^"]+)"',
    )
    for p in patterns:
        m = re.search(p, html_str, re.IGNORECASE)
        if m:
            dt = _parse_iso(m.group(1))
            if dt:
                return dt
    return None


def extract_html(
    *,
    html_body: bytes,
    final_url: Optional[str] = None,
) -> HtmlExtraction:
    """Extract main-content article text from raw HTML bytes.

    Wraps ``acquisition.urls.extract.html_to_markdown`` for the
    title/author/markdown work, then adds the published-at + paywall
    detection on top. Returns a uniform envelope regardless of source.
    """
    # Imported here so module import is cheap (the extractor pulls in
    # beautifulsoup4 + html2text; we don't want the import cost when a
    # caller only uses the EPUB or PDF path).
    from acquisition.urls.extract import html_to_markdown

    md_doc = html_to_markdown(html_body, base_url=final_url)
    try:
        html_str = (
            html_body.decode("utf-8") if isinstance(html_body, bytes) else html_body
        )
    except UnicodeDecodeError:
        html_str = html_body.decode("latin-1", errors="replace") if isinstance(html_body, bytes) else ""

    published_at = _resolve_published_at(html_str)
    paywalled = _detect_paywall(html_str, md_doc.word_count)

    return HtmlExtraction(
        title=md_doc.title,
        byline=md_doc.author,
        content_html=html_str,
        content_text=md_doc.markdown,
        published_at=published_at,
        word_count=md_doc.word_count,
        paywalled=paywalled,
        final_url=final_url,
    )
