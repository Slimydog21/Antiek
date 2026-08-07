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
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from acquisition.arxiv.ids import looks_like_error_feed, split_id_version

if TYPE_CHECKING:
    from acquisition.arxiv.throttle import ArxivThrottle


class ArxivErrorFeed(ValueError):
    """arXiv returned its Atom error feed (a malformed/invalid query), not papers.

    Subclasses ``ValueError`` so existing callers that already treat a parse
    failure as a per-request error catch it for free, while a caller that wants to
    distinguish "the query was rejected" from "the XML was malformed" can branch
    on this type.
    """

_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
_OPENSEARCH_NS = "{http://a9.com/-/spec/opensearch/1.1/}"

DEFAULT_BASE_URL = "https://export.arxiv.org/api/query"
DEFAULT_TIMEOUT_S = 15.0

# arXiv's rate policy asks clients to carry a contact so the operator can be
# reached BEFORE the whole source IP is banned (the exact failure that has bitten
# this box). The contact is env-configurable — never a hardcoded personal address
# in a shared codebase — and defaults to the project contact page when unset. The
# ``~/.claude/skills/arxiv`` port carries the same polite-pool discipline.
_DEFAULT_CONTACT = "+https://antiek.ai/contact"


def default_user_agent() -> str:
    """The arXiv User-Agent, including a reachable contact per arXiv policy.

    Reads ``ANTIEK_ARXIV_CONTACT`` (e.g. ``mailto:ops@antiek.ai``) so a deployment
    can advertise a real inbox; falls back to the project contact URL. Computed
    per call so a test or a re-configured process picks up the current env.
    """
    contact = os.environ.get("ANTIEK_ARXIV_CONTACT", "").strip() or _DEFAULT_CONTACT
    return f"Antiek/0.1 ({contact}; acquisition.arxiv)"


# Backward-compatible module constant (importers such as ``pdf_fetch`` read this).
# Bound at import from the current env; ``default_user_agent()`` is the live seam.
DEFAULT_USER_AGENT = default_user_agent()

# arXiv rate-limits: one query / 3s. This export SEARCH API
# (``export.arxiv.org``) is the endpoint that historically IP-banned the box
# (project_researchmaxx_arxiv.md, 2026-05-17). SPR-09 M1: every GET here is
# routed through the host-global rate governor
# (``acquisition.arxiv.rate_governor.governed_request``) so the >=3s spacing +
# 429 ``banned_until`` sentinel hold across ALL arXiv jobs on the box — a bare
# per-call in-process timer (the prior pattern) let two host jobs both fire in
# one 3s window, which is the exact race that banned the box. The throttle is
# threaded in by the CLIs (which already construct an ``ArxivThrottle``); when a
# caller omits it the governed seam owns the CANONICAL throttle, so even a caller
# that forgets is host-globally spaced.
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
    authors: list[str]
    abstract: str
    categories: list[str]
    primary_category: str | None
    published_at: datetime
    updated_at: datetime
    abs_url: str
    pdf_url: str
    # The license URI arXiv declares for THIS paper (the
    # {http://arxiv.org/schemas/atom}license element). ``None`` when the
    # entry carries no license element. This is the rights anchor: the
    # license — not the fact that arXiv is free to read — is what decides
    # whether Antiek may redistribute the full text. See
    # ``acquisition.arxiv.licenses`` for the URI → servable-class mapping.
    license_uri: str | None = None
    raw_id: str = ""  # the full <id> URI as returned by arXiv
    metadata: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


def _build_search_url(
    *,
    query: str | None = None,
    author: str | None = None,
    category: str | None = None,
    ids: Iterable[str] | None = None,
    max_results: int = 5,
    sort: str = "relevance",
    base_url: str | None = None,
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
        dt = dt.replace(tzinfo=UTC)
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
    # Error-feed trap: a malformed query returns a 200 Atom feed whose single
    # entry's <id> is arXiv's ``…/api/errors#…`` sentinel. Parsing it would mint a
    # garbage ArxivPaper; reject the whole response instead (SPR-arxiv-clean).
    if looks_like_error_feed(raw_id):
        raise ArxivErrorFeed(
            f"arXiv returned an error-feed entry ({raw_id!r}); the query was "
            "rejected upstream — not a paper record.",
        )
    full_id = (
        raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id
    )
    # Robust version split anchored to a trailing ``vN`` — replaces the fragile
    # ``full_id.split("v")[0]`` (which partitions on the first ``v`` anywhere).
    base_id, version = split_id_version(full_id)

    authors = [
        (name_el.text or "").strip()
        for a in entry.findall("a:author", _ATOM_NS)
        if (name_el := a.find("a:name", _ATOM_NS)) is not None
    ]
    cats = [
        c.get("term", "") for c in entry.findall("a:category", _ATOM_NS)
        if c.get("term")
    ]
    primary_el = entry.find(
        "{http://arxiv.org/schemas/atom}primary_category",
    )
    primary = primary_el.get("term") if primary_el is not None else None

    # Same arXiv schema namespace as primary_category. The license URI
    # is the element TEXT (not an attribute). Absent element → None,
    # which the licenses mapping treats as "no grant → gated".
    lic_el = entry.find("{http://arxiv.org/schemas/atom}license")
    license_uri = (
        lic_el.text.strip() if lic_el is not None and lic_el.text else None
    )

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
        license_uri=license_uri,
        raw_id=raw_id,
    )


