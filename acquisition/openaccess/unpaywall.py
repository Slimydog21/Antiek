"""Unpaywall full-text resolution adapter.

Unpaywall (https://unpaywall.org/products/api) maps a DOI to its best legal
open-access location: a PDF URL + the OA license + the OA status (gold /
green / hybrid / bronze / closed). This adapter resolves a DOI to that best
location and (optionally) downloads the PDF.

THE INVARIANT in action: Unpaywall's ``best_oa_location`` can be a BRONZE
location (free-to-read on the publisher site, license ``None``). Unpaywall
will happily hand us that URL — but bronze is not a redistribution grant, so
the OA license resolver gates it. We resolve the license from the location's
declared ``license`` field, never from "Unpaywall gave us a URL."

Unpaywall requires an ``email`` query param (their politeness convention,
analogous to OpenAlex's mailto). Uses ``httpx`` so tests inject a
``MockTransport`` — NO live HTTP in CI.
"""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .licenses import LicenseResolution, resolve_oa_license
from .throttle import POLITE_POOL_MAILTO, OAThrottle

DEFAULT_BASE_URL = "https://api.unpaywall.org/v2"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.openaccess)"
DEFAULT_TIMEOUT_S = 15.0


class NotAPdf(ValueError):
    """The fetched bytes are not a PDF (e.g. an HTML landing page served
    200-OK). A counted, recoverable failure mode: the caller should try the
    next candidate URL rather than abort the item. Subclasses ValueError so
    OAThrottle.run_with_retry re-raises it immediately (a landing page will
    not become a PDF on retry) instead of burning the retry budget."""


def _looks_like_pdf(content: bytes, content_type: Optional[str]) -> bool:
    """True when the response is plausibly a PDF. Rejects an HTML/text body
    by content-type, then confirms the ``%PDF-`` magic bytes (first 1KB,
    leading whitespace tolerated)."""
    if content_type:
        ct = content_type.lower()
        if "application/pdf" not in ct and ("text/html" in ct or "text/plain" in ct):
            return False
    head = content[:1024].lstrip()
    return head.startswith(b"%PDF-")


@dataclass(frozen=True)
class OAFullText:
    """A resolved best-OA full-text location for a DOI.

    ``pdf_url`` is the directly-fetchable PDF (``None`` when the best OA
    location is a landing page only — a counted failure mode, not a servable
    location). ``resolution`` carries the deny-by-default license verdict
    derived from ``license_uri``."""

    doi: str
    is_oa: bool
    oa_status: Optional[str]
    pdf_url: Optional[str]
    landing_url: Optional[str]
    license_uri: Optional[str]
    resolution: LicenseResolution
    source: str = "unpaywall"


def _build_url(doi: str, *, email: str, base_url: Optional[str]) -> str:
    base = base_url or os.environ.get("ANTIEK_UNPAYWALL_BASE_URL", DEFAULT_BASE_URL)
    return f"{base}/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}"


def parse_response(payload: dict[str, Any], doi: str) -> OAFullText:
    """Unpaywall DOI JSON -> ``OAFullText``. Pure; the recorded-response
    tests target this directly.

    The license precedence: when the best OA location declares a license we
    resolve THAT; when it declares none we still pass the (None) license
    through the resolver so bronze/green-without-license gates by default —
    we do NOT fall back to oa_status as a redistribution signal."""
    best = payload.get("best_oa_location") or {}
    license_uri = best.get("license")
    return OAFullText(
        doi=doi,
        is_oa=bool(payload.get("is_oa")),
        oa_status=payload.get("oa_status"),
        pdf_url=best.get("url_for_pdf"),
        landing_url=best.get("url"),
        license_uri=license_uri,
        resolution=resolve_oa_license(license_uri),
    )


def resolve_doi(
    doi: str,
    *,
    email: str = POLITE_POOL_MAILTO,
    client: Optional[httpx.Client] = None,
    base_url: Optional[str] = None,
    throttle: Optional[OAThrottle] = None,
) -> OAFullText:
    """Resolve a DOI to its best OA full-text location + license verdict.

    A 404 (DOI unknown to Unpaywall) propagates as ``HTTPStatusError`` —
    permanent, so the batch records a per-item miss without retrying."""
    url = _build_url(doi, email=email, base_url=base_url)

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
    return parse_response(payload, doi)


def download_pdf(
    pdf_url: str,
    *,
    client: Optional[httpx.Client] = None,
    throttle: Optional[OAThrottle] = None,
) -> bytes:
    """Download PDF bytes from a resolved OA URL. Transient errors retry via
    the throttle; the caller is responsible for verifying the bytes are a PDF
    (a landing page masquerading as a PDF is a counted failure mode)."""

    def _get() -> bytes:
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
                f"(content-type={r.headers.get('content-type')!r}, "
                f"head={content[:8]!r}) — likely a landing page, not a PDF"
            )
        return content

    return throttle.run_with_retry(_get) if throttle is not None else _get()
