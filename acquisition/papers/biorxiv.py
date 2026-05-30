"""bioRxiv / medRxiv preprint connector (SPR-07 M4).

bioRxiv and medRxiv expose a public details API
(``https://api.biorxiv.org/details/{server}/...``) returning preprint records,
each carrying a DOI and — load-bearing for this sprint — an AUTHOR-SELECTED
``license`` field (``cc_by``, ``cc_by_nc``, ``cc0``, ``cc_by_nd``, or
``no-reuse`` / ``confidential``). The license is PER-RECORD: a preprint server
is NOT uniformly open. Assuming "preprint server => open" would serve a
"no-reuse" body and void §9, so this connector reads each record's declared
license and passes it to the chokepoint.

The biorxiv license codes are underscore-delimited (``cc_by_nc``); we normalize
to the hyphenated CC short codes the shared licenses_core table matches
(``cc-by-nc``) — that is a SYNTAX normalization (one vocabulary -> the canonical
CC short-code vocabulary), NOT a rights decision. The redistribution verdict for
any code is still the chokepoint's: ``cc-by`` / ``cc-by-sa`` / ``cc0`` ->
servable, ``cc-by-nc`` / ``cc-by-nd`` / ``no_reuse`` / unknown -> gated. No CC
semantics are encoded here.

Identity: the preprint DOI. A preprint later published with a JOURNAL DOI is
recognized as the same work when SPR-04 sees both DOIs on records from different
sources (the published-version record carries the journal DOI; the dedup ladder
collapses on whichever DOI is shared). Within this connector the key is the
preprint DOI.

``both`` server param fetches bioRxiv + medRxiv. Uses ``httpx`` so tests inject
a ``MockTransport`` — NO live HTTP in CI.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from acquisition.papers._pipeline import PaperRecord

DEFAULT_BASE_URL = "https://api.biorxiv.org/details"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.papers.biorxiv)"
DEFAULT_TIMEOUT_S = 20.0
SERVERS = ("biorxiv", "medrxiv")


def _server_source(server: str) -> str:
    return server.strip().lower()


def _normalize_license_code(raw_license: Optional[str]) -> Optional[str]:
    """Map biorxiv's underscore license code to the canonical CC short-code
    vocabulary the shared licenses_core table matches. SYNTAX ONLY — no rights
    verdict is made here; the chokepoint decides servability from the code.

    ``cc_by`` -> ``cc-by``, ``cc_by_nc`` -> ``cc-by-nc``, ``cc0`` -> ``cc0``.
    A ``no-reuse`` / ``confidential`` / empty value is left as-is (or None) so
    the chokepoint deny-by-defaults it. We do NOT inspect the CC family here;
    underscores simply become hyphens."""
    if not raw_license:
        return None
    code = raw_license.strip().lower()
    if not code:
        return None
    # biorxiv uses underscores; the shared CC short-code table uses hyphens.
    # This is a delimiter swap, not a license interpretation.
    return code.replace("_", "-")


def detail_to_record(raw: dict[str, Any], *, server: str) -> PaperRecord:
    """Map ONE biorxiv/medrxiv detail record into the shared PaperRecord.

    The declared license is read from the record's ``license`` field, normalized
    to the canonical CC short-code syntax, and passed to classify — the
    connector never decides servability. The full-text PDF is at the standard
    ``{doi}.full.pdf`` URL on the server's content host; ``has_servable_body`` is
    True so a CC-redistribution preprint can be served, while a ``no-reuse`` one
    gates regardless (its license fails the chokepoint)."""
    doi = raw.get("doi")
    doi = str(doi).strip() if doi else None
    if not doi:
        raise ValueError("biorxiv record has no DOI")
    declared = _normalize_license_code(raw.get("license"))
    src = _server_source(server)
    pdf_url = f"https://www.{src}.org/content/{doi}v{raw.get('version') or 1}.full.pdf"
    authors_raw = raw.get("authors")
    authors: tuple[str, ...] = ()
    if isinstance(authors_raw, str) and authors_raw.strip():
        authors = tuple(a.strip() for a in authors_raw.split(";") if a.strip())
    return PaperRecord(
        source=src,
        source_id=doi,
        title=str(raw.get("title") or "").strip(),
        license=declared,
        license_field="license",
        doi=doi,
        abstract=(str(raw.get("abstract")).strip() if raw.get("abstract") else None),
        authors=authors,
        pdf_url=pdf_url,
        has_servable_body=True,
        legitimate_source=True,  # biorxiv/medrxiv public API is legitimate
        metadata={"server": src, "version": raw.get("version"), "category": raw.get("category")},
    )


def parse_details_response(payload: dict[str, Any], *, server: str) -> list[PaperRecord]:
    """biorxiv ``/details`` JSON -> records. Pure; recorded-response tests target
    this directly. The records live under ``collection``."""
    out: list[PaperRecord] = []
    for r in payload.get("collection", []) or []:
        if isinstance(r, dict):
            try:
                out.append(detail_to_record(r, server=server))
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


def fetch_details(
    *,
    server: str = "biorxiv",
    interval: str = "2024-01-01/2024-12-31",
    cursor: int = 0,
    limit: int = 25,
    client: Optional[httpx.Client] = None,
    base_url: Optional[str] = None,
    throttle: Any = None,
) -> list[PaperRecord]:
    """Fetch a page of preprint details from one server.

    ``server`` is ``biorxiv``, ``medrxiv``, or ``both`` (queries each in turn).
    ``interval`` is biorxiv's date range. ``throttle`` (a SourceThrottle) spaces
    the request per-server + carries the ban sentinel; tests pass a no-op one or
    omit it.
    """
    server = server.strip().lower()
    if server == "both":
        out: list[PaperRecord] = []
        for s in SERVERS:
            out.extend(
                fetch_details(
                    server=s, interval=interval, cursor=cursor, limit=limit,
                    client=client, base_url=base_url, throttle=throttle,
                )
            )
        return out

    base = base_url or os.environ.get("ANTIEK_BIORXIV_BASE_URL", DEFAULT_BASE_URL)
    url = f"{base}/{server}/{interval}/{int(cursor)}"
    if throttle is not None:
        throttle.before_request(f"biorxiv_{server}")
    payload = _http_get(url, client=client)
    records = parse_details_response(payload, server=server)
    return records[: int(limit)] if limit else records
