"""arXiv Atom API client.

Wraps the ``http://export.arxiv.org/api/query`` endpoint. Returns
structured ``ArxivPaper`` records — no printing, no CLI; that's the
upstream ``search_arxiv.py``'s job.

Uses ``httpx`` (already a dep) instead of ``urllib`` so tests can
inject a ``MockTransport`` with no network. Honors a configurable
base URL via the ``ANTIEK_ARXIV_BASE_URL`` env var for staging /
mock servers.

Atom namespace handling: arXiv embeds Atom + OpenSearch elements.
We pull both into the parser so totalResults is exposed alongside
the entry list.
"""

from __future__ import annotations

import os
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional

import httpx

from acquisition.arxiv import ban_state


class ArxivBanned(RuntimeError):
    """Raised when a persisted 429 ban is still in effect.

    Carries the remaining ban time so the caller can log it and route
    to the PDF endpoint or Semantic Scholar fallback instead of
    re-hitting export.arxiv.org during the ban window. Raising BEFORE
    the request is the whole point — it's what breaks the
    re-trigger loop documented in
    tests/regression/agent_failures/banned-until-sentinel-absent.yaml.
    """

    def __init__(self, message: str, *, remaining_seconds: float) -> None:
        super().__init__(message)
        self.remaining_seconds = remaining_seconds


_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
_OPENSEARCH_NS = "{http://a9.com/-/spec/opensearch/1.1/}"

DEFAULT_BASE_URL = "https://export.arxiv.org/api/query"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.arxiv)"
DEFAULT_TIMEOUT_S = 15.0

# arXiv rate-limits: one query / 3s. Callers issuing batches must
# honor this themselves; client itself does not throttle.
_SORT_MAP = {
    "relevance": "relevance",
    "date": "submittedDate",
    "updated": "lastUpdatedDate",
}


@dataclass(frozen=True)
class ArxivPaper:
    """One Atom entry. ``arxiv_id`` is the base id (no version
    suffix); ``version`` is the explicit ``vN`` suffix when present.
    ``abstract`` is the summary with line-wrap collapsed."""

    arxiv_id: str
    version: str
    title: str
    authors: List[str]
    abstract: str
    categories: List[str]
    primary_category: Optional[str]
    published_at: datetime
    updated_at: datetime
    abs_url: str
    pdf_url: str
    raw_id: str = ""  # the full <id> URI as returned by arXiv
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


def _build_search_url(
    *,
    query: Optional[str] = None,
    author: Optional[str] = None,
    category: Optional[str] = None,
    ids: Optional[Iterable[str]] = None,
    max_results: int = 5,
    sort: str = "relevance",
    base_url: Optional[str] = None,
) -> str:
    """Compose the query URL. Mirrors upstream ``search_arxiv.py``
    semantics: ``ids`` short-circuits to ``id_list``; otherwise
    AND-combine ``query``/``author``/``category`` parts."""
    params: list[tuple[str, str]] = []
    if ids:
        params.append(("id_list", ",".join(ids)))
    else:
        parts: list[str] = []
        if query:
            parts.append(f"all:{urllib.parse.quote(query)}")
        if author:
            parts.append(f"au:{urllib.parse.quote(author)}")
        if category:
            parts.append(f"cat:{category}")
        if not parts:
            raise ValueError(
                "search requires one of query/author/category/ids",
            )
        params.append(("search_query", "+AND+".join(parts)))

    params.append(("max_results", str(int(max_results))))
    params.append(("sortBy", _SORT_MAP.get(sort, sort)))
    params.append(("sortOrder", "descending"))

    base = base_url or os.environ.get(
        "ANTIEK_ARXIV_BASE_URL", DEFAULT_BASE_URL,
    )
    return base + "?" + "&".join(f"{k}={v}" for k, v in params)


# ---------------------------------------------------------------------------
# Atom parsing
# ---------------------------------------------------------------------------


