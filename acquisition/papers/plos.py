"""PLOS connector (SPR-07 M5a).

PLOS journals are uniformly CC-BY open access — the cleanest servable paper
source. But the servable class still flows through the SPR-02 chokepoint: the
connector records the catalog-wide CC-BY as the per-record declared license and
hands it to ``classify`` like every other source. It does NOT bypass
classification by stamping ``content_class="source_declared_open"`` directly —
that legacy direct route is exactly what this wave retires. The license_basis
names "PLOS catalog CC-BY" so the SPR-10 audit can read why the body is servable.

The PLOS Search (solr) API returns articles with a DOI, title, abstract, and
author list. PLOS does not vary the license per article (catalog-wide CC-BY),
so the connector supplies the CC-BY URI as the declared license; this is the
ONE per-source basis the sprint permits — and even it goes through the
chokepoint. The CC-BY URI is the canonical Creative-Commons license URI the
shared licenses_core table resolves; the connector does not interpret it.

Identity: the article DOI. Uses ``httpx`` so tests inject a ``MockTransport`` —
NO live HTTP in CI.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from acquisition.papers._pipeline import PaperRecord

DEFAULT_BASE_URL = "https://api.plos.org/search"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.papers.plos)"
DEFAULT_TIMEOUT_S = 20.0
PLOS_SOURCE = "plos"
PLOS_THROTTLE_KEY = "plos"

# PLOS's catalog-wide license is CC-BY. We carry the canonical CC-BY license URI
# as the per-record DECLARED license string and pass it to classify() — the
# chokepoint resolves it to a servable class. This is the catalog basis the
# sprint permits as a per-source declaration; it is NOT an inline rights
# decision (the connector resolves nothing — it hands the URI to the chokepoint,
# exactly as CORE/S2/biorxiv hand their per-record license strings).
PLOS_CATALOG_LICENSE_URI = "https://creativecommons.org/licenses/by/4.0/"


def _article_pdf_url(doi: str) -> str:
    """PLOS's article-asset PDF URL convention for a DOI."""
    return f"https://journals.plos.org/plosone/article/file?id={doi}&type=printable"


def article_to_record(raw: dict[str, Any]) -> PaperRecord:
    """Map ONE PLOS solr article doc into the shared PaperRecord, carrying the
    catalog CC-BY as the declared license. ``license`` is the CC-BY URI; the
    chokepoint resolves it — the connector decides nothing."""
    doi = raw.get("id") or raw.get("doi")
    doi = str(doi).strip() if doi else None
    if not doi:
        raise ValueError("PLOS article has no DOI/id")
    # PLOS solr returns title_display + abstract as single-element lists.
    title = raw.get("title_display") or raw.get("title")
    if isinstance(title, list):
        title = title[0] if title else ""
    abstract = raw.get("abstract")
    if isinstance(abstract, list):
        abstract = " ".join(str(a) for a in abstract).strip()
    authors_raw = raw.get("author_display") or raw.get("author") or []
    authors = tuple(str(a).strip() for a in authors_raw if str(a).strip()) if isinstance(authors_raw, list) else ()
    return PaperRecord(
        source=PLOS_SOURCE,
        source_id=doi,
        title=str(title or "").strip(),
        # The catalog CC-BY URI — handed to classify(), not interpreted here.
        license=PLOS_CATALOG_LICENSE_URI,
        license_field="catalog CC-BY",
        doi=doi,
        abstract=(str(abstract).strip() if abstract else None),
        authors=authors,
        pdf_url=_article_pdf_url(doi),
        has_servable_body=True,
        legitimate_source=True,  # PLOS is a legitimate open-access publisher
        metadata={"journal": raw.get("journal"), "publication_date": raw.get("publication_date")},
    )


def parse_search_response(payload: dict[str, Any]) -> list[PaperRecord]:
    """PLOS solr JSON -> records. Pure; recorded-response tests target this
    directly. Docs live under ``response.docs``."""
    docs = ((payload.get("response") or {}).get("docs")) or []
    out: list[PaperRecord] = []
    for d in docs:
        if isinstance(d, dict):
            try:
                out.append(article_to_record(d))
            except ValueError:
                continue
    return out


def _http_get(url: str, *, client: Optional[httpx.Client]) -> dict:
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if client is not None:
        r = client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    else:
        with httpx.Client(follow_redirects=True) as c:
            r = c.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def search_articles(
    *,
    query: str,
    limit: int = 25,
    client: Optional[httpx.Client] = None,
    base_url: Optional[str] = None,
    throttle: Any = None,
) -> list[PaperRecord]:
    """Query the PLOS search API for articles matching ``query``. ``throttle``
    (a SourceThrottle) spaces the request + carries the ban sentinel; tests pass
    a no-op one or omit it."""
    import urllib.parse

    base = base_url or os.environ.get("ANTIEK_PLOS_BASE_URL", DEFAULT_BASE_URL)
    qs = urllib.parse.urlencode(
        {"q": query, "rows": int(limit), "wt": "json",
         "fl": "id,title_display,abstract,author_display,journal,publication_date"}
    )
    url = f"{base}?{qs}"
    if throttle is not None:
        throttle.before_request(PLOS_THROTTLE_KEY)
    payload = _http_get(url, client=client)
    return parse_search_response(payload)
