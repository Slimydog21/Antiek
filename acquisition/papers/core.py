"""CORE aggregator connector (SPR-07 M2).

CORE (https://core.ac.uk) aggregates open-access research from repositories
worldwide. Its ``/search/works`` API returns works each carrying a DOI, a
declared license (CORE's ``license`` field), and download URLs.

This is a thin connector: it queries CORE, maps each work into the shared
:class:`acquisition.papers._pipeline.PaperRecord`, and lets the shared pipeline do
the classification (the chokepoint), dedup-ref projection, and staging. It
reads the per-record declared license string and passes it VERBATIM to
``classify`` — no inline CC parsing here. A CORE work whose ``license`` is a CC
redistribution license lands servable (basis names ``CORE work.license``); a
work with no/unknown license lands gated (deny-by-default).

Intellectual honesty (rigor #1): CORE marks works "open" whose actual PDF is
gone or is an HTML landing page. We never upgrade a record to servable on
CORE's word — the license basis AND a real extractable body (the shared
``assert_pdf`` gate at fetch) are both required. ``has_servable_body`` is set
only when CORE offers a download URL; the PDF-vs-HTML reality check happens at
fetch via the shared ``pdf_detect.assert_pdf``.

Uses ``httpx`` so tests inject a ``MockTransport`` — NO live HTTP in CI. The
shared ``SourceThrottle`` (key ``core``) spaces requests + carries the
cross-process ban sentinel.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from acquisition.papers._pipeline import PaperRecord

DEFAULT_BASE_URL = "https://api.core.ac.uk/v3/search/works"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.papers.core)"
DEFAULT_TIMEOUT_S = 20.0
CORE_SOURCE = "core"
CORE_THROTTLE_KEY = "core"


def _first_doi(raw: dict[str, Any]) -> str | None:
    doi = raw.get("doi")
    if isinstance(doi, str) and doi.strip():
        return doi.strip()
    # CORE sometimes nests identifiers in an ``identifiers`` list.
    for ident in raw.get("identifiers") or []:
        if isinstance(ident, dict) and ident.get("type") == "DOI":
            v = ident.get("identifier")
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _pdf_url(raw: dict[str, Any]) -> str | None:
    """CORE's downloadable full-text URL, when present. ``downloadUrl`` is the
    direct file; ``fullTextIdentifier`` is a fallback. Either may be an HTML
    landing page — the shared ``assert_pdf`` gate catches that at fetch."""
    for key in ("downloadUrl", "fullTextIdentifier"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _authors(raw: dict[str, Any]) -> tuple[str, ...]:
    out: list[str] = []
    for a in raw.get("authors") or []:
        if isinstance(a, dict):
            name = a.get("name")
        else:
            name = a
        if isinstance(name, str) and name.strip():
            out.append(name.strip())
    return tuple(out)


def work_to_record(raw: dict[str, Any]) -> PaperRecord:
    """Map ONE CORE work into the shared PaperRecord. The declared license
    string is read from CORE's ``license`` field and passed through verbatim;
    classification (servable vs gated) is the chokepoint's job."""
    core_id = str(raw.get("id") or raw.get("coreId") or "").strip()
    doi = _first_doi(raw)
    if not core_id and not doi:
        raise ValueError("CORE work has neither id nor DOI")
    # ``license`` is CORE's declared rights string for this work (a CC URI/code
    # or None). We pass it straight to classify() — never interpret it here.
    license_str = raw.get("license")
    license_str = str(license_str).strip() if license_str else None
    pdf = _pdf_url(raw)
    return PaperRecord(
        source=CORE_SOURCE,
        source_id=core_id or (doi or ""),
        title=str(raw.get("title") or "").strip(),
        license=license_str,
        license_field="work.license",
        doi=doi,
        arxiv_id=str(raw["arxivId"]).strip() if raw.get("arxivId") else None,
        abstract=(str(raw.get("abstract")).strip() if raw.get("abstract") else None),
        authors=_authors(raw),
        pdf_url=pdf,
        has_servable_body=bool(pdf),
        legitimate_source=True,  # CORE is a legitimate open-access aggregator
        metadata={"oa_status": raw.get("oai"), "year": raw.get("yearPublished")},
    )


def parse_works_response(payload: dict[str, Any]) -> list[PaperRecord]:
    """CORE ``/search/works`` JSON -> records. Pure; the recorded-response
    tests target this directly. CORE returns hits under ``results``."""
    out: list[PaperRecord] = []
    for w in payload.get("results", []) or []:
        if isinstance(w, dict):
            try:
                out.append(work_to_record(w))
            except ValueError:
                continue
    return out


def _http_post(
    url: str, body: dict[str, Any], *, api_key: str | None, client: httpx.Client | None
) -> dict:
    # HOST-GLOBAL arXiv GOVERNANCE (SPR-09 host-based seam): ``url`` is
    # env/param-overridable (``ANTIEK_CORE_BASE_URL`` / ``base_url``), so the
    # actual HTTP send is routed through ``govern_if_arxiv`` on the resolved URL.
    # The default api.core.ac.uk host is non-arXiv → the send is issued DIRECTLY
    # (govern_if_arxiv is a no-op; CORE's own ``SourceThrottle`` already spaced
    # it before this call), so behavior is preserved. Were the base ever an arXiv
    # host it would route through the host-global flock + >=3s spacing + 429 ban
    # sentinel on the shared throttle state. The client (caller-passed or
    # self-built) also carries the per-hop request hook so EVERY hop whose host is
    # arXiv — initial OR a redirect target — is governed by construction.
    from acquisition.arxiv.rate_governor import (
        arxiv_governed_client,
        canonical_arxiv_throttle,
        govern_if_arxiv,
        install_arxiv_request_hook,
    )

    headers = {"User-Agent": DEFAULT_USER_AGENT, "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if client is not None:
        install_arxiv_request_hook(client, throttle=canonical_arxiv_throttle())

        def _send() -> httpx.Response:
            return client.post(url, json=body, headers=headers, timeout=DEFAULT_TIMEOUT_S)

        r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
    else:
        with arxiv_governed_client(throttle=canonical_arxiv_throttle()) as c:
            def _send() -> httpx.Response:
                return c.post(url, json=body, headers=headers, timeout=DEFAULT_TIMEOUT_S)

            r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
    r.raise_for_status()
    return r.json()


def search_works(
    *,
    query: str,
    limit: int = 25,
    api_key: str | None = None,
    client: httpx.Client | None = None,
    base_url: str | None = None,
    throttle: Any = None,
) -> list[PaperRecord]:
    """Query CORE for works matching ``query``.

    ``throttle`` (a ``substrate.source_throttle.SourceThrottle``) spaces the
    request + raises ``SourceBanned`` while CORE is banned; the orchestrator
    catches that to rotate sources. Tests pass a throttle with a no-op sleep,
    or omit it.
    """
    base = base_url or os.environ.get("ANTIEK_CORE_BASE_URL", DEFAULT_BASE_URL)
    key = api_key if api_key is not None else os.environ.get("ANTIEK_CORE_API_KEY")
    body = {"q": query, "limit": int(limit)}
    if throttle is not None:
        throttle.before_request(CORE_THROTTLE_KEY)
    payload = _http_post(base, body, api_key=key, client=client)
    return parse_works_response(payload)
