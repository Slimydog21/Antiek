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
from typing import Any, List, Optional

import httpx

from .licenses import LicenseResolution, resolve_oa_license
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

    pmcid: Optional[str]
    doi: Optional[str]
    title: str
    is_open_access: bool
    pdf_url: Optional[str]
    license_uri: Optional[str]
    resolution: LicenseResolution
    source: str = "europepmc"


def _normalize_license(raw: Optional[str]) -> Optional[str]:
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


def _extract_open_pdf_url(article: dict[str, Any]) -> Optional[str]:
    urls = (article.get("fullTextUrlList") or {}).get("fullTextUrl") or []
    for u in urls:
        style = (u.get("documentStyle") or "").lower()
        avail = (u.get("availability") or "").lower()
        if style == "pdf" and avail == _OPEN_AVAILABILITY:
            return u.get("url")
    return None


def parse_search_response(payload: dict[str, Any]) -> List[PMCArticle]:
    """Europe PMC ``/search`` (resultType=core) JSON -> articles. Pure; the
    recorded-response tests target this directly."""
    results = (payload.get("resultList") or {}).get("result") or []
    out: List[PMCArticle] = []
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


def _build_search_url(query: str, *, base_url: Optional[str]) -> str:
    base = base_url or os.environ.get("ANTIEK_EUROPEPMC_BASE_URL", DEFAULT_BASE_URL)
    qs = urllib.parse.urlencode(
        {"query": query, "format": "json", "resultType": "core"}
    )
    return f"{base}/search?{qs}"


def resolve_by_doi(
    doi: str,
    *,
    client: Optional[httpx.Client] = None,
    base_url: Optional[str] = None,
    throttle: Optional[OAThrottle] = None,
) -> Optional[PMCArticle]:
    """Resolve a DOI to its PMC article + OA verdict. Returns ``None`` when
    Europe PMC has no record for the DOI."""
    articles = _search(f"DOI:{doi}", client=client, base_url=base_url, throttle=throttle)
    return articles[0] if articles else None


def _search(
    query: str,
    *,
    client: Optional[httpx.Client],
    base_url: Optional[str],
    throttle: Optional[OAThrottle],
) -> List[PMCArticle]:
    url = _build_search_url(query, base_url=base_url)

    def _get() -> dict:
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if client is not None:
            r = client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)
        else:
            with httpx.Client(follow_redirects=True) as c:
                r = c.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)
        r.raise_for_status()
        return r.json()

    payload = throttle.run_with_retry(_get) if throttle is not None else _get()
    return parse_search_response(payload)


def download_pdf(
    pdf_url: str,
    *,
    client: Optional[httpx.Client] = None,
    throttle: Optional[OAThrottle] = None,
) -> bytes:
    """Download PMC PDF bytes. Transient errors retry via the throttle."""

    def _get() -> bytes:
        from .unpaywall import NotAPdf, _looks_like_pdf

        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if client is not None:
            r = client.get(pdf_url, headers=headers, timeout=DEFAULT_TIMEOUT_S)
        else:
            with httpx.Client(follow_redirects=True) as c:
                r = c.get(pdf_url, headers=headers, timeout=DEFAULT_TIMEOUT_S)
        r.raise_for_status()
        content = r.content
        if not _looks_like_pdf(content, r.headers.get("content-type")):
            raise NotAPdf(
                f"{pdf_url} returned non-PDF bytes "
                f"(content-type={r.headers.get('content-type')!r}) — not a PDF "
                "(PMC ?pdf=render can return an HTML interstitial)"
            )
        return content

    return throttle.run_with_retry(_get) if throttle is not None else _get()