def _parse_response(xml_bytes: bytes) -> list[ArxivPaper]:
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
    url: str,
    *,
    client: httpx.Client | None = None,
    throttle: ArxivThrottle | None = None,
) -> bytes:
    """One GET to the export SEARCH API, host-rate-governed (SPR-09 M1).

    This is the 4th arXiv egress (the export-search API at
    ``export.arxiv.org/api/query``) and the one that historically IP-banned the
    box. The send is routed through
    ``acquisition.arxiv.rate_governor.governed_request`` so the whole
    ``wait_if_needed -> send -> note_response`` critical section runs inside the
    host-global ``fcntl.flock`` — the >=3s spacing + 429 ``banned_until`` sentinel
    therefore hold across the OAI harvest, the PDF fetch, AND this search, not
    merely per-process. A BARE ``client.get`` here (the prior shape) only spaced
    within this process, so a concurrent harvest + a ``search``/``fetch_by_id``
    could both fire inside one 3s window — the exact un-spaced-parallel-stream
    race the governor closes.

    The ``throttle`` is threaded down by the CLIs (which own an ``ArxivThrottle``
    and persist its 429 sentinel across invocations). When ``None``, the governed
    seam constructs the CANONICAL default throttle, so even a caller that forgets
    to pass one is still host-globally spaced + ban-aware. ``raise_for_status`` is
    applied to the governed response AFTER the gated send; ``ArxivBanned`` (an
    active ban) propagates from inside the governed call so the caller PAUSES.

    Caller can inject an ``httpx.Client`` with a ``MockTransport`` for tests;
    otherwise we build a short-lived client per call (single connection).
    """
    from acquisition.arxiv.rate_governor import governed_request

    headers = {"User-Agent": DEFAULT_USER_AGENT}

    if client is not None:
        def _send() -> httpx.Response:
            return client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

        r = governed_request(_send, throttle=throttle)
        r.raise_for_status()
        return r.content

    with httpx.Client(
        timeout=DEFAULT_TIMEOUT_S,  # module default; same pattern as acquisition/papers/core.py DEFAULT_TIMEOUT_S
    ) as c:
        def _send() -> httpx.Response:
            return c.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

        r = governed_request(_send, throttle=throttle)
        r.raise_for_status()
        return r.content


def search(
    *,
    query: str | None = None,
    author: str | None = None,
    category: str | None = None,
    max_results: int = 5,
    sort: str = "relevance",
    client: httpx.Client | None = None,
    base_url: str | None = None,
    throttle: ArxivThrottle | None = None,
) -> list[ArxivPaper]:
    """Query arXiv. At least one of query/author/category must be set.

    ``sort`` is one of ``relevance`` / ``date`` / ``updated``.
    ``client`` is an injectable ``httpx.Client`` — tests pass a
    ``MockTransport``-backed client; production passes ``None``.

    ``throttle`` is the cross-process ``ArxivThrottle`` (>=3s spacing + 429
    sentinel) the host-global rate governor reuses; the CLIs thread theirs in so
    a live 429's ban sentinel persists. When ``None``, the governed seam owns the
    canonical throttle (SPR-09 M1) — this export-search egress is NEVER
    ungoverned."""
    url = _build_search_url(
        query=query, author=author, category=category,
        max_results=max_results, sort=sort, base_url=base_url,
    )
    body = _http_get(url, client=client, throttle=throttle)
    return _parse_response(body)


def fetch_by_id(
    arxiv_id: str,
    *,
    client: httpx.Client | None = None,
    base_url: str | None = None,
    throttle: ArxivThrottle | None = None,
) -> ArxivPaper | None:
    """Fetch a single paper by id. Returns ``None`` when arXiv
    returns no entries (id unknown).

    ``throttle`` is threaded through to the host-global rate governor (SPR-09 M1)
    exactly as in :func:`search`; this export-search egress is never ungoverned."""
    url = _build_search_url(
        ids=[arxiv_id], max_results=1, base_url=base_url,
    )
    body = _http_get(url, client=client, throttle=throttle)
    papers = _parse_response(body)
    return papers[0] if papers else None
