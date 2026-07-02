"""PubMed Central / Europe PMC full-text resolution adapter.

Europe PMC (https://europepmc.org/RestfulWebService) mirrors the PMC OA
subset and exposes a per-article ``license`` field plus a full-text URL list.
This adapter looks up an article by DOI or PMCID, reads its per-article
license, and resolves the OA PDF URL.

THE INVARIANT in action: PMC's full-text-URL list mixes availability tiers —
a row can be ``"Subscription required"`` (the DOI link) right next to an
``"Open access"`` PDF. We only ever take an ``Open access`` PDF row, and the
servability decision comes from the article's declared ``license`` (resolved
deny-by-default), never from "PMC has a full-text URL." An article in PMC with
NO license field gates by default.

Europe PMC normalises licenses to short forms ("cc by", "cc-by", "cc by-nc")
— we lower-case and substitute spaces so they match the CC rows' substrings.

Uses ``httpx`` so tests inject a ``MockTransport`` — NO live HTTP in CI.
"""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from typing import Any, cast

import httpx

from acquisition.licenses_core import LicenseResolution

from .licenses import resolve_oa_license
from .throttle import OAThrottle

DEFAULT_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.openaccess)"
DEFAULT_TIMEOUT_S = 15.0

# Europe PMC marks full-text rows with an availability label; only this one
# is a fetchable open PDF. Anything else (subscription/restricted) is skipped.
_OPEN_AVAILABILITY = "open access"


@dataclass(frozen=True)
class PMCArticle:
    """A resolved PMC article + its OA verdict.

    ``pdf_url`` is the Open-access PDF render URL (``None`` when the article
    has no open full-text row — a counted miss). ``resolution`` is the
    deny-by-default verdict from the per-article license string."""

    pmcid: str | None
    doi: str | None
    title: str
    is_open_access: bool
    pdf_url: str | None
    license_uri: str | None
    resolution: LicenseResolution
    source: str = "europepmc"


def _normalize_license(raw: str | None) -> str | None:
    """Europe PMC emits "cc by" / "cc-by" / "cc by-nc-nd". Map to the
    canonical CC URI fragment so the CC license rows match. Unrecognised
    strings pass through verbatim (the resolver then gates them)."""
    if not raw:
        return None
    s = raw.strip().lower().replace(" ", "-")
    # "cc-by", "cc-by-sa", "cc-by-nc-nd", "cc0"
    if s in ("cc0", "cc-zero"):
        return "creativecommons.org/publicdomain/zero/1.0/"
    if s.startswith("cc-by"):
        variant = s[len("cc-"):]  # "by", "by-sa", "by-nc-nd", ...
        return f"creativecommons.org/licenses/{variant}/4.0/"
    if s in ("public-domain", "pd", "cc-pdm"):
        return "creativecommons.org/publicdomain/mark/1.0/"
    return raw


def _extract_open_pdf_url(article: dict[str, Any]) -> str | None:
    urls = (article.get("fullTextUrlList") or {}).get("fullTextUrl") or []
    for u in urls:
        style = (u.get("documentStyle") or "").lower()
        avail = (u.get("availability") or "").lower()
        if style == "pdf" and avail == _OPEN_AVAILABILITY:
            url = u.get("url")
            return url if isinstance(url, str) else None
    return None


def parse_search_response(payload: dict[str, Any]) -> list[PMCArticle]:
    """Europe PMC ``/search`` (resultType=core) JSON -> articles. Pure; the
    recorded-response tests target this directly."""
    results = (payload.get("resultList") or {}).get("result") or []
    out: list[PMCArticle] = []
    for art in results:
        license_uri = _normalize_license(art.get("license"))
        out.append(
            PMCArticle(
                pmcid=art.get("pmcid"),
                doi=art.get("doi"),
                title=art.get("title") or "",
                is_open_access=(art.get("isOpenAccess") == "Y"),
                pdf_url=_extract_open_pdf_url(art),
                license_uri=license_uri,
                resolution=resolve_oa_license(license_uri),
            )
        )
    return out


def _build_search_url(query: str, *, base_url: str | None) -> str:
    base = base_url or os.environ.get("ANTIEK_EUROPEPMC_BASE_URL", DEFAULT_BASE_URL)
    qs = urllib.parse.urlencode(
        {"query": query, "format": "json", "resultType": "core"}
    )
    return f"{base}/search?{qs}"


