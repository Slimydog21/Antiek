"""Semantic Scholar (S2) connector (SPR-07 M3).

The Semantic Scholar Academic Graph API returns rich metadata + an
``openAccessPdf`` object for open-access records and an ``abstract`` for many
closed ones. Each record carries an ``externalIds`` map (DOI / ArXiv / ...) and
a ``corpusId`` (the S2-local id).

THE LOAD-BEARING CASE FOR THIS SPRINT lives here: an S2 record with NO
``openAccessPdf`` (closed access) and an all-rights-reserved / unknown license
must ingest GATED — metadata + abstract into the graph for private search, body
NEVER fetched or served. That is the catastrophic-failure this sprint makes
structurally impossible: there is no body to fetch (``has_servable_body`` is
False, ``pdf_url`` is None), and the license — read from ``openAccessPdf.license``
when present, else None — flows through the chokepoint, which deny-by-defaults a
missing license to ``restricted_pending_opt_in``.

S2's ``openAccessPdf.license`` can be a CC code; a record with an OA PDF + a CC
redistribution license lands servable, basis naming ``S2 openAccessPdf.license``.
The license string is passed VERBATIM to classify — no inline CC parsing here.

Identity precedence: DOI > arXiv id (both from ``externalIds``) > S2 corpusId —
the corpusId is used as the dedup key ONLY when no DOI/arXiv id is present.

Uses ``httpx`` so tests inject a ``MockTransport`` — NO live HTTP in CI.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from acquisition.papers._pipeline import PaperRecord

DEFAULT_BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.papers.semantic_scholar)"
DEFAULT_TIMEOUT_S = 20.0
S2_SOURCE = "semantic_scholar"
S2_THROTTLE_KEY = "semantic_scholar"

# The fields S2 must return for the rights + identity decision. ``openAccessPdf``
# is the OA body signal; ``externalIds`` carries DOI / ArXiv for dedup precedence.
DEFAULT_FIELDS = "title,abstract,externalIds,openAccessPdf,authors,corpusId"


def _doi_arxiv(external_ids: Any) -> tuple[Optional[str], Optional[str]]:
    """Pull (DOI, arXiv id) out of S2's ``externalIds`` map. The keys S2 uses
    are ``DOI`` and ``ArXiv``."""
    if not isinstance(external_ids, dict):
        return None, None
    doi = external_ids.get("DOI")
    arxiv = external_ids.get("ArXiv")
    doi = str(doi).strip() if doi else None
    arxiv = str(arxiv).strip() if arxiv else None
    return doi, arxiv


def _authors(raw: dict[str, Any]) -> tuple[str, ...]:
    out: list[str] = []
    for a in raw.get("authors") or []:
        if isinstance(a, dict):
            name = a.get("name")
            if isinstance(name, str) and name.strip():
                out.append(name.strip())
    return tuple(out)


def paper_to_record(raw: dict[str, Any]) -> PaperRecord:
    """Map ONE S2 paper into the shared PaperRecord.

    Closed-access (no ``openAccessPdf``): ``pdf_url`` is None,
    ``has_servable_body`` is False, and the license is None -> the chokepoint
    gates it. Open-access: the ``openAccessPdf.url`` is the fetchable body and
    ``openAccessPdf.license`` is the declared license string passed verbatim to
    classify."""
    corpus_id = str(raw.get("corpusId") or raw.get("paperId") or "").strip()
    doi, arxiv = _doi_arxiv(raw.get("externalIds"))
    if not corpus_id and not doi and not arxiv:
        raise ValueError("S2 paper has no corpusId / DOI / arXiv id")

    oa = raw.get("openAccessPdf")
    pdf_url: Optional[str] = None
    license_str: Optional[str] = None
    license_field: Optional[str] = None
    has_body = False
    if isinstance(oa, dict) and oa.get("url"):
        pdf_url = str(oa["url"]).strip()
        has_body = bool(pdf_url)
        lic = oa.get("license")
        # The declared license string for the OA PDF; passed verbatim to
        # classify(). None when S2 has an OA PDF but no declared license — the
        # chokepoint then deny-by-defaults it to gated (an OA url is "free to
        # read", not necessarily "free to redistribute").
        license_str = str(lic).strip() if lic else None
        license_field = "openAccessPdf.license"

    abstract = raw.get("abstract")
    return PaperRecord(
        source=S2_SOURCE,
        source_id=corpus_id or (doi or arxiv or ""),
        title=str(raw.get("title") or "").strip(),
        license=license_str,
        license_field=license_field,
        doi=doi,
        arxiv_id=arxiv,
        abstract=(str(abstract).strip() if abstract else None),
        authors=_authors(raw),
        pdf_url=pdf_url,
        has_servable_body=has_body,
        legitimate_source=True,  # S2 is a legitimate public academic-graph API
        metadata={"corpusId": corpus_id},
    )


def parse_search_response(payload: dict[str, Any]) -> list[PaperRecord]:
    """S2 ``/paper/search`` JSON -> records. Pure; recorded-response tests
    target this directly. S2 returns hits under ``data``."""
    out: list[PaperRecord] = []
    for p in payload.get("data", []) or []:
        if isinstance(p, dict):
            try:
                out.append(paper_to_record(p))
            except ValueError:
                continue
    return out


def _http_get(
    url: str, *, api_key: Optional[str], client: Optional[httpx.Client]
) -> dict:
    # HOST-GLOBAL arXiv GOVERNANCE (SPR-09 root fix): ``url`` is built from a
    # ``base_url`` that is env/param-overridable, so the actual send is routed
    # through the host-based gate. The default ``api.semanticscholar.org`` is a
    # non-arXiv host → ``govern_if_arxiv`` is a no-op and the send is issued
    # directly (the S2 ``throttle`` in ``search_papers`` already spaced it); were
    # the base ever an arXiv host the send would go through the host-global flock
    # + >=3s spacing + 429 ban sentinel on the shared throttle state. Host-based,
    # not module-location-based — uniform with the openaccess fetchers. The
    # client carries the per-hop request hook so an arXiv REDIRECT target is
    # governed too; ``govern_if_arxiv`` governs the initial hop (re-entrant, no
    # double-wait, no deadlock).
    from acquisition.arxiv.rate_governor import (
        arxiv_governed_client,
        canonical_arxiv_throttle,
        govern_if_arxiv,
        install_arxiv_request_hook,
    )

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if api_key:
        headers["x-api-key"] = api_key
    if client is not None:
        install_arxiv_request_hook(client, throttle=canonical_arxiv_throttle())

        def _send() -> httpx.Response:
            return client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

        r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
    else:
        with arxiv_governed_client(throttle=canonical_arxiv_throttle()) as c:
            def _send() -> httpx.Response:
                return c.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

            r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
    r.raise_for_status()
    return r.json()


def search_papers(
    *,
    query: str,
    limit: int = 25,
    fields: str = DEFAULT_FIELDS,
    api_key: Optional[str] = None,
    client: Optional[httpx.Client] = None,
    base_url: Optional[str] = None,
    throttle: Any = None,
) -> list[PaperRecord]:
    """Query S2 for papers matching ``query``. ``throttle`` (a SourceThrottle)
    spaces the request + carries the ban sentinel; tests pass a no-op-sleep one
    or omit it."""
    import urllib.parse

    base = base_url or os.environ.get("ANTIEK_S2_BASE_URL", DEFAULT_BASE_URL)
    key = api_key if api_key is not None else os.environ.get("ANTIEK_S2_API_KEY")
    qs = urllib.parse.urlencode(
        {"query": query, "limit": int(limit), "fields": fields}
    )
    url = f"{base}?{qs}"
    if throttle is not None:
        throttle.before_request(S2_THROTTLE_KEY)
    payload = _http_get(url, api_key=key, client=client)
    return parse_search_response(payload)
