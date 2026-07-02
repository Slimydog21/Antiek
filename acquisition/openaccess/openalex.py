"""OpenAlex discovery adapter.

OpenAlex (https://docs.openalex.org) is the discovery layer: query by topic /
author / work, get back candidate works each carrying a DOI, OA status,
best-OA-location URL, and the OA license string. It is NOT a full-text host —
the actual PDF resolution + download is the job of the per-source adapters
(``unpaywall`` / ``pmc`` / ``doaj``). This module just surfaces candidates +
their declared license so the caller can route the servable ones.

Polite-pool: every request carries a ``mailto`` query param so OpenAlex puts
us in the faster, more forgiving pool (and can contact us before throttling).

Uses ``httpx`` so tests inject a ``MockTransport`` — NO live HTTP in CI.

OUT OF SCOPE (per the sprint): we do NOT walk OpenAlex reference edges to
build a citation graph. We ingest works, not their citation network.
"""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

from .throttle import POLITE_POOL_MAILTO, OAThrottle

DEFAULT_BASE_URL = "https://api.openalex.org/works"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.openaccess)"
DEFAULT_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class OpenAlexWork:
    """One OpenAlex work, reduced to the fields the rights router needs.

    ``license_uri`` is the best-OA-location's declared license (``None`` when
    OpenAlex has none — a common bronze/green-without-license case, which the
    OA license resolver gates by default). ``oa_status`` is OpenAlex's coarse
    classification (gold / green / hybrid / bronze / closed) — informational;
    the redistribution decision is made from ``license_uri``, never from
    oa_status alone (bronze is "free to read", not "free to redistribute")."""

    openalex_id: str
    doi: str | None
    title: str
    is_oa: bool
    oa_status: str | None
    best_oa_pdf_url: str | None
    best_oa_landing_url: str | None
    license_uri: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Ordered, de-duped PDF-URL candidates (best/primary/locations[].pdf_url,
    # then open_access.oa_url as a last-resort landing fallback). The OA ingest
    # thunk tries these in order so a leading HTML landing page no longer
    # detonates the whole work in pypdf. Defaulted, so existing positional
    # construction sites and ``best_oa_pdf_url`` readers keep working.
    pdf_url_candidates: tuple[str, ...] = ()


def _normalize_doi(doi: str | None) -> str | None:
    """OpenAlex emits DOIs as full ``https://doi.org/10.x/...`` URLs; reduce
    to the bare ``10.x/...`` form the downstream resolvers expect."""
    if not doi:
        return None
    d = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.lower().startswith(prefix):
            return d[len(prefix):]
    return d


def _parse_work(raw: dict[str, Any]) -> OpenAlexWork:
    oa = raw.get("open_access") or {}
    best = raw.get("best_oa_location") or {}
    primary = raw.get("primary_location") or {}
    # Ordered, de-duped PDF candidates: prefer locations that DECLARE a pdf_url
    # (a direct file) over open_access.oa_url (the best free-to-READ url, often
    # an HTML landing page). The landing url is kept only as a last resort so a
    # work with no declared pdf_url is still attempted, but is tried LAST.
    ordered: list[str] = []
    for loc in (best, primary, *(raw.get("locations") or [])):
        u = (loc or {}).get("pdf_url")
        if isinstance(u, str) and u and u not in ordered:
            ordered.append(u)
    oa_url = oa.get("oa_url")
    if isinstance(oa_url, str) and oa_url and oa_url not in ordered:
        ordered.append(oa_url)  # last-resort landing fallback
    return OpenAlexWork(
        openalex_id=str(raw.get("id") or ""),
        doi=_normalize_doi(raw.get("doi")),
        title=raw.get("title") or raw.get("display_name") or "",
        is_oa=bool(oa.get("is_oa")),
        oa_status=oa.get("oa_status"),
        best_oa_pdf_url=(ordered[0] if ordered else None),
        best_oa_landing_url=best.get("landing_page_url") or primary.get("landing_page_url"),
        # The license lives on the best-OA-location; OpenAlex normalises it to
        # a CC short form ("cc-by") or a URI. Either matches the CC rows'
        # substrings; absent -> None -> gated by default.
        license_uri=best.get("license"),
        metadata={
            "oa_status": oa.get("oa_status"),
            "version": best.get("version"),
            "publication_year": raw.get("publication_year"),
        },
        pdf_url_candidates=tuple(ordered),
    )


def _build_url(
    *,
    search: str | None,
    author: str | None,
    filters: str | None,
    per_page: int,
    mailto: str,
    base_url: str | None,
) -> str:
    """Compose the works query URL. ``search`` is full-text; ``author`` adds
    an ``author.id`` / display-name filter; ``filters`` is a raw OpenAlex
    filter expression (e.g. ``open_access.is_oa:true``). The polite-pool
    mailto is always appended."""
    params: list[tuple[str, str]] = []
    if search:
        params.append(("search", search))
    filter_parts: list[str] = []
    if filters:
        filter_parts.append(filters)
    if author:
        filter_parts.append(f"raw_author_name.search:{author}")
    if filter_parts:
        params.append(("filter", ",".join(filter_parts)))
    if not search and not filter_parts:
        raise ValueError("openalex query requires search, author, or filters")
    params.append(("per_page", str(int(per_page))))
    params.append(("mailto", mailto))

    base = base_url or os.environ.get("ANTIEK_OPENALEX_BASE_URL", DEFAULT_BASE_URL)
    qs = "&".join(f"{k}={urllib.parse.quote(v, safe=':,.')}" for k, v in params)
    return f"{base}?{qs}"


def _http_get(url: str, *, client: httpx.Client | None) -> dict[str, Any]:
    # ``url`` is built from an env/param-overridable base, so route through the
    # host-based gate: the default api.openalex.org host is fetched directly;
    # were the base ever an arXiv host it would be governed by the shared gate.
    from acquisition.arxiv.rate_governor import (
        canonical_arxiv_throttle,
        govern_if_arxiv,
    )

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if client is not None:
        def _send() -> httpx.Response:
            return client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

        r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
    else:
        with httpx.Client(
            follow_redirects=True,
            timeout=DEFAULT_TIMEOUT_S,  # module default; same pattern as acquisition/papers/core.py DEFAULT_TIMEOUT_S
        ) as c:
            def _send() -> httpx.Response:
                return c.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

            r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
    r.raise_for_status()
    return cast("dict[str, Any]", r.json())


def parse_works_response(payload: dict[str, Any]) -> list[OpenAlexWork]:
    """OpenAlex ``/works`` JSON -> list of works. Pure; the recorded-response
    tests target this directly."""
    return [_parse_work(w) for w in payload.get("results", [])]


# ---------------------------------------------------------------------------
# Enrichment helper (SPR-03): fetch the FULL raw work record by arXiv id / DOI.
#
# ``search_works`` / ``_parse_work`` deliberately REDUCE a work to the rights
# router's lean view (id / doi / title / OA / license / pdf), DISCARDING the
# authorships, ORCIDs, and referenced_works. arXiv enrichment (SPR-03) needs
# exactly those discarded fields. Rather than fork a second HTTP client, this
# helper REUSES the existing ``_build_url`` / ``_http_get`` / ``OAThrottle``
# plumbing and returns the FIRST RAW result dict untouched, so the caller
# (``acquisition.arxiv.enrich_openalex``) can read authorships + referenced_works
# off the raw JSON. ``OpenAlexWork`` / ``_parse_work`` are NOT modified — the
# rights router keeps its lean view.
# ---------------------------------------------------------------------------


def arxiv_doi(arxiv_id: str) -> str:
    """The DataCite arXiv DOI for an arXiv id: ``10.48550/arXiv.<id>``.

    arXiv mints a DataCite DOI for every paper under the ``10.48550`` prefix.
    OpenAlex indexes the work under exactly this DOI, so it is the reliable
    join key from an arXiv id (the arXiv OAI-PMH metadata carries NO DOI of its
    own — verified — so the DOI must be derived, not read)."""
    return f"10.48550/arXiv.{arxiv_id.strip()}"


def fetch_work_record(
    *,
    arxiv_id: str | None = None,
    doi: str | None = None,
    client: httpx.Client | None = None,
    throttle: OAThrottle | None = None,
    base_url: str | None = None,
    mailto: str = POLITE_POOL_MAILTO,
) -> dict[str, Any] | None:
    """Fetch ONE raw OpenAlex work record, joined by arXiv id (primary) or DOI.

    Returns the FIRST raw result dict (the full OpenAlex JSON object, carrying
    ``authorships`` + ``referenced_works`` + ``cited_by_count``), or ``None`` when
    OpenAlex has no matching work. Never fabricates a match: a no-result query
    returns ``None`` and the caller records a miss.

    Join order (the caller may pass either or both):

      1. ``arxiv_id`` (PRIMARY) — joined via the DataCite arXiv DOI
         ``10.48550/arXiv.<arxiv_id>`` (``arxiv_doi``); the arXiv id itself is not
         a native OpenAlex filter, but its minted DOI is the indexed key.
      2. ``doi`` (FALLBACK) — an explicit DOI, tried only if ``arxiv_id`` is
         absent OR produced no match.

    REUSE, not a fork: this issues its request through the SAME ``_build_url`` /
    ``_http_get`` / ``OAThrottle`` plumbing ``search_works`` uses — there is no
    second HTTP client and no duplicate request logic. No ``open_access.is_oa``
    filter is applied: enrichment wants the work's metadata regardless of OA
    status — we are joining a citation/author record, not downloading a PDF.
    """
    if not arxiv_id and not doi:
        raise ValueError("fetch_work_record requires arxiv_id or doi")

    # PRIMARY: arXiv id -> its DataCite DOI. FALLBACK: the explicit DOI.
    candidate_dois: list[str] = []
    if arxiv_id:
        candidate_dois.append(arxiv_doi(arxiv_id))
    if doi and doi not in candidate_dois:
        candidate_dois.append(doi)

    for candidate in candidate_dois:
        # OpenAlex's ``doi`` filter is case-insensitive and accepts the bare
        # ``10.x/...`` form. One result is all we need; per_page=1 keeps it cheap.
        url = _build_url(
            search=None,
            author=None,
            filters=f"doi:{candidate}",
            per_page=1,
            mailto=mailto,
            base_url=base_url,
        )
        if throttle is not None:
            def _fetch_candidate(url: str = url) -> dict[str, Any]:
                return _http_get(url, client=client)

            payload = throttle.run_with_retry(_fetch_candidate)
        else:
            payload = _http_get(url, client=client)
        results = payload.get("results") or []
        if results:
            return cast("dict[str, Any]", results[0])
    return None


def search_works(
    *,
    search: str | None = None,
    author: str | None = None,
    filters: str | None = None,
    per_page: int = 25,
    oa_only: bool = True,
    mailto: str = POLITE_POOL_MAILTO,
    client: httpx.Client | None = None,
    base_url: str | None = None,
    throttle: OAThrottle | None = None,
) -> list[OpenAlexWork]:
    """Query OpenAlex for candidate works.

    ``oa_only`` (default True) ANDs ``open_access.is_oa:true`` into the filter
    so closed-access works are never even surfaced — they can't be ingested
    from this source, so there's no reason to page them. ``throttle`` (when
    supplied) provides spacing + retry; tests pass one with a no-op sleep."""
    effective_filters = filters
    if oa_only:
        oa_filter = "open_access.is_oa:true"
        effective_filters = (
            f"{filters},{oa_filter}" if filters else oa_filter
        )
    url = _build_url(
        search=search,
        author=author,
        filters=effective_filters,
        per_page=per_page,
        mailto=mailto,
        base_url=base_url,
    )
    if throttle is not None:
        payload = throttle.run_with_retry(lambda: _http_get(url, client=client))
    else:
        payload = _http_get(url, client=client)
    return parse_works_response(payload)