def resolve_by_doi(
    doi: str,
    *,
    client: httpx.Client | None = None,
    base_url: str | None = None,
    throttle: OAThrottle | None = None,
) -> PMCArticle | None:
    """Resolve a DOI to its PMC article + OA verdict. Returns ``None`` when
    Europe PMC has no record for the DOI."""
    articles = _search(f"DOI:{doi}", client=client, base_url=base_url, throttle=throttle)
    return articles[0] if articles else None


def _search(
    query: str,
    *,
    client: httpx.Client | None,
    base_url: str | None,
    throttle: OAThrottle | None,
) -> list[PMCArticle]:
    url = _build_search_url(query, base_url=base_url)

    def _get() -> dict[str, Any]:
        from acquisition.arxiv.rate_governor import (
            canonical_arxiv_throttle,
            govern_if_arxiv,
        )

        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if client is not None:
            def _send() -> httpx.Response:
                return client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

            r = cast(
                "httpx.Response",
                govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle()),
            )
        else:
            with httpx.Client(
                follow_redirects=True,
                timeout=DEFAULT_TIMEOUT_S,  # module default; same pattern as acquisition/papers/core.py DEFAULT_TIMEOUT_S
            ) as c:
                def _send() -> httpx.Response:
                    return c.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

                r = cast(
                    "httpx.Response",
                    govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle()),
                )
        r.raise_for_status()
        return cast("dict[str, Any]", r.json())

    payload = throttle.run_with_retry(_get) if throttle is not None else _get()
    return parse_search_response(payload)


def download_pdf(
    pdf_url: str,
    *,
    client: httpx.Client | None = None,
    throttle: OAThrottle | None = None,
) -> bytes:
    """Download PMC PDF bytes. Transient errors retry via the (non-arXiv)
    ``OAThrottle``.

    HOST-GLOBAL arXiv GOVERNANCE (SPR-09 root fix): ``pdf_url`` is a RESOLVED,
    variable URL read off Europe PMC's ``fullTextUrlList`` — PMC normally points
    at an ``ncbi.nlm.nih.gov`` render URL, but the host is not statically known,
    so the actual HTTP send is routed through ``govern_if_arxiv``. Were a row to
    resolve to an arXiv host it would be governed by the host-global flock on the
    shared throttle state; the ordinary non-arXiv PMC host is fetched directly
    (the ``OAThrottle`` above provides that path's spacing/retry). Host-based, not
    module-location-based — uniform with the unpaywall fetcher.

    REDIRECT-SAFE (SPR-09 round-5): a PMC render URL can 302-REDIRECT to an arXiv
    host; the client carries the per-hop arXiv request/response hooks so EVERY
    hop whose host is arXiv — initial OR a redirect target — is governed by
    construction (the initial-host ``govern_if_arxiv`` check alone would miss the
    redirect hop)."""
    def _get() -> bytes:
        from acquisition.arxiv.rate_governor import (
            arxiv_governed_client,
            canonical_arxiv_throttle,
            govern_if_arxiv,
            install_arxiv_request_hook,
        )

        from .pdf_detect import assert_pdf

        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if client is not None:
            install_arxiv_request_hook(client, throttle=canonical_arxiv_throttle())
            def _send() -> httpx.Response:
                return client.get(pdf_url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

            r = cast(
                "httpx.Response",
                govern_if_arxiv(pdf_url, _send, throttle=canonical_arxiv_throttle()),
            )
            content_type = r.headers.get("content-type")
            r.raise_for_status()
            content = r.content
        else:
            with arxiv_governed_client(throttle=canonical_arxiv_throttle()) as c:
                def _send() -> httpx.Response:
                    return c.get(pdf_url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

                r = cast(
                    "httpx.Response",
                    govern_if_arxiv(pdf_url, _send, throttle=canonical_arxiv_throttle()),
                )
                content_type = r.headers.get("content-type")
                r.raise_for_status()
                content = r.content
        # PMC ?pdf=render can return an HTML interstitial; the shared layered
        # detector (content-type / %PDF- / pypdf parse) rejects it as NotAPdf.
        assert_pdf(content, content_type=content_type, url=pdf_url)
        return content

    return throttle.run_with_retry(_get) if throttle is not None else _get()