def _parse_iso(ts: str) -> datetime:
    """arXiv emits RFC3339 timestamps with ``Z`` suffix. Parse to
    timezone-aware UTC."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_entry(entry: ET.Element) -> ArxivPaper:
    """One Atom ``<entry>`` → ``ArxivPaper``."""
    title_el = entry.find("a:title", _ATOM_NS)
    id_el = entry.find("a:id", _ATOM_NS)
    summary_el = entry.find("a:summary", _ATOM_NS)
    published_el = entry.find("a:published", _ATOM_NS)
    updated_el = entry.find("a:updated", _ATOM_NS)

    if (
        title_el is None or id_el is None or summary_el is None
        or published_el is None or updated_el is None
    ):
        raise ValueError("arXiv entry missing required fields")

    raw_id = (id_el.text or "").strip()
    full_id = (
        raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id
    )
    base_id = full_id.split("v")[0] if "v" in full_id else full_id
    version = full_id[len(base_id):] if full_id != base_id else ""

    authors = [
        (a.find("a:name", _ATOM_NS).text or "").strip()
        for a in entry.findall("a:author", _ATOM_NS)
        if a.find("a:name", _ATOM_NS) is not None
    ]
    cats = [
        c.get("term", "") for c in entry.findall("a:category", _ATOM_NS)
        if c.get("term")
    ]
    primary_el = entry.find(
        "{http://arxiv.org/schemas/atom}primary_category",
    )
    primary = primary_el.get("term") if primary_el is not None else None

    return ArxivPaper(
        arxiv_id=base_id,
        version=version,
        title=" ".join((title_el.text or "").split()),
        authors=authors,
        abstract=" ".join((summary_el.text or "").split()),
        categories=cats,
        primary_category=primary,
        published_at=_parse_iso((published_el.text or "").strip()),
        updated_at=_parse_iso((updated_el.text or "").strip()),
        abs_url=f"https://arxiv.org/abs/{base_id}",
        pdf_url=f"https://arxiv.org/pdf/{base_id}",
        raw_id=raw_id,
    )


def _parse_response(xml_bytes: bytes) -> List[ArxivPaper]:
    """Atom feed → list of papers. Returns [] when the feed is empty
    (zero results); raises ``ValueError`` on malformed XML."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"arXiv response is not valid XML: {e!r}") from e
    return [_parse_entry(e) for e in root.findall("a:entry", _ATOM_NS)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _http_get(
    url: str, *, client: Optional[httpx.Client] = None,
) -> bytes:
    """One GET. Caller can inject an ``httpx.Client`` with a
    ``MockTransport`` for tests; otherwise we build a short-lived
    client.

    Two harness guards wrap the request (closing the arxiv-ingestion
    regression fixtures):

    1. **Ban guard (pre-request).** If a 429 ban is still in effect per
       ``ban_state``, raise ``ArxivBanned`` BEFORE issuing the request.
       This is the load-bearing fix — re-hitting export.arxiv.org during
       a ban extends it. The caller routes to a fallback instead.
    2. **SSL bootstrap (pre-request, only when building our own
       client).** Ensure a CA bundle is resolvable so a python.org
       Python without system certs fails loud with a remedy rather than
       a buried SSLCertVerificationError. Skipped when a client is
       injected (tests own their transport).
    3. **429 capture (post-response).** On a 429, persist the ban
       sentinel so subsequent calls short-circuit, then re-raise.
    """
    # Guard 1 — honor an in-effect ban before touching the network.
    remaining = ban_state.remaining()
    if remaining is not None:
        raise ArxivBanned(
            f"export.arxiv.org is rate-limit-banned for ~{int(remaining.total_seconds())}s more; "
            f"route to the PDF endpoint or Semantic Scholar fallback instead of re-hitting it",
            remaining_seconds=remaining.total_seconds(),
        )

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if client is not None:
        r = client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    else:
        # Guard 2 — only when we own the client; injected clients (tests)
        # bring their own transport and cert config.
        from runtime.ssl_bootstrap import ensure_ssl_certs

        ensure_ssl_certs()
        with httpx.Client() as c:
            r = c.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

    # Guard 3 — capture a 429 into the shared sentinel so the next
    # caller (this process or another) short-circuits at Guard 1.
    if r.status_code == 429:
        ban_state.mark_banned(reason=f"429 from {url}")
        r.raise_for_status()  # raises httpx.HTTPStatusError

    r.raise_for_status()
    return r.content


def search(
    *,
    query: Optional[str] = None,
    author: Optional[str] = None,
    category: Optional[str] = None,
    max_results: int = 5,
    sort: str = "relevance",
    client: Optional[httpx.Client] = None,
    base_url: Optional[str] = None,
) -> List[ArxivPaper]:
    """Query arXiv. At least one of query/author/category must be set.

    ``sort`` is one of ``relevance`` / ``date`` / ``updated``.
    ``client`` is an injectable ``httpx.Client`` — tests pass a
    ``MockTransport``-backed client; production passes ``None``."""
    url = _build_search_url(
        query=query, author=author, category=category,
        max_results=max_results, sort=sort, base_url=base_url,
    )
    body = _http_get(url, client=client)
    return _parse_response(body)


def fetch_by_id(
    arxiv_id: str,
    *,
    client: Optional[httpx.Client] = None,
    base_url: Optional[str] = None,
) -> Optional[ArxivPaper]:
    """Fetch a single paper by id. Returns ``None`` when arXiv
    returns no entries (id unknown)."""
    url = _build_search_url(
        ids=[arxiv_id], max_results=1, base_url=base_url,
    )
    body = _http_get(url, client=client)
    papers = _parse_response(body)
    return papers[0] if papers else None
