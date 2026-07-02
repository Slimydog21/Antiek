"""DOAJ journal-level open-access confirmation adapter.

DOAJ (https://doaj.org/api/docs) is the Directory of Open Access Journals.
Unlike Unpaywall/PMC it is NOT a full-text host — it confirms that a JOURNAL
is open access and carries a journal-level license (the license a journal's
articles are published under). This adapter looks up an article by DOI, reads
the journal-level license, and resolves the OA verdict from it.

THE INVARIANT in action: DOAJ confirming a journal is "open access" is NOT a
redistribution grant — a DOAJ journal can be CC-BY-NC (gated) or CC-BY
(servable). The decision is the journal's declared CC license, resolved
deny-by-default; a DOAJ record with no license still gates.

DOAJ's license block is structured (``{"type": "CC BY", "url": ".../by/4.0/"}``)
— we prefer the explicit ``url`` (a CC URI the resolver matches directly),
falling back to the ``type`` short form.

IMPORTANT (measured in the M1 spike): the DOAJ ARTICLE-search response does
NOT carry the license — the journal block on an article record has only
ISSN/title/publisher. The license lives on the JOURNAL record. So when an
article carries no article-level license, ``confirm_by_doi`` does a follow-up
``/search/journals/issn:<issn>`` lookup and reads the journal-level license
from there. Without that follow-up, DOAJ would gate every article
deny-by-default for lack of a visible license — which is safe but useless.

DOAJ does not host PDFs, so this adapter has no ``download_pdf`` — it pairs
with another resolver (or a publisher fulltext link) for the actual bytes.

Uses ``httpx`` so tests inject a ``MockTransport`` — NO live HTTP in CI.
"""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from typing import Any

import httpx

from .licenses import LicenseResolution, resolve_oa_license
from .throttle import OAThrottle

DEFAULT_BASE_URL = "https://doaj.org/api/v2"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.openaccess)"
DEFAULT_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class DOAJArticle:
    """A DOAJ article + its journal-level OA verdict.

    ``in_doaj`` is True when DOAJ returned a record (the journal is a
    confirmed OA journal). ``fulltext_url`` is the publisher/repository link
    DOAJ carries (DOAJ doesn't host bytes). ``resolution`` is the
    deny-by-default verdict from the journal-level CC license."""

    doi: str | None
    title: str
    in_doaj: bool
    fulltext_url: str | None
    license_uri: str | None
    resolution: LicenseResolution
    issns: tuple[str, ...] = ()
    source: str = "doaj"


def _extract_license_uri(bibjson: dict[str, Any]) -> str | None:
    """Pull the CC URI from a DOAJ bibjson license block. Article-level
    license wins when present; else the journal-level license. Prefer the
    explicit CC ``url``; fall back to the ``type`` short form."""
    candidates = bibjson.get("license") or (bibjson.get("journal") or {}).get("license")
    if not candidates:
        return None
    first = candidates[0] if isinstance(candidates, list) else candidates
    if not isinstance(first, dict):
        return None
    url = first.get("url")
    if url:
        return url
    # No URL — fall back to the short type ("CC BY-NC-ND"), normalised to a
    # CC fragment so the resolver's CC rows match.
    t = (first.get("type") or "").strip().lower().replace(" ", "-")
    if t.startswith("cc-by"):
        return f"creativecommons.org/licenses/{t[len('cc-'):]}/4.0/"
    if t in ("cc0", "cc-zero"):
        return "creativecommons.org/publicdomain/zero/1.0/"
    return first.get("type")


def _extract_fulltext_url(bibjson: dict[str, Any]) -> str | None:
    for link in bibjson.get("link") or []:
        if (link.get("type") or "").lower() == "fulltext":
            return link.get("url")
    return None


def parse_search_response(payload: dict[str, Any]) -> list[DOAJArticle]:
    """DOAJ ``/search/articles`` JSON -> articles. Pure; the recorded-response
    tests target this directly."""
    out: list[DOAJArticle] = []
    for res in payload.get("results") or []:
        bib = res.get("bibjson") or {}
        ids = bib.get("identifier") or []
        doi = next(
            (i.get("id") for i in ids if (i.get("type") or "").lower() == "doi"),
            None,
        )
        license_uri = _extract_license_uri(bib)
        issns = tuple((bib.get("journal") or {}).get("issns") or [])
        out.append(
            DOAJArticle(
                doi=doi,
                title=bib.get("title") or "",
                in_doaj=True,
                fulltext_url=_extract_fulltext_url(bib),
                license_uri=license_uri,
                resolution=resolve_oa_license(license_uri),
                issns=issns,
            )
        )
    return out


def parse_journal_response(payload: dict[str, Any]) -> str | None:
    """DOAJ ``/search/journals`` JSON -> the journal-level CC license URI (or
    None). Pure; the recorded-response tests target this directly."""
    results = payload.get("results") or []
    if not results:
        return None
    return _extract_license_uri(results[0].get("bibjson") or {})


def _base(base_url: str | None) -> str:
    return base_url or os.environ.get("ANTIEK_DOAJ_BASE_URL", DEFAULT_BASE_URL)


def _build_article_url(doi: str, *, base_url: str | None) -> str:
    # DOAJ's article search-by-DOI path. The DOI is path-encoded.
    return f"{_base(base_url)}/search/articles/doi:{urllib.parse.quote(doi, safe='')}"


def _build_journal_url(issn: str, *, base_url: str | None) -> str:
    return f"{_base(base_url)}/search/journals/issn:{urllib.parse.quote(issn, safe='')}"


def _get_json(
    url: str, *, client: httpx.Client | None, throttle: OAThrottle | None
) -> dict:
    def _get() -> dict:
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
        return r.json()

    return throttle.run_with_retry(_get) if throttle is not None else _get()


def journal_license_by_issn(
    issn: str,
    *,
    client: httpx.Client | None = None,
    base_url: str | None = None,
    throttle: OAThrottle | None = None,
) -> str | None:
    """Look up a DOAJ journal by ISSN and return its CC license URI (or None)."""
    payload = _get_json(
        _build_journal_url(issn, base_url=base_url), client=client, throttle=throttle
    )
    return parse_journal_response(payload)


def confirm_by_doi(
    doi: str,
    *,
    client: httpx.Client | None = None,
    base_url: str | None = None,
    throttle: OAThrottle | None = None,
) -> DOAJArticle | None:
    """Confirm a DOI is in a DOAJ open-access journal + resolve its license.

    The article record carries the ISSN but NOT the license (measured in the
    M1 spike); when no article-level license is present we follow up with a
    journal-by-ISSN lookup and resolve the journal-level license. Returns
    ``None`` when DOAJ has no article record for the DOI."""
    payload = _get_json(
        _build_article_url(doi, base_url=base_url), client=client, throttle=throttle
    )
    articles = parse_search_response(payload)
    if not articles:
        return None
    art = articles[0]
    if art.license_uri is not None:
        return art

    # No article-level license — resolve via the journal record.
    for issn in art.issns:
        try:
            jl = journal_license_by_issn(
                issn, client=client, base_url=base_url, throttle=throttle
            )
        except Exception:
            continue
        if jl:
            return DOAJArticle(
                doi=art.doi,
                title=art.title,
                in_doaj=True,
                fulltext_url=art.fulltext_url,
                license_uri=jl,
                resolution=resolve_oa_license(jl),
                issns=art.issns,
            )
    return art
